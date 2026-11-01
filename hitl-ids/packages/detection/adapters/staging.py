"""Offline EVE staging. No operational tables, learning, or evaluation writes."""
from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from packages.contracts import db
from packages.contracts.models import utc_now
from .admission_policy import AdmissionPolicy, load_admission_policy
from .suricata_bundle import SUPPORTED, parse_record, correlation_key, build_bundle, canonical_json

PENDING = "Operational admission: pending; requires separately reviewed Alert Contract V2."


@dataclass
class ImportReport:
    parsed: int = 0
    staged: int = 0
    duplicate: int = 0
    preserved: int = 0
    duplicate_records: int = 0
    skipped: int = 0
    invalid: int = 0
    rejected_by_policy: int = 0
    dry_run: bool = False
    issues: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "operational_admission": "pending"}


def _finite_json(value: str):
    raise ValueError(f"non-finite JSON constant {value} is not allowed")


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _decode(text: str):
    return json.loads(text, parse_constant=_finite_json, object_pairs_hook=_unique_keys)


def records(path: Path):
    """Accept a JSON object/array or JSONL; retain per-line failures for JSONL."""
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        return
    try:
        document = _decode(text)
    except ValueError as exc:
        if text.lstrip().startswith("[") or len(text.splitlines()) <= 1:
            yield 1, None, str(exc)
            return
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                yield line_number, _decode(line), None
            except ValueError as error:
                yield line_number, None, str(error)
    else:
        for index, event in enumerate(document if isinstance(document, list) else [document], 1):
            yield index, event, None


def _has_inbox(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                        "AND name='external_alert_inbox'").fetchone() is not None


def _correlated_batch(conn, path, sensor_id, report, dry_run):
    """Preserve validated records, then seal complete per-flow snapshots for this offline batch.

    Earlier evidence-only batches can contribute. A late change to a sealed detection fails
    the whole import explicitly; it cannot mutate admitted evidence or produce a duplicate.
    """
    has_records = conn is not None and conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='suricata_eve_records'").fetchone() is not None
    groups, seen = {}, set()
    for index, raw, error in records(path):
        if error is not None:
            report.invalid += 1
            report.issues.append({'record': index, 'reason': error})
            continue
        report.parsed += 1
        if not isinstance(raw, dict) or not isinstance(raw.get('event_type'), str):
            report.invalid += 1
            report.issues.append({'record': index, 'reason': 'event object requires event_type'})
            continue
        if raw['event_type'] not in SUPPORTED:
            report.skipped += 1
            continue
        try:
            record = parse_record(raw, sensor_id)
        except (ValueError, TypeError):
            report.invalid += 1
            report.issues.append({'record': index, 'reason': 'invalid EVE evidence'})
            continue
        key = correlation_key(record)
        if key not in groups:
            groups[key] = {}
            if has_records and record.flow_id is not None:
                for previous in conn.execute('SELECT raw_snapshot FROM suricata_eve_records WHERE sensor_id=? AND flow_id=?',
                                             (sensor_id, record.flow_id)):
                    old = parse_record(json.loads(previous[0]), sensor_id)
                    groups[key][old.source_record_ref] = old
        groups[key][record.source_record_ref] = record
        exists = record.source_record_ref in seen or (has_records and conn.execute(
            'SELECT 1 FROM suricata_eve_records WHERE sensor_id=? AND source_record_ref=?',
            (sensor_id, record.source_record_ref)).fetchone())
        if exists:
            report.duplicate_records += 1
        else:
            if not dry_run:
                conn.execute('INSERT INTO suricata_eve_records (sensor_id,source_record_ref,event_type,flow_id,tx_id,'
                    'timestamp,raw_snapshot,imported_at) VALUES (?,?,?,?,?,?,?,?)', (sensor_id,record.source_record_ref,
                    record.event_type,record.flow_id,record.tx_id,record.timestamp,canonical_json(record.raw),
                    db.format_timestamp(utc_now())))
            report.preserved += 1
        seen.add(record.source_record_ref)
    for index, group in enumerate(groups.values(), 1):
        if any(record.event_type == 'alert' for record in group.values()):
            yield index, build_bundle(group.values())


