"""Tests for view_worker_logs parameter normalization."""

from __future__ import annotations

from code_analysis.commands.log_viewer_mcp_commands.view_worker_logs import (
    ViewWorkerLogsMCPCommand,
)


def test_view_worker_logs_strips_dot_log_suffix_for_log_id() -> None:
    cmd = ViewWorkerLogsMCPCommand()
    out = cmd.validate_params({"log_id": "mcp_server.log"})
    assert out["log_id"] == "mcp_server"


def test_view_worker_logs_leaves_canonical_log_id() -> None:
    cmd = ViewWorkerLogsMCPCommand()
    out = cmd.validate_params({"log_id": "code_analysis"})
    assert out["log_id"] == "code_analysis"
