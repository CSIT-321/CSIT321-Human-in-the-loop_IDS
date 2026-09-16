#!/usr/bin/env python3
"""Render the Preliminary User Manual to HTML for the published Pages site.

The manual's source of truth is ``docs/preliminary-user-manual.md`` — the same file
``scripts/build_user_manual.py`` renders to .docx. This renders the same Markdown to a web page,
so the published manual can never drift from the submitted document: both are generated from one
source, and neither is edited by hand.

    python site/build_manual.py [--source docs/preliminary-user-manual.md] [--out _site/user-manual.html]

The page is written beside the site's copied ``img/`` directory, because the Markdown references
its screenshots as ``img/demo-guide/*.png`` relative to itself.
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                      # hitl-ids/
DEFAULT_SOURCE = ROOT / "docs" / "preliminary-user-manual.md"
DEFAULT_OUT = ROOT / "_site" / "user-manual.html"

# The console's own tokens (apps/web/src/index.css), so the published manual reads as part of the
# product rather than as a generic converted document.
SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
  :root{{
    --bg:#0b0d10; --surface:#111418; --raised:#171b21;
    --border:#242a33; --border-strong:#333b47;
    --text:#e6e8eb; --muted:#8f97a3; --dim:#656d79;
    --accent:#58a6ff; --primary:#2f81f7; --danger:#f85149;
    --mono:"JetBrains Mono",ui-monospace,monospace;
    --sans:"IBM Plex Sans","Segoe UI",system-ui,sans-serif;
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--text);font-family:var(--sans);
        font-size:15px;line-height:1.68;-webkit-font-smoothing:antialiased}}
  .wrap{{max-width:860px;margin:0 auto;padding-block:0 80px;padding-inline:20px}}
  .back{{display:inline-block;margin-top:26px;font-family:var(--mono);font-size:12px;
         color:var(--dim);text-decoration:none}}
  .back:hover{{color:var(--accent)}}
  h1{{font-size:32px;line-height:1.2;margin:18px 0 8px;font-weight:600;letter-spacing:-.01em}}
  h2{{font-size:21px;margin:40px 0 10px;padding-top:18px;border-top:1px solid var(--border);
      font-weight:600}}
  h3{{font-size:16px;margin:26px 0 8px;font-weight:600}}
  h4{{font-size:14px;margin:20px 0 6px;font-weight:600;color:var(--muted)}}
  p,li{{max-width:74ch}}
  a{{color:var(--accent)}}
  code{{font-family:var(--mono);font-size:12.5px;background:var(--raised);
        border:1px solid var(--border);padding:1px 5px;border-radius:2px}}
  pre{{background:var(--surface);border:1px solid var(--border);border-left:2px solid var(--primary);
       padding:13px 16px;overflow-x:auto;font-size:12.5px;line-height:1.6}}
  pre code{{background:none;border:0;padding:0}}
  blockquote{{margin:16px 0;padding:12px 16px;background:var(--surface);
              border-left:2px solid var(--accent);color:var(--muted)}}
  blockquote p{{margin:0}}
  table{{border-collapse:collapse;width:100%;font-size:13.5px;margin:14px 0}}
  th,td{{text-align:left;padding:8px 12px;border:1px solid var(--border);vertical-align:top}}
  th{{background:var(--raised);font-family:var(--mono);font-size:11px;letter-spacing:.06em;
      text-transform:uppercase;color:var(--muted);font-weight:500}}
  img{{max-width:100%;height:auto;border:1px solid var(--border);margin:12px 0;display:block}}
  hr{{border:0;border-top:1px solid var(--border);margin:34px 0}}
  footer{{margin-top:48px;padding-top:18px;border-top:1px solid var(--border);
          color:var(--dim);font-size:12.5px;font-family:var(--mono)}}
  @media (max-width:600px){{ h1{{font-size:25px}} .wrap{{padding-inline:16px}} }}
</style>
</head>
<body><div class="wrap">
<a class="back" href="index.html">&#8592; Project pages</a>
{body}
<footer>Generated from <code>docs/preliminary-user-manual.md</code> at build time &mdash;
the same source the submitted .docx is rendered from, so the two cannot drift.</footer>
</div></body>
</html>
"""


def title_of(markdown_text: str, fallback: str) -> str:
    """The document's own first heading, so the tab matches the file rather than the filename."""
    found = re.search(r"^#\s+(.+)$", markdown_text, re.MULTILINE)
    return html.escape(found.group(1).strip()) if found else fallback


def render(source: Path, out: Path) -> None:
    if not source.exists():
        raise SystemExit(f"missing {source}")
    text = source.read_text(encoding="utf-8")
    body = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "attr_list", "sane_lists", "toc"],
        extension_configs={"toc": {"permalink": False}},
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        SHELL.format(title=title_of(text, "Preliminary User Manual"), body=body),
        encoding="utf-8",
    )
    print(f"wrote {out} ({len(body):,} bytes of body)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    render(args.source, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
