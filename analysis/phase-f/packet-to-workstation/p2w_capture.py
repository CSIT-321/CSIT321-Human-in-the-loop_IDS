"""Layer 1 and 2 facts for the packet-to-workstation walkthrough.

1. Find the first real 'ET SCAN Potential SSH Scan' alert in the Wednesday-14-02-2018 capture for 172.31.69.25.
2. Read the matching packets from the repaired pcap that contains that host, by 5-tuple and time window.
3. Write data/packets.json and data/suricata_alert.json.

Read-only: reads the pcap and eve.json, writes only under analysis/phase-f/packet-to-workstation/data/.

Usage: python p2w_capture.py [--window 5]
"""
from __future__ import annotations

import argparse
import json
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[3] / "hitl-ids"
OUT = Path(__file__).resolve().parent / "data"
EVE = BASE / "data/spike/Wednesday-14-02-2018/suricata-172.31.69.25/eve.json"
PCAP = BASE / "data/spike/Wednesday-14-02-2018/repaired/172.31.69.25.pcap"
SIG = "ET SCAN Potential SSH Scan"


def first_alert() -> dict:
    with EVE.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"event_type":"alert"' not in line or SIG not in line:
                continue
            e = json.loads(line)
            if e.get("event_type") == "alert" and e["alert"]["signature"] == SIG:
                return e
    raise SystemExit("alert not found")


def read_pcap(path: Path, want: dict, window_ms: int, limit: int = 12) -> list[dict]:
    """Return the first `limit` TCP packets of want['src']->want['dst']:dport inside the window."""
    src = bytes(map(int, want["src"].split(".")))
    dst = bytes(map(int, want["dst"].split(".")))
    lo = want["utc"] - timedelta(milliseconds=window_ms)
    hi = want["utc"] + timedelta(milliseconds=window_ms)
    out = []
    with path.open("rb") as f:
        head = f.read(24)
        magic = head[:4]
        if magic == b"\xd4\xc3\xb2\xa1":
            endian = "<"
        elif magic == b"\xa1\xb2\xc3\xd4":
            endian = ">"
        else:
            raise SystemExit(f"unsupported pcap magic {magic.hex()}")
        linktype = struct.unpack(endian + "I", head[20:24])[0]
        index = 0
        while True:
            ph = f.read(16)
            if len(ph) < 16:
                break
            ts_sec, ts_frac, incl, _orig = struct.unpack(endian + "IIII", ph)
            data = f.read(incl)
            if len(data) < incl:
                break
            index += 1
            when = datetime.fromtimestamp(ts_sec, tz=timezone.utc) + timedelta(microseconds=ts_frac)
            if when < lo:
                continue
            if when > hi:
                break
            ip = data[14:] if linktype == 1 else data
            if len(ip) < 20 or ip[0] >> 4 != 4 or ip[9] != 6:
                continue
            ihl = (ip[0] & 0x0F) * 4
            if ip[12:16] != src or ip[16:20] != dst:
                continue
            tcp = ip[ihl:]
            if len(tcp) < 20:
                continue
            sport, dport = struct.unpack(">HH", tcp[:4])
            if dport != want["dport"]:
                continue
            flags = tcp[13]
            names = "".join(n for b, n in ((1, "FIN"), (2, "SYN"), (4, "RST"), (8, "PSH"), (16, "ACK")) if flags & b)
            out.append({
                "index": index,
                "utc": when.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z",
                "epoch": f"{ts_sec}.{ts_frac:06d}",
                "frameBytes": len(data),
                "ethSrcMac": data[6:12].hex(":"),
                "ethDstMac": data[0:6].hex(":"),
                "etherType": data[12:14].hex(),
                "ipVersion": ip[0] >> 4,
                "ipHeaderLength": ihl,
                "ipTotalLength": struct.unpack(">H", ip[2:4])[0],
                "ipTtl": ip[8],
                "ipProtocol": ip[9],
                "ipChecksum": ip[10:12].hex(),
                "src": want["src"], "dst": want["dst"],
                "srcPort": sport, "dstPort": dport,
                "seq": struct.unpack(">I", tcp[4:8])[0],
                "ack": struct.unpack(">I", tcp[8:12])[0],
                "window": struct.unpack(">H", tcp[14:16])[0],
                "tcpHeaderLength": (tcp[12] >> 4) * 4,
                "flags": names,
                "flagsBits": flags,
                "payloadBytes": len(tcp) - ((tcp[12] >> 4) * 4),
                "hex": data[:54].hex(" "),
            })
            if len(out) >= limit:
                break
    return out


