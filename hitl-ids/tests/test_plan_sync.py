"""The lifecycle documents must agree with each other, and with the code.

**Why this file exists.** The plan (`plans/hitl-ids-demo-build.md`) is canonical for what to build
next, but for eleven changelog versions nobody opened it: work was driven from `HANDOVER.md` §7
while the plan still told a reader to retire `SIG-FTP-BRUTE-FORCE` (one of the two rules that
survive), to expect 8 `signature_override` alerts (there are none), and to rehearse a demo narrative
whose own stop-condition had already triggered. None of it was caught, because nothing checked.

A delegated worker is handed a step from the plan. If the plan is stale the worker builds the wrong
thing *correctly*, and the error surfaces at review — which is the lapse this suite closes.

These tests are cheap and deliberately narrow. They do not review prose; they check the handful of
facts that must be identical in more than one place:

* the plan's ``PLAN-STATUS`` table against the handover's §7 "done" list;
* exactly one ``NEXT`` step, and that it is not already done elsewhere;
* the changelog's ``← current`` version against the handover's header;
* the test count the handover quotes against the number actually defined;
* every step in the dependency graph having a status row;
* and that the plan does not once again *assert* a claim the deviations register lists as withdrawn.

The model is `test_contracts.py::test_columns_are_tdm_names_plus_logged_deviations`, which fails on
an unlogged schema column. This is the same idea raised from the schema to the plan.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

HITL = Path(__file__).resolve().parents[1]
REPO = HITL.parent
PLAN = REPO / "plans" / "hitl-ids-demo-build.md"
HANDOVER = HITL / "docs" / "HANDOVER.md"
CHANGELOG = HITL / "docs" / "plan-changelog.md"
DEVIATIONS = HITL / "docs" / "deviations.md"

STATUSES = {"DONE", "PARTIAL", "NEXT", "TODO"}


def read(path: Path) -> str:
    assert path.exists(), f"{path} is missing; the lifecycle documents are incomplete"
    return path.read_text(encoding="utf-8")


def plan_status() -> dict[str, tuple[str, str]]:
    """The plan's canonical status table: step -> (status, landed)."""
    body = read(PLAN)
    block = re.search(r"<!-- PLAN-STATUS:BEGIN -->(.*?)<!-- PLAN-STATUS:END -->", body, re.S)
    assert block, "the plan has lost its PLAN-STATUS markers; it can no longer answer 'what next'"
    rows: dict[str, tuple[str, str]] = {}
    for line in block.group(1).splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4 or cells[0] == "Step" or set(cells[0]) <= {"-"}:
            continue
        step, _name, status, landed = cells
        assert re.fullmatch(r"S\d+[ab]?", step), f"{step!r} is not a step id"
        assert status in STATUSES, f"{step} has unknown status {status!r}"
        rows[step] = (status, landed)
    assert rows, "the PLAN-STATUS table is empty"
    return rows


def handover_done_steps() -> set[str]:
    """Steps the handover's §7 table marks done, by its ``**DONE`` convention."""
    done: set[str] = set()
    for line in read(HANDOVER).splitlines():
        if "**DONE" not in line:
            continue
        done.update(re.findall(r"\bS\d+[ab]?\b", line.split("**DONE")[0]))
    return done


def test_every_step_in_the_dependency_graph_has_a_status():
    """A step in the graph with no status row is a step nobody is tracking."""
    graph = set(re.findall(r"\bS\d+[ab]?\b", read(PLAN).split("## Step status")[0]))
    # S7 and S10 appear in the graph under their pre-split names; their halves carry the status.
    missing = {step for step in graph if step not in plan_status()} - {"S7", "S10"}
    assert not missing, f"steps in the plan with no status row: {sorted(missing)}"


def test_the_plan_names_exactly_one_next_step():
    """Two NEXT steps means nobody knows what to pick up; none means the plan claims to be over."""
    nxt = [step for step, (status, _) in plan_status().items() if status == "NEXT"]
    assert len(nxt) == 1, f"expected exactly one NEXT step, found {nxt}"


