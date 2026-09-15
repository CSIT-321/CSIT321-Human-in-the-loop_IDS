"""Request plumbing for the demo API (plan step S10b): a connection and one error shape.

The principal — who is calling — lives in ``apps.api.auth`` (S18a: a real signed account). What
this module owns is the request's connection and the one error envelope every failure leaves
through, so the wire carries one error shape and a client has one error path.

**One connection per request, closed afterwards.** SQLite is a file, the demo is single-user, and a
pool would be machinery for a problem that does not exist yet.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from apps.api.contract.common import ErrorBody, ErrorResponse
from packages.contracts import db

HITL = Path(__file__).resolve().parents[2]

#: Where the demo database lives. Overridable so tests and a packaged demo can point elsewhere.
DB_ENV_VAR = "HITL_IDS_DB"
DEFAULT_DB = HITL / "data" / "demo.db"


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
    # FastAPI runs this generator and the handler in its threadpool, on whichever worker threads are
    # free — so under concurrent requests (a browser opening an alert fires three reads at once) the
    # connection is created on one thread and used on another. SQLite's default same-thread check then
    # fails the request with a 500. Safe to lift: the connection belongs to one request and is never
    # used by two threads at once. Found by the browser end-to-end run, not by sequential tests.
    connection = db.connect(str(path), check_same_thread=False)
    # A demo database built before a migration existed is upgraded on first use. Cheap when current:
    # one PRAGMA read.
    db.migrate(connection)
    try:
        yield connection
    finally:
        connection.close()
