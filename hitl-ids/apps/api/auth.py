"""Real sign-in for the demo API (S18a): bcrypt passwords, JWT bearers, role checks.

This replaces the S10 role-switch stub (``X-Demo-Role`` trusted as sent). The demo now has three
accounts, one per role, and the role travels **inside** a signed token: a client can no longer
claim to be the admin by writing a header. What S10 deliberately kept — one ``ApiError`` envelope,
a ``require_role`` factory, dependency-shaped call sites — is kept here unchanged, per the plan's
"replace the principal, not the call sites".

**The accounts are seeded, idempotently, on first sign-in.** Fresh databases, old databases that
predate the stub's lazy ``demo-{role}`` users, and the disposable rehearsal copies all self-heal —
the same philosophy as ``db.migrate`` in ``get_connection``. The usernames and passwords are
committed on purpose: this is an offline demo, and a secret that cannot be looked up would only
cost presentation time. ``users.last_login`` records each successful sign-in.

**The signing key** comes from ``HITL_IDS_JWT_SECRET`` when set; the committed default exists so a
fresh checkout runs. Tokens live eight hours, long enough for a presentation, short enough that a
token leaked into a screenshot is a bounded problem.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import timedelta

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.api.deps import ApiError, get_connection
from packages.contracts import db
from packages.contracts import models as m

#: Override for real deployments; the default is committed so a fresh checkout just works.
SECRET_ENV_VAR = "HITL_IDS_JWT_SECRET"
DEV_SECRET = "hitl-ids-demo-secret-not-for-production"

#: How long a sign-in lasts. A demo presentation is an hour; a working session is an afternoon.
TOKEN_HOURS = 8

_ALGORITHM = "HS256"

#: (username, password, display_name, role, email). One account per role: the console's three
#: views are three people, not one person switching hats.
DEMO_ACCOUNTS: tuple[tuple[str, str, str, str, str], ...] = (
    ("g.ang", "analyst-demo", "Glenn Ang", "security_analyst", "g.ang@demo.local"),
    ("admin", "admin-demo", "System Administrator", "system_admin", "admin@demo.local"),
    ("evaluator", "evaluator-demo", "Evaluator", "evaluator", "evaluator@demo.local"),
)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    """ bcrypt refuses passwords longer than 72 bytes rather than truncating; that refusal is a
    wrong answer here, not an error."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


#: The demo passwords are constants, so their hashes are computed once per process. Three bcrypt
#: operations per test database would otherwise add the better part of a second to every test.
_HASH_CACHE: dict[str, str] = {}


def _seed_hash(password: str) -> str:
    if password not in _HASH_CACHE:
        _HASH_CACHE[password] = hash_password(password)
    return _HASH_CACHE[password]


#: Verified against when the username does not exist, so "no such user" and "wrong password" take
#: the same time and the failure message can stay honestly vague.
_DUMMY_HASH = hash_password("not-any-account's-password")


@dataclass(frozen=True)
class Principal:
    """The signed-in account, as the handlers see it.

    ``user_id`` is internal: it keys ``feedback_events`` and ``audit_log``, and never appears on
    the wire (the contract's rule is alertRef-style public ids, and S18's Postgres migration is
    free to renumber these).
    """

    user_id: int
    username: str
    display_name: str
    role: str


def ensure_demo_accounts(conn: sqlite3.Connection) -> None:
    """Create any of the three demo accounts that are missing. Idempotent and cheap when current:
    one SELECT of three usernames."""
    usernames = [account[0] for account in DEMO_ACCOUNTS]
    placeholders = ", ".join("?" * len(usernames))
    present = {row["username"] for row in
               conn.execute(f"SELECT username FROM users WHERE username IN ({placeholders})",
                            usernames)}
    missing = [account for account in DEMO_ACCOUNTS if account[0] not in present]
    if not missing:
        return
    with conn:
        for username, password, display_name, role, email in missing:
            db.insert(conn, m.User(username=username, password_hash=_seed_hash(password),
                                   display_name=display_name, email=email, role=role))


def authenticate(conn: sqlite3.Connection, username: str, password: str) -> m.User | None:
    """The whole credential check in one place: seed, fetch, verify. ``None`` means refused — the
    caller raises one 401 for a wrong username, a wrong password and a disabled account alike, so
    the answer leaks which of the three it was to nobody."""
    ensure_demo_accounts(conn)
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    user = db.from_row(m.User, row) if row is not None else None
    hashed = user.password_hash if user is not None else _DUMMY_HASH
    if user is None or not verify_password(password, hashed) or user.status != "active":
        return None
    return user


def encode_token(user: m.User) -> str:
    now = m.utc_now()
    return jwt.encode(
        {"sub": str(user.id), "username": user.username, "role": user.role,
         "iat": int(now.timestamp()), "exp": int((now + timedelta(hours=TOKEN_HOURS)).timestamp())},
        os.environ.get(SECRET_ENV_VAR) or DEV_SECRET,
        algorithm=_ALGORITHM,
    )


def _decode(token: str) -> dict[str, str]:
    return jwt.decode(token, os.environ.get(SECRET_ENV_VAR) or DEV_SECRET,
                      algorithms=[_ALGORITHM])


def _unauthorized(message: str, detail: dict[str, str] | None = None) -> ApiError:
    return ApiError(401, "UNAUTHORIZED", message, detail)


_bearer = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    conn: sqlite3.Connection = Depends(get_connection),
) -> Principal:
    """The signed-in account. Every protected handler depends on this, directly or through
    ``require_role``: no token, a forged token, an expired token or a disabled account all leave
    through the same 401 envelope."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Sign in first: POST /api/auth/login", {"scheme": "Bearer"})
    try:
        payload = _decode(credentials.credentials)
    except jwt.ExpiredSignatureError as error:
        raise _unauthorized("The sign-in expired. Sign in again.") from error
    except jwt.InvalidTokenError as error:
        raise _unauthorized("That token is not valid.") from error
    row = conn.execute("SELECT * FROM users WHERE id = ?", (int(payload["sub"]),)).fetchone()
    if row is None:
        raise _unauthorized("That account no longer exists.")
    user = db.from_row(m.User, row)
    if user.status != "active":
        raise _unauthorized(f"Account {user.username} is {user.status}.")
    return Principal(user_id=user.id or 0, username=user.username,
                     display_name=user.display_name, role=user.role)


def require_role(*allowed: str):
    """Dependency factory: refuse a caller whose account role is not in ``allowed``.

    Used only where a role genuinely gates an action, as before — sprinkling it everywhere would
    imply an access-control model finer than the demo has.
    """

    def check(principal: Principal = Depends(current_user)) -> Principal:
        if principal.role not in allowed:
            raise ApiError(
                403, "FORBIDDEN_ROLE",
                f"This action requires the {' or '.join(allowed)} role",
                {"role": principal.role, "required": list(allowed)})
        return principal

    return check
