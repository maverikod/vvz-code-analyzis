"""Tests for fs_grep parameter bounds validation."""

from __future__ import annotations

import uuid

import pytest

from code_analysis.commands.fs_grep_command import FsGrepCommand
from code_analysis.core.exceptions import ValidationError


@pytest.fixture
def cmd() -> FsGrepCommand:
    return FsGrepCommand()


@pytest.fixture
def base_params() -> dict[str, object]:
    return {"project_id": str(uuid.uuid4()), "pattern": "needle"}


def test_validate_params_accepts_bounded_params_in_range(
    cmd: FsGrepCommand,
    base_params: dict[str, object],
) -> None:
    out = cmd.validate_params(
        {
            **base_params,
            "max_matches": 500,
            "enrich_max_results": 50,
            "max_file_bytes": 5242880,
            "line_preview_len": 120,
            "grep_sync_max_wall_seconds": 45.0,
            "hard_timeout_seconds": 120.0,
            "inline_timeout_seconds": 3.0,
        }
    )
    assert out["max_matches"] == 500
    assert out["enrich_max_results"] == 50
    assert out["max_file_bytes"] == 5242880
    assert out["line_preview_len"] == 120


@pytest.mark.parametrize("max_matches", [0, -1, 10001, 50000])
def test_validate_params_rejects_max_matches_out_of_range(
    cmd: FsGrepCommand,
    base_params: dict[str, object],
    max_matches: int,
) -> None:
    with pytest.raises(ValidationError, match="max_matches") as exc_info:
        cmd.validate_params({**base_params, "max_matches": max_matches})
    assert exc_info.value.field == "max_matches"


@pytest.mark.parametrize("enrich_max_results", [-1, 201, 500])
def test_validate_params_rejects_enrich_max_results_out_of_range(
    cmd: FsGrepCommand,
    base_params: dict[str, object],
    enrich_max_results: int,
) -> None:
    with pytest.raises(ValidationError, match="enrich_max_results") as exc_info:
        cmd.validate_params({**base_params, "enrich_max_results": enrich_max_results})
    assert exc_info.value.field == "enrich_max_results"


@pytest.mark.parametrize("max_file_bytes", [-1, 1073741825])
def test_validate_params_rejects_max_file_bytes_out_of_range(
    cmd: FsGrepCommand,
    base_params: dict[str, object],
    max_file_bytes: int,
) -> None:
    with pytest.raises(ValidationError, match="max_file_bytes") as exc_info:
        cmd.validate_params({**base_params, "max_file_bytes": max_file_bytes})
    assert exc_info.value.field == "max_file_bytes"


@pytest.mark.parametrize("line_preview_len", [0, -1, 100001])
def test_validate_params_rejects_line_preview_len_out_of_range(
    cmd: FsGrepCommand,
    base_params: dict[str, object],
    line_preview_len: int,
) -> None:
    with pytest.raises(ValidationError, match="line_preview_len") as exc_info:
        cmd.validate_params({**base_params, "line_preview_len": line_preview_len})
    assert exc_info.value.field == "line_preview_len"


@pytest.mark.parametrize("grep_sync_max_wall_seconds", [4.9, -1.0, 601.0, 1000.0])
def test_validate_params_rejects_grep_sync_max_wall_seconds_out_of_range(
    cmd: FsGrepCommand,
    base_params: dict[str, object],
    grep_sync_max_wall_seconds: float,
) -> None:
    with pytest.raises(ValidationError, match="grep_sync_max_wall_seconds") as exc_info:
        cmd.validate_params(
            {**base_params, "grep_sync_max_wall_seconds": grep_sync_max_wall_seconds}
        )
    assert exc_info.value.field == "grep_sync_max_wall_seconds"


@pytest.mark.parametrize("hard_timeout_seconds", [0, -1.0, 3601.0, 5000.0])
def test_validate_params_rejects_hard_timeout_seconds_out_of_range(
    cmd: FsGrepCommand,
    base_params: dict[str, object],
    hard_timeout_seconds: float,
) -> None:
    with pytest.raises(ValidationError, match="hard_timeout_seconds") as exc_info:
        cmd.validate_params(
            {**base_params, "hard_timeout_seconds": hard_timeout_seconds}
        )
    assert exc_info.value.field == "hard_timeout_seconds"


@pytest.mark.parametrize("inline_timeout_seconds", [0.0, 0.05, 30.1, 100.0])
def test_validate_params_rejects_inline_timeout_seconds_out_of_range(
    cmd: FsGrepCommand,
    base_params: dict[str, object],
    inline_timeout_seconds: float,
) -> None:
    with pytest.raises(ValidationError, match="inline_timeout_seconds") as exc_info:
        cmd.validate_params(
            {**base_params, "inline_timeout_seconds": inline_timeout_seconds}
        )
    assert exc_info.value.field == "inline_timeout_seconds"
