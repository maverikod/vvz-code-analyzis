"""Unit tests for atomic block publication."""

from __future__ import annotations

import json
import threading
import time

from code_analysis.core.search_session.atomic_publication import (
    atomic_publish_rename,
    atomic_write_bytes,
    atomic_write_json,
)


def test_atomic_write_bytes_publishes_complete_file(tmp_path) -> None:
    target = tmp_path / "nested" / "block_1.json"
    atomic_write_bytes(target, b'{"ready": true}')

    assert target.read_bytes() == b'{"ready": true}'
    assert not target.with_suffix(target.suffix + ".tmp").exists()


def test_atomic_write_json_writes_valid_json(tmp_path) -> None:
    target = tmp_path / "index.json"
    atomic_write_json(target, {"blocks": [], "completeness": "search_still_running"})

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["completeness"] == "search_still_running"


def test_readers_never_see_partial_file_during_write(tmp_path) -> None:
    target = tmp_path / "block.json"
    staging = target.with_suffix(target.suffix + ".tmp")
    observed: list[str | None] = []
    started = threading.Event()

    def slow_writer() -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(staging, "wb") as handle:
            handle.write(b'{"partial":')
            handle.flush()
            started.set()
            time.sleep(0.05)
            handle.write(b'"done"}')
            handle.flush()
        atomic_publish_rename(staging, target)

    def reader() -> None:
        started.wait(timeout=1.0)
        deadline = time.time() + 0.2
        while time.time() < deadline:
            if target.exists():
                try:
                    json.loads(target.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    observed.append("partial")
                else:
                    observed.append("complete")
            time.sleep(0.01)

    writer = threading.Thread(target=slow_writer)
    reader_thread = threading.Thread(target=reader)
    writer.start()
    reader_thread.start()
    writer.join(timeout=2.0)
    reader_thread.join(timeout=2.0)

    assert target.exists()
    assert "partial" not in observed
    assert json.loads(target.read_text(encoding="utf-8")) == {"partial": "done"}
