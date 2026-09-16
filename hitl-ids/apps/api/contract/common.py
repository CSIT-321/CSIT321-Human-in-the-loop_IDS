"""Shared wire shapes for the demo API (plan step S10a).

**S10a is the contract, not the service.** Nothing here imports FastAPI — the models and the
OpenAPI document are pure Pydantic, so the contract can be written, reviewed and tested before
`fastapi` is even installed, and S11 can generate its typed client from it while S10b's handlers
are still being written. That is the whole point of the v0.3 split.

**camelCase on the wire, snake_case in Python.** The consumer is a generated TypeScript client, and
this repository already uses camelCase at every boundary it shares with JavaScript
(``ProducerContract``, the signature engine's observable view). Serialise with ``by_alias=True``.

**Two things the API must never do**, both of which the rest of the system is careful about:

* **Never expose a row id as an identifier.** The public identity of an alert is its ``alertRef``
  UUID. Integer ids leak row counts, and S18's Postgres migration is free to renumber them.
* **Never expose ground truth.** It is not in the schema at all (`deviations.md` A7); the only
  component allowed to know the answers is the evaluation, and it reaches them by one join.
"""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from packages.contracts import db
from packages.contracts import models as m

#: The queue's order is the contract's, cited rather than restated. Ordering by anything else —
#: `evidence_priority`, say, as plan v1.0 wrongly specified — hides the re-ranking that feedback
#: performs, which is the one thing the demo exists to show (`deviations.md` C13).
QUEUE_ORDER = db.QUEUE_ORDER_BY

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


class ApiModel(BaseModel):
    """Base for every request and response body on the wire."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        alias_generator=to_camel,
        populate_by_name=True,
    )


ItemT = TypeVar("ItemT")


class PageInfo(ApiModel):
    """Where in the queue this page sits.

    Offset paging, deliberately: the queue is a ranked list an analyst works down, so a cursor
    would buy nothing and cost the ability to jump to a position.
    """

    total: int = Field(ge=0, description="Total items matching the filters, before paging")
    limit: int = Field(ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(ge=0)
    returned: int = Field(ge=0, description="Items in this response")


class Page(ApiModel, Generic[ItemT]):
    """A page of results plus its position. Every list endpoint returns this envelope."""

    items: list[ItemT]
    page: PageInfo


class ErrorBody(ApiModel):
    """The body of every non-2xx response. One shape, so a client has one error path."""

    code: str = Field(min_length=1, description="Stable machine-readable code, e.g. NOT_FOUND")
    message: str = Field(min_length=1, description="Human-readable, safe to display")
    detail: dict[str, Any] | None = Field(
        default=None, description="Field-level context; never internal ids or SQL")


class ErrorResponse(ApiModel):
    error: ErrorBody


#: The codes the demo path can return. A client switches on these, never on the message.
ErrorCode = Literal[
    "UNAUTHORIZED",
    "NOT_FOUND",
    "VALIDATION_FAILED",
    "FORBIDDEN_ROLE",
    "GUARDRAIL_REJECTED",
    "CONFLICT",
    "RUN_IN_PROGRESS",
]


class Actor(ApiModel):
    """Who did something. Since S18a these are the real seeded accounts, not stub role-holders."""

    user_id: int | None = Field(default=None, description="Internal id; null for system actions")
    display_name: str | None = None
    role: m.Role | None = None


# --------------------------------------------------------------------------------------------
# Query parameters. Modelled rather than left to the handlers, because S11 generates its client
# from these and because "sort" and "filter" are where an API quietly grows a second ranking.
# --------------------------------------------------------------------------------------------

#: What a client may sort the queue by. `queue` is the contract order and the default; the others
#: exist because an analyst checking a specific claim needs them. **`queue` is what the demo
#: shows** — the rest are inspection tools, not alternative rankings.
#:
#: `evidence` is the one that earns its place. When a detector's false positives carry an attack's
#: full confidence, no score-based key can separate them and only the rule layer can; measured on
#: `data/stress.db`, evidence-first reaches precision@100 1.000 where the contract order reaches
#: 0.000. It is offered rather than imposed, because the default should lead with urgency.
QueueSort = Literal["queue", "combined_score", "detection_score", "created_at", "severity",
                    "evidence"]

SortDirection = Literal["asc", "desc"]

#: `me` — alerts owned by the caller's demo user; `unassigned` — alerts nobody owns.
QueueOwner = Literal["me", "unassigned"]

#: A flow capture time as the dataset records it (capture-local, no timezone): a date, optionally
#: with hours, minutes, seconds and microseconds. Compared as text, so text order is time order.
FLOW_TIME_PATTERN = r"^\d{4}-\d{2}-\d{2}( \d{2}(:\d{2}(:\d{2}(\.\d{1,6})?)?)?)?$"


class QueueQuery(ApiModel):
    """Query parameters for ``GET /api/alerts``."""

    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(default=0, ge=0)
    sort: QueueSort = Field(default="queue",
                            description=f"Default `queue` is the contract order: {QUEUE_ORDER}")
    direction: SortDirection = "desc"
    queue_class: list[m.QueueClass] | None = Field(
        default=None, description="Filter to these queue bands")
    evidence_class: list[m.EvidenceClass] | None = Field(
        default=None, description="Filter to these evidence classes. Reported, never sorted on")
    severity: list[m.Severity] | None = None
    status: list[m.AlertStatus] | None = None
    attack_category: list[m.AttackClass] | None = None
    requires_review: bool | None = None
    min_score: m.Score | None = Field(default=None, description="On combined_score")
    max_score: m.Score | None = None
    detection_min_score: m.Score | None = Field(
        default=None,
        description="On detection_score, the immutable column. With evidence filters, "
        "`detectionMaxScore=99.999` isolates flagged alerts a confirming verdict can still "
        "visibly raise — 975 of the 996 flagged alerts sit at exactly 100.0, and the rest are "
        "all below 99.999")
    detection_max_score: m.Score | None = None
    search: str | None = Field(
        default=None, max_length=200,
        description="Substring of source IP, destination IP, or matched rule id")
    run_id: int | None = Field(default=None, description="Restrict to one detection run")
    verdict: list[m.FeedbackCategory] | None = Field(
        default=None, description="Filter by the verdict currently in force")
    unjudged: bool | None = Field(
        default=None,
        description="`true`: only alerts with no verdict recorded at all — the complement of the "
        "`verdict` filter, which asks about the verdict currently in force. The queue row's "
        "`hasFeedback` reports the same condition, so a filter and its row pill never disagree")
    owner: QueueOwner | None = Field(
        default=None, description="`me`: owned by the caller's demo user; `unassigned`: no owner")
    flow_from: str | None = Field(
        default=None, pattern=FLOW_TIME_PATTERN,
        description="Earliest flow capture time, capture-local, e.g. 2018-02-14 12:00")
    flow_to: str | None = Field(
        default=None, pattern=FLOW_TIME_PATTERN,
        description="Latest flow capture time; a date alone means the end of that day")
