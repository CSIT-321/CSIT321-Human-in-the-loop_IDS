"""The batch detection run (plan step S9): one command, one populated database.

    flows (S3 seam) -> signature rules (S5) -> model + TreeSHAP (S4) -> fusion (S6)
          -> alert + flow_data + queue band (S7b) -> audit (S8)

D3's shape: detection is an **offline batch**, never inline in the API. Every flow in the source
becomes an alert, including the flows no detector flagged — they are the queue's bottom band and the
evaluation's denominator, and leaving them out would quietly turn recall into precision.

The whole run is one transaction, so a run that fails leaves no half-populated database behind and
the summary can be trusted as a description of what is stored.

Reproducibility (NFR-05) is a property of the row, not of a promise: ``detection_runs`` keeps the
dataset, the model version, the rule-set version, the fusion configuration, the guardrail settings
and the seed. ``tests/test_run.py`` runs the same source twice and compares every score.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from packages.contracts import db
from packages.contracts import models as m
from packages.detection.audit.writer import AuditWriter
from packages.detection.feedback.learning import family_key_of, member_placement
from packages.detection.fusion.cef import FusionConfig, fuse, severity_for
from packages.detection.guardrail.policy import GuardrailPolicy
from packages.detection.pipeline import store
from packages.detection.pipeline.predictor import Predictor
from packages.detection.pipeline.source import Flow, FlowSource, flow_record
from packages.detection.ranking.severity import SeverityChart, load_severity_chart
from packages.detection.signature.engine import match_all
from packages.detection.signature.observable import project_record
from packages.detection.signature.rule_set import load_rule_set

DEFAULT_BATCH = 500


@dataclass(frozen=True)
class DetectionSummary:
    """What one run produced, as stored."""

    run_id: int
    dataset_id: int
    source: str
    model_version: str
    rule_set_version: str
    flows: int
    alerts: int
    by_evidence: dict[str, int] = field(default_factory=dict)
    by_queue_class: dict[str, int] = field(default_factory=dict)
    predictions_unavailable: int = 0
    explanations_computed: bool = True

    @property
    def tier2_candidates(self) -> int:
        return self.by_queue_class.get("tier2_candidate", 0)


def batched(flows: Iterator[Flow], size: int) -> Iterator[list[Flow]]:
    batch: list[Flow] = []
    for flow in flows:
        batch.append(flow)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def run_detection(conn: sqlite3.Connection, source: FlowSource, predictor: Predictor, *,
                  dataset_id: int, rules: Sequence[m.SignatureRule] | None = None,
                  config: FusionConfig | None = None, chart: SeverityChart | None = None,
                  policy: GuardrailPolicy | None = None, seed: int | None = None,
                  batch: int = DEFAULT_BATCH, actor_id: int | None = None,
                  now: datetime | None = None) -> DetectionSummary:
    """Score every flow in ``source`` into ``conn``. One transaction; commits on success."""
    rules = [rule for rule in (rules if rules is not None else load_rule_set()) if rule.enabled]
    if not rules:
        raise ValueError("a detection run needs at least one enabled signature rule")
    versions = {rule.version for rule in rules}
    if len(versions) != 1:
        raise ValueError(f"rules span several versions {sorted(versions)}; a run records one")
    config = config if config is not None else FusionConfig()
    chart = chart if chart is not None else load_severity_chart()
    policy = policy if policy is not None else GuardrailPolicy()
    now = now if now is not None else m.utc_now()

    flows = alerts = unavailable = 0
    with conn:  # one transaction: a failed run stores nothing
        run_id = store.start_run(
            conn, dataset_id=dataset_id, model_version=predictor.version,
            rule_set_version=versions.pop(), fusion_weights=config.snapshot(),
            guardrail_config=store.guardrail_snapshot(conn), seed=seed, now=now)
        for group in batched(source.flows(), batch):
            predictions = predictor.predict(group)
            for flow in group:
                flows += 1
                prediction = predictions.get(flow.source_record_id)
                if prediction is None or prediction.prediction_status != "available":
                    unavailable += 1
                record = project_record(flow.features)
                decision = fuse(match_all(record, rules), prediction, config)
                stored = flow_record(flow)
                alert = _place(conn, decision.to_alert(dataset_id=dataset_id, run_id=run_id,
                                                       created_at=now), stored, chart, policy,
                               config)
                store.insert_alert(conn, alert, stored)
                alerts += 1
        run = store.finish_run(conn, run_id, alert_count=alerts, now=now)
        AuditWriter(conn).detection_run(
            run, actor_id=actor_id,
            rationale=f"batch detection over {source.name} ({flows} flows)")

    return DetectionSummary(
        run_id=run_id, dataset_id=dataset_id, source=source.name,
        model_version=predictor.version, rule_set_version=run.rule_set_version, flows=flows,
        alerts=alerts, by_evidence=store.counts_by(conn, "evidence_class", run_id=run_id),
        by_queue_class=store.counts_by(conn, "queue_class", run_id=run_id),
        predictions_unavailable=unavailable,
        explanations_computed=bool(getattr(predictor, "computes_explanations", False)))


def _place(conn: sqlite3.Connection, alert: m.Alert, flow: m.FlowRecord, chart: SeverityChart,
           policy: GuardrailPolicy, config: FusionConfig) -> m.Alert:
    """Give a freshly fused alert its family, apply what that family has already learned, then band it.

    A family's learning lives in ``alert_families``, and this is the path that carries it to a new
    alert (S7b). Before this, placement ran on a zero adjustment: a detection run over new flows
    started every alert at its raw detection score, and the family's stored learning sat unused.
    """
    key = family_key_of(alert, flow)
    learned = store.family_by_key(conn, key)
    adjustment = learned.applied_adjustment if learned is not None else 0.0
    offset = learned.applied_offset if learned is not None else 0
    place = member_placement(alert, adjustment, offset, chart, policy)
    if not adjustment and not offset and (
            place.score != alert.combined_score or place.requires_review != alert.requires_review):
        raise AssertionError(  # S6 and S7b must agree before any feedback exists
            f"detection placement disagrees with fusion for {flow.source_record_id}: "
            f"{(place.score, place.requires_review)} != "
            f"{(alert.combined_score, alert.requires_review)}")
    return m.Alert.model_validate({
        **alert.model_dump(), "family_key": key,
        "combined_score": place.score,
        "severity": severity_for(place.score, alert.attack_category, config.class_ceilings,
                                 critical_threshold=config.critical_threshold),
        "requires_review": place.requires_review,
        "queue_class": place.queue_class, "queue_priority": place.queue_priority})


def run_summary_row(summary: DetectionSummary) -> dict[str, object]:
    """The summary as a flat row, for a script's output or a report."""
    return {
        "run_id": summary.run_id, "source": summary.source, "flows": summary.flows,
        "alerts": summary.alerts, "model_version": summary.model_version,
        "rule_set_version": summary.rule_set_version, "by_evidence": summary.by_evidence,
        "by_queue_class": summary.by_queue_class, "tier2_candidates": summary.tier2_candidates,
        "predictions_unavailable": summary.predictions_unavailable,
        "explanations_computed_in_run": summary.explanations_computed,
    }


def open_database(path: str, *, create: bool = True) -> sqlite3.Connection:
    """Connect to a demo database, creating the schema when the file is new."""
    exists = Path(path).exists()
    if not exists and not create:
        raise FileNotFoundError(path)
    conn = db.connect(path)
    if not exists:
        db.create_schema(conn)
    else:
        db.migrate(conn)  # an existing database is brought up to the current schema, never rebuilt
    return conn