def test_the_plan_and_the_handover_agree_on_what_is_done():
    """The drift that produced plan v1.1, as a test.

    The handover is a session's entry point; the plan is canonical for the work. When they disagree
    about which steps are finished, whichever one a reader happens to open decides what gets built.
    """
    plan_done = {step for step, (status, _) in plan_status().items() if status == "DONE"}
    only_handover = handover_done_steps() - plan_done
    assert not only_handover, (
        f"HANDOVER §7 marks {sorted(only_handover)} done but the plan does not. Update the "
        f"PLAN-STATUS table in plans/hitl-ids-demo-build.md in the same commit.")


def test_the_next_step_is_not_already_done_somewhere_else():
    nxt = next(step for step, (status, _) in plan_status().items() if status == "NEXT")
    assert nxt not in handover_done_steps(), (
        f"the plan says {nxt} is next, but the handover marks it done")


def test_every_done_step_records_the_version_that_landed_it():
    """A DONE step with no changelog version cannot be audited back to its evidence."""
    versions = set(re.findall(r"^## (v\d+\.\d+)", read(CHANGELOG), re.M))
    for step, (status, landed) in plan_status().items():
        if status != "DONE":
            continue
        assert landed != "—", f"{step} is DONE but records no changelog version"
        assert landed in versions, f"{step} cites {landed}, which is not in the changelog"


def test_the_changelog_marks_exactly_one_current_version():
    current = re.findall(r"^## (v\d+\.\d+).*←\s*\*\*current\*\*", read(CHANGELOG), re.M)
    assert len(current) == 1, f"expected one 'current' changelog version, found {current}"


def test_the_handover_header_cites_the_current_changelog_version():
    match = re.search(r"^## (v\d+\.\d+).*←\s*\*\*current\*\*", read(CHANGELOG), re.M)
    assert match, "the changelog marks no current version"
    header = read(HANDOVER).split("## 0.")[0]
    assert f"changelog {match.group(1)}" in header, (
        f"the changelog's current version is {match.group(1)}; the handover header does not cite it")


def test_the_handover_quotes_the_real_test_count():
    """'279 tests, 0 skipped' in a header is a claim, and it goes stale the moment a file lands."""
    defined = sum(len(re.findall(r"^def test_", path.read_text(encoding="utf-8"), re.M))
                  for path in (HITL / "tests").glob("test_*.py"))
    quoted = re.search(r"\*\*(\d+) tests, 0 skipped\*\*", read(HANDOVER))
    assert quoted, "the handover no longer states a test count"
    # Parametrised cases make the collected count >= the number of `def test_` functions.
    assert int(quoted.group(1)) >= defined, (
        f"the handover claims {quoted.group(1)} tests but {defined} test functions are defined; "
        f"run pytest and update the header")


def test_the_deviations_register_the_plan_mandates_exists():
    body = read(DEVIATIONS)
    assert "## A." in body and "## B." in body, "the deviations register has lost its sections"
    assert "deviations.md" in read(PLAN), "the plan no longer cites the deviations register"


@pytest.mark.parametrize("claim, why", [
    ("the detectors are **complementary**",
     "withdrawn: signature_only = 0 on corrected data (deviations E1)"),
    ("occupy review-queue positions 1–8",
     "unsatisfiable: no signature_override alert exists (deviations E3)"),
    ("AL-0509",
     "an id from the frozen uncorrected fixture, in a precondition that has triggered "
     "(deviations E4)"),
])
def test_the_plan_no_longer_asserts_a_withdrawn_claim(claim, why):
    """Each of these survived in the plan for eleven changelog versions. If one comes back, it is
    because a correction was reverted without reading why it was made."""
    for line in read(PLAN).splitlines():
        if claim not in line:
            continue
        # A withdrawn claim may be *quoted* inside a correction note; it may not be asserted.
        assert any(marker in line for marker in
                   ("v1.1 CORRECTION", "v1.1 CHANGE", "WITHDRAWN", "~~", "had listed", "It said",
                    "v1.0 would", "v1.1:")), f"the plan still asserts: {claim!r} — {why}"
