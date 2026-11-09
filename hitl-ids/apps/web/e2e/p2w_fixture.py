"""Serve one walkthrough database read-only on a chosen port. Product code unchanged.

Usage: python p2w_fixture.py <db-path> <port>
The API is the real app (apps.api.main.create_app). The page under test only reads, so the database
is opened normally but nothing in this script writes to it.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT)]
import uvicorn  # noqa: E402
from apps.api.main import create_app  # noqa: E402

if __name__ == "__main__":
    database, port = Path(sys.argv[1]), int(sys.argv[2])
    if not database.exists():
        raise SystemExit(f"database not found: {database}")
    print(f"serving {database} on 127.0.0.1:{port}", flush=True)
    uvicorn.run(create_app(database), host="127.0.0.1", port=port, log_level="warning")
