"""
Publish the demo API's OpenAPI document (plan step S10a).

    python scripts/build_openapi.py            # write apps/api/openapi.json
    python scripts/build_openapi.py --check    # fail if the committed file is out of date
    python scripts/build_openapi.py --print    # write nothing, print the document

The document is **committed**, because S11 generates its typed client from it and a generated
client must be reproducible from a checkout without running Python. `--check` is what keeps the
committed copy honest; `tests/test_api_contract.py` runs the same comparison.

Output: apps/api/openapi.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HITL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HITL))

from apps.api.contract.openapi import openapi_document  # noqa: E402

TARGET = HITL / "apps" / "api" / "openapi.json"


def rendered() -> str:
    """The document as it must appear on disk. One definition, so the writer and the check agree."""
    return json.dumps(openapi_document(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if the committed document differs from the models")
    parser.add_argument("--print", dest="show", action="store_true", help="print, write nothing")
    parser.add_argument("--output", default=str(TARGET))
    args = parser.parse_args()

    document = rendered()
    if args.show:
        print(document, end="")
        return 0

    target = Path(args.output)
    if args.check:
        if not target.exists():
            print(f"{target} has never been built - run: python scripts/build_openapi.py",
                  file=sys.stderr)
            return 1
        if target.read_text(encoding="utf-8") != document:
            print(f"{target} is out of date with the contract models - "
                  f"run: python scripts/build_openapi.py", file=sys.stderr)
            return 1
        print(f"{target} is up to date")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8")
    parsed = json.loads(document)
    operations = sum(len(methods) for methods in parsed["paths"].values())
    print(f"wrote {target}")
    print(f"  {len(parsed['paths'])} paths, {operations} operations, "
          f"{len(parsed['components']['schemas'])} schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