def stage_file(conn: sqlite3.Connection | None, path: Path, sensor_id: str, *,
               policy: AdmissionPolicy | None = None, dry_run: bool = False) -> ImportReport:
    """Stage a batch atomically. Caller has migrated; dry-run can use a read-only connection.

    Detection identity is sensor + flow_id, or sensor + record hash without flow_id.
    Raw record hashes ignore JSON formatting and key order. Invalid evidence is never stored.
    Unsupported native severity may be preserved but cannot enter the alert inbox.
    Infrastructure or sealed-bundle conflicts roll back the batch.
    """
    if not sensor_id.strip():
        raise ValueError("sensor-id must be nonempty")
    policy = policy or load_admission_policy()
    report = ImportReport(dry_run=dry_run)
    has_inbox = conn is not None and _has_inbox(conn)
    if not dry_run and not has_inbox:
        raise ValueError("database must have the external inbox migration")
    if conn is not None and conn.in_transaction:
        raise ValueError("staging requires a connection outside a transaction")
    if conn is not None:
        conn.execute("BEGIN" if dry_run else "BEGIN IMMEDIATE")
    try:
        for index, alert in _correlated_batch(conn, path, sensor_id, report, dry_run):
            identity = str(alert.canonical_alert_id)
            reference = alert.source_record_reference
            previous = conn.execute('SELECT canonical_snapshot FROM external_alert_inbox WHERE canonical_alert_id=?',
                                    (identity,)).fetchone() if has_inbox else None
            if previous is not None:
                if previous[0] != alert.model_dump_json(by_alias=True):
                    raise ValueError('flow bundle is sealed; late evidence requires a future explicit bundle revision')
                report.duplicate += 1
                continue
            try:
                decision = policy.decide(alert)
            except ValueError as exc:
                report.rejected_by_policy += 1
                report.issues.append({"record": index, "reason": str(exc)})
                continue
            row = inbox_row(alert, decision, sensor_id)
            if not dry_run:
                conn.execute(f"INSERT INTO external_alert_inbox ({', '.join(row)}) "
                             f"VALUES ({', '.join('?' for _ in row)})", list(row.values()))
            report.staged += 1
        if conn is not None:
            conn.rollback() if dry_run else conn.commit()
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    return report


def inbox_row(alert, decision, sensor_id):
    """Serialize the immutable admission boundary, shared with historical snapshot fixtures."""
    return dict(
        canonical_alert_id=str(alert.canonical_alert_id), detector_source=alert.detector_source,
        sensor_id=sensor_id, raw_reference=alert.source_record_reference, occurred_at=alert.occurred_at,
        occurred_at_timezone_offset=alert.occurred_at_timezone_offset,
        native_severity=decision.native_severity, confidence=alert.confidence,
        detection_title=alert.detection_title, detection_category=alert.detection_category,
        source_ip=alert.source_ip, destination_ip=alert.destination_ip,
        source_port=alert.source_port, destination_port=alert.destination_port,
        protocol=alert.protocol, canonical_snapshot=alert.model_dump_json(by_alias=True),
        admission_policy_version=decision.policy_version, admission_decision="hold_for_review",
        admission_reason=PENDING, review_required=decision.requires_review,
        learning_eligible=decision.learning_eligible, evaluation_eligible=decision.evaluation_included,
        proposed_operational_priority=decision.initial_operational_priority,
        proposed_evidence_class=decision.evidence_class,
        policy_snapshot=json.dumps(decision.policy_snapshot, sort_keys=True, allow_nan=False),
        import_status="staged", imported_at=db.format_timestamp(utc_now()))


def open_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def import_file(path: Path, sensor_id: str, database: Path, *,
                policy: AdmissionPolicy | None = None, dry_run: bool = False) -> ImportReport:
    if dry_run:
        if not database.exists():
            return stage_file(None, path, sensor_id, policy=policy, dry_run=True)
        with closing(open_readonly(database)) as conn:
            return stage_file(conn, path, sensor_id, policy=policy, dry_run=True)
    # Require an existing project database. A typo must not create an empty operational database.
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=rw", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA recursive_triggers=ON")
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='alerts'").fetchone():
            raise ValueError("expected an existing HITL project database")
        db.migrate(conn)
        return stage_file(conn, path, sensor_id, policy=policy)


def inspect_inbox(database: Path, limit: int = 50) -> dict[str, Any]:
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    with closing(open_readonly(database)) as conn:
        if not _has_inbox(conn):
            return {"operational_admission": "pending", "total": 0, "records": []}
        total = conn.execute("SELECT COUNT(*) FROM external_alert_inbox").fetchone()[0]
        rows = conn.execute("SELECT * FROM external_alert_inbox ORDER BY id DESC LIMIT ?", (limit,))
        return {"operational_admission": "pending", "total": total,
                "records": [dict(row) for row in rows]}
