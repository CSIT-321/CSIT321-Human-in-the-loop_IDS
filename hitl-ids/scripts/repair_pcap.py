"""Copy a classic libpcap file, dropping records whose header is impossible, so readers do not stop early.

Some CSE-CIC-IDS2018 captures contain a damaged record (e.g. caplen 37,496,642 > snaplen 65,535). libpcap
readers (Suricata, CICFlowMeter's jnetpcap) stop at it, losing the rest of the file. This tool resynchronises
by scanning forward for the next plausible record header. Reports how many records and bytes were dropped.

    python scripts/repair_pcap.py <in.pcap> <out.pcap>
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

MAGICS = {b"\xd4\xc3\xb2\xa1": "<", b"\xa1\xb2\xc3\xd4": ">", b"\x4d\x3c\xb2\xa1": "<", b"\xa1\xb2\x3c\x4d": ">"}


def plausible(hdr: bytes, end: str, snaplen: int, prev_sec: int) -> bool:
    sec, frac, caplen, origlen = struct.unpack(end + "IIII", hdr)
    return (0 < caplen <= snaplen and caplen <= origlen <= 262144 and frac < 1_000_000_000
            and (prev_sec == 0 or abs(sec - prev_sec) < 86400))


def repair(src: Path, dst: Path) -> tuple[int, int, int]:
    data = src.read_bytes()
    end = MAGICS.get(data[:4])
    if end is None:
        sys.exit(f"{src}: not a classic pcap file (magic {data[:4].hex()})")
    snaplen = struct.unpack(end + "I", data[16:20])[0]
    out = bytearray(data[:24])
    pos, kept, dropped_bytes, resyncs, prev_sec = 24, 0, 0, 0, 0
    n = len(data)
    while pos + 16 <= n:
        hdr = data[pos:pos + 16]
        if plausible(hdr, end, snaplen, prev_sec):
            caplen = struct.unpack(end + "I", hdr[8:12])[0]
            if pos + 16 + caplen > n:
                dropped_bytes += n - pos
                break
            out += data[pos:pos + 16 + caplen]
            prev_sec = struct.unpack(end + "I", hdr[:4])[0]
            pos += 16 + caplen
            kept += 1
            continue
        start = pos  # resynchronise: next offset whose header, and the one after it, are both plausible
        pos += 1
        while pos + 16 <= n:
            h = data[pos:pos + 16]
            if plausible(h, end, snaplen, prev_sec):
                c = struct.unpack(end + "I", h[8:12])[0]
                nxt = pos + 16 + c
                if nxt + 16 > n or plausible(data[nxt:nxt + 16], end, snaplen, prev_sec):
                    break
            pos += 1
        resyncs += 1
        dropped_bytes += pos - start
    dst.write_bytes(out)
    return kept, resyncs, dropped_bytes


if __name__ == "__main__":
    kept, resyncs, dropped = repair(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"kept {kept:,} records; {resyncs} damaged region(s), {dropped:,} bytes dropped")
