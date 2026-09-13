"""Serve the demo API over a disposable copy of the demo database (plan step S16).

    python scripts/serve_rehearsal.py --port 8001

The browser end-to-end run (`apps/web/e2e/`) records real verdicts, and verdicts are permanent: the
audit trail refuses UPDATE and DELETE. Pointing that run at `data/demo.db` would hand the next audience
a queue that has already been judged. This copies the database into a temporary folder first and
serves the copy, so every rehearsal starts from the state detection left.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

HITL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HITL))

import uvicorn  # noqa: E402

from apps.api.main import create_app  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", type=Path, default=HITL / "data" / "demo.db")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    if not args.database.exists():
        print(f"No database at {args.database}. Build it with: python scripts/run_detection.py")
        return 2

    copy = Path(tempfile.mkdtemp(prefix="hitl-e2e-")) / "rehearsal.db"
    shutil.copy2(args.database, copy)
    print(f"Serving a disposable copy: {copy}", flush=True)
    uvicorn.run(create_app(copy), host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
