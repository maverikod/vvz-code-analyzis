"""Unit tests for search profile JSONL recorder."""

from __future__ import annotations

import json

from code_analysis.core.search_session.search_profile_log import (
    SearchProfileRecorder,
    is_search_profile_enabled,
    resolve_search_profile_log_path,
)


def test_resolve_search_profile_log_path_uses_log_dir(tmp_path) -> None:
    """Verify test resolve search profile log path uses log dir."""
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    cfg = {"server": {"log_dir": str(tmp_path / "logs")}}

    path = resolve_search_profile_log_path(
        config_data=cfg,
        config_path=config_path,
    )

    assert path == (tmp_path / "logs" / "search_profile.jsonl").resolve()


def test_recorder_writes_jsonl_checkpoint(tmp_path) -> None:
    """Verify test recorder writes jsonl checkpoint."""
    log_path = tmp_path / "search_profile.jsonl"
    rec = SearchProfileRecorder(job_id="job-a", log_path=log_path)
    rec.checkpoint("test_start", rows=3)
    rec.checkpoint("test_done", ok=True)

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["checkpoint"] == "test_start"
    assert first["job_id"] == "job-a"
    assert first["rows"] == 3
    assert second["checkpoint"] == "test_done"
    assert second["since_prev_sec"] >= 0


def test_profile_disabled_via_config() -> None:
    """Verify test profile disabled via config."""
    cfg = {"search_session": {"profile_log_enabled": False}}
    assert is_search_profile_enabled(cfg) is False
