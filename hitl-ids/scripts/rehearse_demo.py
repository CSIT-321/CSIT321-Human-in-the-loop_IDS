"""Rehearse the S16 demo narrative end to end, against a throwaway copy of the demo database.

    python scripts/rehearse_demo.py              # copies data/demo.db, plays the narrative, exits 0/1
    python scripts/rehearse_demo.py --keep       # also prints the copy's path, for the browser e2e

**Every claim the narrative makes is asserted here, through the real API** — not read from a slide.
The plan's S16 gate is "the full narrative executes with no manual DB fixes"; this is that check at
the API level, and `apps/web/e2e/demo.spec.ts` is the same story driven through the browser.

**It never writes to `data/demo.db`.** Verdicts are permanent (the audit trail is append-only), so a
rehearsal against the real database would leave the next audience a queue that has already been
judged. The copy is made first.

The narrative (plan S16, as corrected in changelog v1.21):

1. The analyst opens the queue. ``AL-00478`` sits in the Tier 2 band at 99.89: the model calls it a
   Web Attack, no rule agrees, and ground truth says it is **benign**.
2. They dismiss it as a false positive. The guardrail caps the change at the Critical floor of 70 and
   says so; the Tier 2 marker is withdrawn and the alert drops down the queue.
3. ``AL-03086`` sits in the bottom band at 36.94 — an **attempted Web Attack both detectors missed**.
   They confirm it; it climbs out of the bottom band.
4. They confirm three members of the ``Port Scan / 445`` family. The family's learning gate opens and
   the **two members nobody judged move into the Tier 2 band** (S7b).
5. The service restarts: every change persists.
6. The administrator finds the cap in the guardrail log; the evaluator reads the three-arm deltas,
   including the one that went the wrong way.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

HITL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HITL))

from fastapi.testclient import TestClient  # noqa: E402

from apps.api.main import create_app  # noqa: E402
from packages.evaluation.truth import GroundTruth  # noqa: E402

DEFAULT_DB = HITL / "data" / "demo.db"

FALSE_POSITIVE = "AL-00478"
MISSED_ATTACK = "AL-03086"
CLIMB = "AL-02717"  # 88.48 -> 98.48: the largest fully-visible climb among the non-saturated alerts
FAMILY_KEY = '["Port Scan",445,"tcp","-"]'
FAMILY_JUDGED = ("AL-01696", "AL-03873", "AL-03153")
FAMILY_UNTOUCHED = ("AL-03044", "AL-04526")

ANALYST: dict[str, str] = {}
ADMIN: dict[str, str] = {}
EVALUATOR: dict[str, str] = {}


def sign_in(client: TestClient, username: str, password: str) -> dict[str, str]:
    """S18a: the rehearsal signs in the way the console does — one real account per view."""
    token = ok(client.post("/api/auth/login",
                           json={"username": username, "password": password}))["token"]
    return {"Authorization": f"Bearer {token}"}


class RehearsalFailed(AssertionError):
    pass


def check(condition: bool, claim: str) -> None:
    if not condition:
        raise RehearsalFailed(claim)
    print(f"  PASS  {claim}")


def ok(response: Any) -> dict[str, Any]:
    if response.status_code >= 400:
        raise RehearsalFailed(f"{response.request.method} {response.request.url} -> "
                              f"{response.status_code}: {response.text}")
    return response.json()


def find(client: TestClient, record: str) -> dict[str, Any]:
    items = ok(client.get("/api/alerts", params={"search": record, "limit": 5},
                          headers=ANALYST))["items"]
    matches = [item for item in items if item["sourceRecordId"] == record]
    if len(matches) != 1:
        raise RehearsalFailed(f"{record} is not uniquely findable by search")
    return matches[0]


def rank(client: TestClient, record: str) -> int:
    """The alert's 1-based position in the queue's contract order."""
    offset = 0
    while True:
        page = ok(client.get("/api/alerts", params={"limit": 200, "offset": offset},
                             headers=ANALYST))
        for index, item in enumerate(page["items"]):
            if item["sourceRecordId"] == record:
                return offset + index + 1
        offset += 200
        if offset >= page["page"]["total"]:
            raise RehearsalFailed(f"{record} is not in the queue")


def verdict(client: TestClient, alert_ref: str, category: str, note: str) -> dict[str, Any]:
    return ok(client.post(f"/api/alerts/{alert_ref}/feedback",
                          json={"category": category, "note": note}, headers=ANALYST))


def rehearse(database: Path) -> None:
    global ANALYST, ADMIN, EVALUATOR
    truth = GroundTruth.load()
    client = TestClient(create_app(database))
    ANALYST = sign_in(client, "g.ang", "analyst-demo")
    ADMIN = sign_in(client, "admin", "admin-demo")
    EVALUATOR = sign_in(client, "evaluator", "evaluator-demo")

    print("\n1. The queue, and a confident model that is wrong")
    fp = find(client, FALSE_POSITIVE)
    fp_rank_before = rank(client, FALSE_POSITIVE)
    check(fp["queueClass"] == "tier2_candidate", f"{FALSE_POSITIVE} is a Tier 2 candidate")
    check(fp["evidenceClass"] == "ml_only", f"{FALSE_POSITIVE} is model-only evidence")
    check(fp["combinedScore"] == 99.89, f"{FALSE_POSITIVE} scores 99.89")
    detail = ok(client.get(f"/api/alerts/{fp['alertRef']}", headers=ANALYST))
    check(not detail["signature"].get("matched"), "no signature rule matched it")
    check(detail["ml"]["predictedClass"] == "Web Attack", "the model calls it a Web Attack")
    check(bool(detail["ml"]["topSupporting"]), "TreeSHAP names the features that drove the call")
    check(not truth.malicious(FALSE_POSITIVE), "ground truth: it is benign")
    print(f"        (rank {fp_rank_before} of 5,000)")

    print("\n2. The analyst dismisses it; the guardrail binds, visibly")
    response = verdict(client, fp["alertRef"], "mark_false_positive",
                       "Benign browsing to an internal web server; no exploit payload.")
    chain = response["feedback"]["adjustment"]
    codes = [item["code"] for item in chain["interventions"]]
    check(chain["requestedDelta"] == -30.0, "the verdict requests -30")
    check(chain["action"] == "capped" and "critical_alert_floor" in codes,
          "the Critical floor caps it")
    check(chain["scoreAfter"] == 70.0, "the score is held at 70")
    check(any("floor of 70" in item["explanation"] for item in chain["interventions"]),
          "the guardrail explains itself with the configured value")
    check(chain["queueClassBefore"] == "tier2_candidate" and chain["queueClassAfter"] == "ml_only",
          "the Tier 2 marker is withdrawn: Tier 2 candidate -> Model only")
    fp_rank_after = rank(client, FALSE_POSITIVE)
    check(fp_rank_after > fp_rank_before,
          f"it drops down the queue (rank {fp_rank_before} -> {fp_rank_after})")

    print("\n3. An attack both detectors missed, confirmed by a human")
    missed = find(client, MISSED_ATTACK)
    missed_rank_before = rank(client, MISSED_ATTACK)
    check(missed["evidenceClass"] == "none" and missed["queueClass"] == "none",
          f"{MISSED_ATTACK} was flagged by nothing and sits in the bottom band")
    check(missed["combinedScore"] == 36.94, f"{MISSED_ATTACK} scores 36.94")
    record = truth.of(MISSED_ATTACK)
    check(record.attack_type == "Web Attack" and record.is_attempted,
          "ground truth: an attempted Web Attack")
    chain = verdict(client, missed["alertRef"], "confirm_true_positive",
                    "Repeated crafted requests to the login form; attempt, not success.")["feedback"]["adjustment"]
    check(chain["action"] == "applied" and chain["actualDelta"] == 10.0,
          "+10 is applied; no guardrail needed to act")
    check(chain["queueClassBefore"] == "none" and chain["queueClassAfter"] == "ml_only",
          "it climbs out of the bottom band")
    missed_rank_after = rank(client, MISSED_ATTACK)
    check(missed_rank_after < missed_rank_before,
          f"it climbs the queue (rank {missed_rank_before} -> {missed_rank_after})")

    print("\n3b. The saturation filter, and a climb that is fully visible")
    filtered = ok(client.get("/api/alerts", params={
        "evidenceClass": ["ml_only"], "detectionMaxScore": 99.999, "limit": 50}, headers=ANALYST))
    check(filtered["page"]["total"] == 21,
          "the not-saturated filter finds the 21 flagged alerts below 100.0")
    climb = find(client, CLIMB)
    check(climb["detectionScore"] == 88.48 and climb["queueClass"] == "ml_only",
          f"{CLIMB} sits in Model only at 88.48 - the widest headroom below 100")
    chain = verdict(client, climb["alertRef"], "confirm_true_positive",
                    "Repeated SQL-injection probes against the web tier; confirm and escalate."
                    )["feedback"]["adjustment"]
    check(chain["action"] == "applied" and chain["actualDelta"] == 10.0,
          "+10 is applied in full - nothing clamps at 100")
    check(chain["scoreAfter"] == 98.48, "88.48 -> 98.48: the score visibly climbs")
    check(chain["queueClassBefore"] == "ml_only" and chain["queueClassAfter"] == "tier2_candidate",
          "a True Positive on a severity >= 7 class earns the Tier 2 band (E2)")

    print("\n4. Three agreeing verdicts teach a family; alerts nobody touched move")
    judged = [find(client, record) for record in FAMILY_JUDGED]
    untouched_before = {record: find(client, record) for record in FAMILY_UNTOUCHED}
    for record in (*FAMILY_JUDGED, *FAMILY_UNTOUCHED):
        check(truth.of(record).attack_type == "Port Scan", f"ground truth: {record} is a Port Scan")
    family_detail = ok(client.get(f"/api/alerts/{judged[0]['alertRef']}", headers=ANALYST))
    check(family_detail["family"]["familyKey"] == FAMILY_KEY, f"the family is {FAMILY_KEY}")
    check(family_detail["family"]["members"] == 5, "it has five members")
    check(all(item["queueClass"] == "ml_only" for item in untouched_before.values()),
          "the two unjudged members start in the Model only band")
    last: dict[str, Any] = {}
    for index, item in enumerate(judged, start=1):
        last = verdict(client, item["alertRef"], "confirm_true_positive",
                       f"Sequential SMB probes from one host ({index} of 3).")
        if index < 3:
            check(not last["family"]["gateOpen"], f"after {index} verdict(s) the gate stays closed")
    check(last["family"]["gateOpen"], "the third agreeing verdict opens the gate")
    check(last["family"]["membersMoved"] == 2, "two members nobody judged moved")
    for record in FAMILY_UNTOUCHED:
        after = find(client, record)
        check(after["queueClass"] == "tier2_candidate" and not after["hasFeedback"],
              f"{record} moved into the Tier 2 band without a verdict of its own")

    print("\n5. A restart: everything persists")
    restarted = TestClient(create_app(database))
    check(find(restarted, FALSE_POSITIVE)["combinedScore"] == 70.0, f"{FALSE_POSITIVE} is still 70")
    history = ok(restarted.get(f"/api/alerts/{fp['alertRef']}/feedback-history", headers=ANALYST))
    check(len(history["events"]) == 1, "its verdict is in the history")
    check(find(restarted, FAMILY_UNTOUCHED[0])["queueClass"] == "tier2_candidate",
          "the family's learning persisted")

    print("\n6. The administrator and the evaluator")
    log = ok(restarted.get("/api/audit-log", params={"eventType": ["GUARDRAIL_INTERVENTION"]},
                           headers=ADMIN))["items"]
    check(any(entry.get("alertRef") == fp["alertRef"] for entry in log),
          "the cap is in the guardrail log")
    learning = ok(restarted.get("/api/audit-log", params={"eventType": ["SIMILAR_ALERT_LEARNING"]},
                                headers=ADMIN))["items"]
    check(bool(learning), "the family learning is in the audit trail")
    runs = ok(restarted.get("/api/evaluation/runs", headers=EVALUATOR))["items"]
    check(bool(runs), "the evaluator can find the three-arm run")
    run = ok(restarted.get(f"/api/evaluation/runs/{runs[0]['runId']}", headers=EVALUATOR))
    deltas = run["deltas"]["B_minus_A"]
    check(run["detectionMetricsIdenticalAcrossArms"], "detection is identical across all three arms")
    # S15: the deltas are rendered as measured, in whichever direction they went. Under the
    # severity-first queue (v1.31) feedback no longer costs a top-50 place; the band order did, at
    # precision@50 -0.020. The wrong-way evidence now lives in the slower metrics.
    check(deltas["false_positives_in_top_50"] == 0,
          "feedback adds no false positive to the top 50 (the band order added 1)")
    negative = {key: value for key, value in deltas.items()
                if isinstance(value, (int, float)) and value < 0}
    check(bool(negative), "the remaining deltas are still reported as measured: "
          + ", ".join(f"{key} {value:+g}" for key, value in sorted(negative.items())[:3]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", type=Path, default=DEFAULT_DB,
                        help="source database; it is copied, never modified")
    parser.add_argument("--keep", action="store_true", help="keep the rehearsed copy and print its path")
    args = parser.parse_args()
    if not args.database.exists():
        print(f"No database at {args.database}. Build it with: python scripts/run_detection.py")
        return 2

    workdir = Path(tempfile.mkdtemp(prefix="hitl-rehearsal-"))
    copy = workdir / "rehearsal.db"
    shutil.copy2(args.database, copy)
    print(f"Rehearsing on a copy: {copy}")
    try:
        rehearse(copy)
    except RehearsalFailed as failure:
        print(f"\n  FAIL  {failure}")
        return 1
    finally:
        if not args.keep:
            shutil.rmtree(workdir, ignore_errors=True)
    print("\nThe demo narrative holds end to end.")
    if args.keep:
        print(f"Rehearsed database kept at: {copy}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