def read_pcap_by_index(path: Path, index: int) -> dict | None:
    """Decode one frame by its 1-based position in the capture, as eve.json's pcap_cnt counts it."""
    if index <= 0:
        return None
    with path.open("rb") as f:
        head = f.read(24)
        endian = "<" if head[:4] == b"\xd4\xc3\xb2\xa1" else ">"
        linktype = struct.unpack(endian + "I", head[20:24])[0]
        for i in range(1, index + 1):
            ph = f.read(16)
            if len(ph) < 16:
                return None
            ts_sec, ts_frac, incl, _orig = struct.unpack(endian + "IIII", ph)
            data = f.read(incl)
            if i != index:
                continue
            ip = data[14:] if linktype == 1 else data
            if len(ip) < 20 or ip[0] >> 4 != 4:
                return {"index": index, "note": "frame is not IPv4"}
            ihl = (ip[0] & 0x0F) * 4
            row = {"index": index, "epoch": f"{ts_sec}.{ts_frac:06d}",
                   "utc": datetime.fromtimestamp(ts_sec, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                   "src": ".".join(map(str, ip[12:16])), "dst": ".".join(map(str, ip[16:20])),
                   "ipProtocol": ip[9], "ipTotalLength": struct.unpack(">H", ip[2:4])[0],
                   "frameBytes": len(data), "hex": data[:54].hex(" ")}
            if ip[9] == 6 and len(ip) >= ihl + 20:
                tcp = ip[ihl:]
                row["srcPort"], row["dstPort"] = struct.unpack(">HH", tcp[:4])
                row["flagsBits"] = tcp[13]
                row["flags"] = "".join(n for b, n in ((1, "FIN"), (2, "SYN"), (4, "RST"), (8, "PSH"), (16, "ACK"))
                                       if tcp[13] & b)
            return row
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=5000, help="half window in milliseconds")
    args = ap.parse_args()
    alert = first_alert()
    when = datetime.fromisoformat(alert["timestamp"].replace("+0800", "+08:00")).astimezone(timezone.utc)
    want = {"src": alert["src_ip"], "dst": alert["dest_ip"], "dport": alert["dest_port"], "utc": when}
    print(f"alert: {alert['alert']['signature']} sid {alert['alert']['signature_id']} "
          f"at {alert['timestamp']} ({when:%Y-%m-%dT%H:%M:%SZ}) {want['src']} -> {want['dst']}:{want['dport']}")
    packets = read_pcap(PCAP, want, args.window)
    # eve.json names the exact frame that raised the alert: pcap_cnt. Read that frame by index.
    exact = read_pcap_by_index(PCAP, int(alert.get("pcap_cnt") or 0))
    print(f"packets in +-{args.window} ms: {len(packets)}")
    for p in packets[:6]:
        print(f"  {p['utc']} {p['src']}:{p['srcPort']} -> {p['dst']}:{p['dstPort']} {p['flags']} "
              f"ip_len {p['ipTotalLength']} ttl {p['ipTtl']} win {p['window']}")
    OUT.mkdir(parents=True, exist_ok=True)
    keep = {k: alert.get(k) for k in ("timestamp", "flow_id", "pcap_cnt", "src_ip", "src_port", "dest_ip",
                                      "dest_port", "proto", "app_proto", "direction")}
    keep["alert"] = alert["alert"]
    keep["flow"] = alert.get("flow")
    (OUT / "suricata_alert.json").write_text(json.dumps({
        "source_file": str(EVE.relative_to(BASE)).replace("\\", "/"),
        "alert": keep,
        "raw_line_bytes": len(json.dumps(alert)),
    }, indent=1), encoding="utf-8")
    (OUT / "packets.json").write_text(json.dumps({
        "pcap": str(PCAP.relative_to(BASE)).replace("\\", "/"),
        "filter": {"src": want["src"], "dst": want["dst"], "dstPort": want["dport"]},
        "windowMs": args.window, "count": len(packets), "packets": packets,
        "triggerFrame": exact,
    }, indent=1), encoding="utf-8")
    print(f"wrote {OUT / 'packets.json'} and {OUT / 'suricata_alert.json'}")


if __name__ == "__main__":
    main()
