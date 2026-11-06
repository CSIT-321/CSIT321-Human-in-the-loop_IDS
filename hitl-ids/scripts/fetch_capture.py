"""Fetch CSE-CIC-IDS2018 packet captures from the public AWS bucket, by member, with HTTP range reads.

The day archives are 36-55 GiB. A zip keeps its directory at the end, so this script reads only the
directory, lists the members, and downloads just the members asked for. Every byte is checked against
the archive's own CRC-32. Nothing here needs AWS credentials.

    python scripts/fetch_capture.py --day Wednesday-14-02-2018 --list
    python scripts/fetch_capture.py --day Wednesday-14-02-2018 --member <name> [--member <name> ...]
    python scripts/fetch_capture.py --day Wednesday-14-02-2018 --all

Output: data/raw/pcap/<day>/<member path>. That folder is gitignored.
"""
from __future__ import annotations

import argparse
import io
import sys
import urllib.parse
import urllib.request
import zipfile
import zlib
from pathlib import Path

BUCKET = "https://cse-cic-ids2018.s3.ca-central-1.amazonaws.com/"
PREFIX = "Original Network Traffic and Log data/"
OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "pcap"
CHUNK = 8 * 1024 * 1024


class HttpRangeFile(io.RawIOBase):
    """A read-only, seekable file over HTTP range requests (enough for zipfile)."""

    def __init__(self, url: str):
        self.url = url
        head = urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60)
        self.size = int(head.headers["Content-Length"])
        self.pos = 0

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def read(self, n: int = -1) -> bytes:
        if self.pos >= self.size:
            return b""
        end = self.size - 1 if n is None or n < 0 else min(self.size - 1, self.pos + n - 1)
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        data = urllib.request.urlopen(req, timeout=120).read()
        self.pos += len(data)
        return data

    def readinto(self, b) -> int:
        data = self.read(len(b))
        b[: len(data)] = data
        return len(data)


def archive_url(day: str) -> str:
    for name in ("pcap.zip", "pcap.rar"):
        url = BUCKET + urllib.parse.quote(PREFIX + f"{day}/{name}")
        try:
            urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60)
            if name.endswith(".rar"):
                sys.exit(f"{day} is a RAR archive; member download needs a zip. Download it whole: {url}")
            return url
        except urllib.error.HTTPError:
            continue
    sys.exit(f"no archive for {day}")


def fetch(zf: zipfile.ZipFile, info: zipfile.ZipInfo, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size == info.file_size:
        print(f"present  {info.filename} ({info.file_size:,} B)")
        return
    part = dest.with_suffix(dest.suffix + ".part")
    crc, done = 0, 0
    with zf.open(info) as src, part.open("wb") as out:
        while chunk := src.read(CHUNK):
            out.write(chunk)
            crc = zlib.crc32(chunk, crc)
            done += len(chunk)
            print(f"\r{info.filename}: {done / info.file_size:6.1%}", end="", flush=True)
    print()
    if crc != info.CRC or done != info.file_size:
        part.unlink()
        sys.exit(f"CRC/size mismatch on {info.filename}")
    part.replace(dest)
    print(f"verified {info.filename} ({done:,} B, CRC {crc:08x})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", required=True, help="e.g. Wednesday-14-02-2018")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--member", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    remote = HttpRangeFile(archive_url(args.day))
    zf = zipfile.ZipFile(io.BufferedReader(remote, buffer_size=CHUNK))
    members = [i for i in zf.infolist() if not i.is_dir()]
    if args.list or not (args.member or args.all):
        print(f"{args.day}: {len(members)} members, archive {remote.size:,} B")
        for i in members:
            print(f"{i.file_size:>15,}  {i.compress_size:>15,}  {i.filename}")
        return
    wanted = members if args.all else [i for i in members if i.filename in set(args.member)]
    missing = set(args.member) - {i.filename for i in wanted}
    if missing:
        sys.exit(f"not in archive: {sorted(missing)}")
    for info in wanted:
        fetch(zf, info, OUT / args.day / info.filename)


if __name__ == "__main__":
    main()
