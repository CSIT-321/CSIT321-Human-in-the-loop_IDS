"""Request plumbing for the demo API (plan step S10b): a connection, a role, and one error shape.

**The role check is a stub, and it is named to look like one.** `X-Demo-Role` is trusted exactly as
the client sends it. That is D3's deliberate choice — real JWT/bcrypt with RBAC is S18 — and the
dependency is called ``demo_role_stub`` so nobody mistakes it for authentication during a review.
What it *does* enforce is the shape of the rule, so S18 replaces the principal and not the call
sites.

**One connection per request, closed afterwards.** SQLite is a file, the demo is single-user, and a
pool would be machinery for a problem that does not exist yet.

**Every failure leaves through ``ApiError``**, so the wire carries one error envelope and a client
has one error path.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any, get_args

from fastapi import Depends, Header, HTTPException, Request

from apps.api.contract.common import ROLE_HEADER, ErrorBody, ErrorResponse
from packages.contracts import db
from packages.contracts import models as m

HITL = Path(__file__).resolve().parents[2]

#: Where the demo database lives. Overridable so tests and a packaged demo can point elsewhere.
DB_ENV_VAR = "HITL_IDS_DB"
DEFAULT_DB = HITL / "data" / "demo.db"

ROLES: tuple[str, ...] = get_args(m.Role)


def database_path() -> Path:
    return Path(os.environ.get(DB_ENV_VAR) or DEFAULT_DB)


class ApiError(HTTPException):
    """An error with a stable code. The handler renders it as the contract's envelope."""

    def __init__(self, status_code: int, code: str, message: str,
                 detail: dict[str, Any] | None = None) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.context = detail

    def body(self) -> dict[str, Any]:
        return ErrorResponse(
            error=ErrorBody(code=self.code, message=self.message, detail=self.context)
        ).model_dump(by_alias=True, exclude_none=True)


def not_found(what: str, ref: object) -> ApiError:
    return ApiError(404, "NOT_FOUND", f"No {what} with reference {ref}")


def get_connection(request: Request) -> Iterator[sqlite3.Connection]:
    """One connection per request.

    A missing database is a 503 carrying the command that fixes it, not a stack trace: on a fresh
    checkout the demo database is gitignored and has to be built, which is much the most likely
    reason for this to fail.
    """
    path = getattr(request.app.state, "database_path", None) or database_path()
    if not Path(path).exists():
        raise ApiError(
            503, "DATABASE_MISSING",
            f"No detection database at {path}. Build it with: python scripts/run_detection.py")
    connection = db.connect(str(path))
    try:
        yield connection
    finally:
        connection.close()


def demo_role_stub(role: str | None = Header(default=None, alias=ROLE_HEADER)) -> str:
    """The caller's claimed role. **Trusted, not verified** — S18 replaces this wholesale.

    Defaults to `security_analyst`, so the demo's main path needs no header at all. An unrecognised
    role is refused rather than silently downgraded: a typo that quietly grants analyst access is
    exactly the sort of thing nobody notices.
    """
    if role is None:
        return "security_analyst"
    if role not in ROLES:
        raise ApiError(400, "VALIDATION_FAILED", f"Unknown role {role!r}",
                       {"header": ROLE_HEADER, "allowed": list(ROLES)})
    return role


def require_role(*allowed: str):
    """Dependency factory: refuse a caller whose stubbed role is not in ``allowed``.

    Used only where a role genuinely gates an action. Sprinkling it everywhere would imply an
    access-control model the demo does not have.
    """

    def check(role: str = Depends(demo_role_stub)) -> str:
        if role not in allowed:
            raise ApiError(
                403, "FORBIDDEN_ROLE",
                f"This action requires the {' or '.join(allowed)} role",
                {"role": role, "required": list(allowed)})
        return role

    return check
