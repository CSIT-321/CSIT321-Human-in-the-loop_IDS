"""ExporterSource (S17 skeleton): tailing a CSV as it grows, the shape a live flow exporter is
expected to write to. See packages/detection/pipeline/source.py for what this class does and
does not solve - no capture tool is wired up here, only reading its eventual output correctly.

The one correctness property worth a real test, not just a read-the-whole-file-at-once check: a
poll can land while a writer has only flushed part of a row. A naive line-splitter would either
drop that half-row or corrupt the next one by gluing them together. This test forces exactly that
by writing a row in two pieces, with a real pause between them, on a real background thread.
"""

from __future__ import annotations

import csv
import io
import threading
import time

import pytest
from conftest import COLUMNS, row

from packages.detection.pipeline.source import ExporterSource


def write_header(path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore").writeheader()


def append_row(path, record: dict[str, object]) -> None:
    with path.open("a", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore").writerow(record)


def render_row(record: dict[str, object]) -> str:
    """One CSV row as text, without writing it anywhere - so a test can split it itself."""
    buffer = io.StringIO()
    csv.DictWriter(buffer, fieldnames=COLUMNS, extrasaction="ignore").writerow(record)
    return buffer.getvalue()


def append_text(path, text: str) -> None:
    with path.open("a", newline="", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()


def test_exporter_source_tails_a_growing_file_across_a_split_write(tmp_path):
    path = tmp_path / "live.csv"
    write_header(path)
    source = ExporterSource(path, poll_interval=0.02, idle_polls_before_stop=15)

    def writer() -> None:
        append_row(path, row("AL-LIVE-0001", minute=0, dst_port=22))
        time.sleep(0.08)  # let the reader poll and consume the first row on its own

        # Write one row in two pieces, with a real gap between them, so a poll is guaranteed to
        # land mid-row at least some of the time this test runs.
        full_line = render_row(row("AL-LIVE-0002", minute=1, dst_port=21))
        half = len(full_line) // 2
        append_text(path, full_line[:half])
        time.sleep(0.08)
        append_text(path, full_line[half:])
        time.sleep(0.08)

        append_row(path, row("AL-LIVE-0003", minute=2, dst_port=80))

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    flows = list(source.flows())
    thread.join(timeout=5)

    assert [flow.source_record_id for flow in flows] == [
        "AL-LIVE-0001", "AL-LIVE-0002", "AL-LIVE-0003"]
    # The split row must have arrived whole, not truncated or merged with its neighbour.
    assert flows[1].features["Dst Port"] == 21
    assert flows[2].features["Dst Port"] == 80


def test_exporter_source_rejects_a_file_missing_required_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("alert_id,Timestamp\n", encoding="utf-8")
    source = ExporterSource(path, idle_polls_before_stop=1, poll_interval=0.01)
    with pytest.raises(KeyError):
        next(source.flows())


def test_exporter_source_stops_after_the_configured_idle_polls(tmp_path):
    path = tmp_path / "quiet.csv"
    write_header(path)
    append_row(path, row("AL-LIVE-ONLY", minute=0, dst_port=22))
    source = ExporterSource(path, poll_interval=0.01, idle_polls_before_stop=3)

    start = time.monotonic()
    flows = list(source.flows())
    elapsed = time.monotonic() - start

    assert [flow.source_record_id for flow in flows] == ["AL-LIVE-ONLY"]
    assert elapsed < 2  # it must actually stop, not hang forever
