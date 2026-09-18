#!/usr/bin/env python3
"""Assemble and (optionally) serve the project's published pages.

This is the **single source of truth** for how the site is built. The Pages workflow runs the same
script with ``--check``, so what you preview locally is byte-for-byte what gets published — the two
cannot drift, because there is only one implementation.

    python site/build_site.py                 # build into hitl-ids/_site
    python site/build_site.py --serve         # build, then serve on http://127.0.0.1:8080
    python site/build_site.py --check         # build, then fail if any local link is broken

``--check`` exists because a broken link has already happened once: the manual referenced a
wireframe image that the first version of the workflow did not copy, and it would have shipped
broken. The check makes that a build failure instead of a surprise on the live site.

Only these pages are published:

    index.html          the landing page                site/index.html
    showcase.html       the console walkthrough         docs/ids-console-showcase.html
    pipeline-map.html   the detection pipeline          docs/pipeline-map.html
    user-manual.html    the user manual, rendered       docs/preliminary-user-manual.md

The repository's internal records — HANDOVER.md, the plan changelog, the deviations register — are
deliberately **not** copied. They belong in the repo, not on a public page.
"""

from __future__ import annotations

import argparse
import http.server
import re
import shutil
import socketserver
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                       # hitl-ids/
DOCS = ROOT / "docs"
OUT = ROOT / "_site"

#: source -> published name. Adding a page is a one-line change here.
PAGES = {
    HERE / "index.html": "index.html",
    DOCS / "ids-console-showcase.html": "showcase.html",
    DOCS / "pipeline-map.html": "pipeline-map.html",
}
#: asset directories the copied pages reference relatively.
ASSETS = ("demo-guide", "wireframes")
#: generated, not copied — see site/build_manual.py.
MANUAL_SOURCE = DOCS / "preliminary-user-manual.md"
MANUAL_PAGE = "user-manual.html"


def build(out: Path) -> list[str]:
    """Write the site into ``out``. Returns the list of pages written."""
    if out.exists():
        shutil.rmtree(out)
    (out / "img").mkdir(parents=True)

    written: list[str] = []
    for source, name in PAGES.items():
        if not source.exists():
            raise SystemExit(f"missing source page: {source}")
        shutil.copy2(source, out / name)
        written.append(name)

    for asset in ASSETS:
        src = DOCS / "img" / asset
        if not src.is_dir():
            raise SystemExit(f"missing asset directory: {src}")
        shutil.copytree(src, out / "img" / asset)
        written.append(f"img/{asset}/")

    # Imported here so `--help` works without the markdown package installed.
    sys.path.insert(0, str(HERE))
    import build_manual  # noqa: PLC0415
    build_manual.render(MANUAL_SOURCE, out / MANUAL_PAGE)
    written.append(MANUAL_PAGE)
    return written


def check(out: Path) -> list[str]:
    """Problems with the built pages: broken local refs, and missing encoding declarations.

    Both have shipped before. A broken image reached the first version of this build; and both the
    showcase and the pipeline map were written as Artifacts, which inject ``<meta charset>`` for
    them — served as ordinary files they had none, so a browser decoded them as cp1252 and every
    em-dash, multiplication sign and "&#8805;" rendered as mojibake. The declaration has to sit in
    the first 1024 bytes to be honoured, so it is checked there rather than anywhere in the file.
    """
    problems: list[str] = []
    for page in sorted(out.glob("*.html")):
        text = page.read_text(encoding="utf-8")
        for ref in re.findall(r'(?:src|href)="([^"#][^"]*)"', text):
            if ref.startswith(("http://", "https://", "mailto:", "data:", "//")):
                continue
            target = (out / ref.split("?")[0].split("#")[0]).resolve()
            if not target.exists():
                problems.append(f"{page.name} -> broken reference: {ref}")
        if not re.search(r'<meta[^>]+charset\s*=\s*["\']?utf-8', text[:1024], re.I):
            problems.append(f'{page.name} -> no <meta charset="utf-8"> in the first 1 KB')
    return problems


def serve(out: Path, port: int) -> None:
    def handler(*args, **kwargs):
        return http.server.SimpleHTTPRequestHandler(*args, directory=str(out), **kwargs)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        print(f"\n  serving {out}")
        print(f"  http://127.0.0.1:{port}/\n")
        print("  Ctrl+C to stop. Re-run this command after editing a page.\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  stopped.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT, help="build directory (default: %(default)s)")
    parser.add_argument("--serve", action="store_true", help="serve after building")
    parser.add_argument("--port", type=int, default=8080, help="port for --serve (default: %(default)s)")
    parser.add_argument("--check", action="store_true",
                        help="fail the build if any local link is broken")
    args = parser.parse_args()

    written = build(args.out)
    print(f"built {len(written)} entries into {args.out}")
    for name in written:
        print(f"  {name}")

    if args.check:
        problems = check(args.out)
        if problems:
            print(f"\nFAIL: {len(problems)} problem(s) with the built pages", file=sys.stderr)
            for item in problems:
                print(f"  {item}", file=sys.stderr)
            return 1
        print("\nOK: every local reference resolves, and every page declares UTF-8")

    if args.serve:
        serve(args.out, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
