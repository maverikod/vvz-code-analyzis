"""Pagination contract for log viewing MCP commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from code_analysis.commands.log_viewer import LogViewerCommand
from code_analysis.commands.log_viewer_mcp_commands.analyze_timing_bottlenecks import (
    AnalyzeTimingBottlenecksMCPCommand,
)
from code_analysis.commands.log_viewer_mcp_commands.list_logs import ListLogsMCPCommand
from code_analysis.commands.log_viewer_mcp_commands.list_worker_logs import (
    ListWorkerLogsMCPCommand,
)
from code_analysis.commands.log_viewer_mcp_commands.view_worker_logs import (
    ViewWorkerLogsMCPCommand,
)


def _sample_log_lines(n: int) -> list[str]:
    return [f"2024-01-01 12:00:00 | INFO | 5 | message {i}\n" for i in range(n)]


@pytest.mark.asyncio
async def test_log_viewer_command_pagination(tmp_path: Path) -> None:
    log_file = tmp_path / "test.log"
    log_file.write_text("".join(_sample_log_lines(5)), encoding="utf-8")

    cmd = LogViewerCommand(
        log_path=str(log_file),
        worker_type="server",
        page_size=2,
        offset=2,
        block_position=2,
    )
    result = await cmd.execute()

    assert result["paginated"] is True
    assert result["total"] == 5
    assert result["count"] == 2
    assert result["block_position"] == 2
    assert result["has_more"] is True
    assert len(result["entries"]) == 2
    assert result["entries"] == result["items"]
    assert "message 2" in result["entries"][0]["message"]


@pytest.mark.asyncio
async def test_list_worker_logs_pagination(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    for i in range(5):
        (log_dir / f"app_{i}.log").write_text("x\n")

    cmd = ListWorkerLogsMCPCommand()
    result = await cmd.execute(
        log_dirs=[str(log_dir)],
        worker_type="server",
        page_size=2,
        block_position=2,
    )

    assert result.data is not None
    data = result.data
    assert data["paginated"] is True
    assert data["total"] == 5
    assert data["count"] == 2
    assert data["has_more"] is True
    assert len(data["log_files"]) == 2
    assert data["log_files"] == data["items"]
    assert data["total_files"] == data["total"]


@pytest.mark.asyncio
async def test_list_logs_pagination() -> None:
    fake_logs = [{"log_id": f"log_{i}", "description": f"d{i}"} for i in range(4)]

    cmd = ListLogsMCPCommand()
    with (
        patch.object(
            ListLogsMCPCommand,
            "_resolve_config_path",
            return_value="/tmp/config.json",
        ),
        patch(
            "code_analysis.commands.log_viewer_mcp_commands.list_logs.load_raw_config",
            return_value={},
        ),
        patch(
            "code_analysis.commands.log_viewer_mcp_commands.list_logs.ListLogsByIdCommand"
        ) as mock_cls,
    ):
        mock_cls.return_value.execute = AsyncMock(
            return_value={"logs": fake_logs, "total": len(fake_logs), "message": "ok"}
        )
        result = await cmd.execute(page_size=2, block_position=2)

    assert result.data is not None
    data = result.data
    assert data["paginated"] is True
    assert data["total"] == 4
    assert data["count"] == 2
    assert data["logs"] == data["items"]
    assert data["logs"][0]["log_id"] == "log_2"


@pytest.mark.asyncio
async def test_analyze_timing_bottlenecks_operations_pagination(tmp_path: Path) -> None:
    log_file = tmp_path / "vectorization_worker.log"
    lines = []
    for i in range(6):
        lines.append(
            f"2024-01-01 12:00:00 | INFO | 5 | [TIMING] op_{i} duration=0.{i}s\n"
        )
    log_file.write_text("".join(lines), encoding="utf-8")

    cmd = AnalyzeTimingBottlenecksMCPCommand()
    with patch.object(cmd, "_is_timing_enabled", return_value=True):
        result = await cmd.execute(
            log_path=str(log_file),
            page_size=2,
            block_position=2,
        )

    assert result.data is not None
    data = result.data
    assert data["paginated"] is True
    assert data["operations_total"] == 6
    assert data["total"] == 6
    assert data["count"] == 2
    assert data["operations"] == data["items"]
    assert len(data["bottlenecks_by_total"]) <= 10


def test_view_worker_logs_validate_pagination_defaults() -> None:
    cmd = ViewWorkerLogsMCPCommand()
    out = cmd.validate_params({"limit": 50})
    assert out["page_size"] == 50
    assert out["block_position"] == 1
    assert out["offset"] == 0
