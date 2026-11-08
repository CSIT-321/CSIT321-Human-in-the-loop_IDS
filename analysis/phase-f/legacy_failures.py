"""List every distinct failing browser test across batch-run logs, with its first error line. Read-only.
Usage: python legacy_failures.py <log-dir> [<log-dir> ...]"""
import re
import sys
from pathlib import Path

seen = {}
for d in sys.argv[1:]:
    for log in sorted(Path(d).glob('*.log')):
        text = log.read_text(encoding='utf-8', errors='replace')
        for block in re.split(r'\n(?=  \d+\) \[chromium\])', text)[1:]:
            head = re.match(r'  \d+\) \[chromium\] › (\S+:\d+):\d+ › (.*?)(?: ─|\n)', block)
            if not head:
                continue
            err = next((ln.strip() for ln in block.splitlines()
                        if re.search(r'Locator:|Error:|> +\d+ \|', ln) and 'test-results' not in ln), '')
            key = head.group(1)
            seen.setdefault(key, [head.group(2)[:90], err[:170], set()])[2].add(log.stem)
for key, (title, err, configs) in sorted(seen.items()):
    print(f'{key:44} [{",".join(sorted(configs))}]\n    {title}\n    {err}')
print(len(seen), 'distinct failing tests')
