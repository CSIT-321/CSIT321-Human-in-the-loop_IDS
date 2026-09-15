"""Sign-in wire shapes (S18a): the request the login form sends, and what comes back.

The role is **not** a field the client picks. It travels inside the token, minted from the
account's row, so a client cannot ask to be the admin — only sign in as the admin.
"""

from __future__ import annotations

from pydantic import Field

from apps.api.contract.common import ApiModel
from packages.contracts import models as m


class LoginRequest(ApiModel):
    """What the sign-in form sends. A wrong username and a wrong password answer identically."""

    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(ApiModel):
    """The signed token plus the account it names. The console stores this as its session."""

    token: str = Field(description="JWT bearer token; send as `Authorization: Bearer <token>`. "
                                    "Valid for 8 hours.")
    username: str
    display_name: str
    role: m.Role


class MeResponse(ApiModel):
    """Who the token says is calling — the session check for `GET /api/auth/me`."""

    username: str
    display_name: str
    role: m.Role
