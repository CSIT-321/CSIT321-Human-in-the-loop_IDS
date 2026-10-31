"""Shared non-migrating connection and JWT principal for inspection endpoints."""
import sqlite3
from typing import Annotated
from fastapi import Depends
from apps.api import auth
from apps.api.deps import get_readonly_connection

ReadConn = Annotated[sqlite3.Connection, Depends(get_readonly_connection)]
ReadPrincipal = Annotated[auth.Principal, Depends(auth.current_readonly_user)]
