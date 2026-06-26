"""Text format universal_file_* write_mode preview/commit lifecycle.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from code_analysis.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from code_analysis.commands.universal_file_edit.open_command import (
    UniversalFileOpenCommand,
)
from code_analysis.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)

_PROJECT_UUID = "baadf00d-baad-4bad-b00d-baaaaaaaaaaa"


def _ensure_project_root(tmp: Path) -> None:
    """Return ensure project root."""
    marker = tmp / "projectid"
    if not marker.exists():
        marker.write_text(
            '{"id": "00000000-0000-0000-0000-000000000001"}\n',
            encoding="utf-8",
        )


def _mock_db_bundle(tmp: Path) -> MagicMock:
    """Return mock db bundle."""
    db = MagicMock()
    proj = MagicMock()
    proj.root_path = str(tmp.resolve())
    db.get_project.return_value = proj
    return db


async def _open_text(tmp: Path, rel: str = "notes/sample.txt") -> tuple[str, Path]:
    """Return open text."""
    _ensure_project_root(tmp)
    target = tmp / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("line one\nline two\n", encoding="utf-8")
    cmd = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_mock_db_bundle(tmp)
    ):
        res = await cmd.execute(
            **cmd.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        )
    assert isinstance(res, SuccessResult)
    return str(res.data["session_id"]), target


@pytest.mark.asyncio
async def test_text_write_preview_does_not_touch_disk(tmp_path: Path) -> None:
    """write_mode=preview must not commit even on repeated calls."""
    rel = "notes/sample.txt"
    sid, target = await _open_text(tmp_path, rel)
    before = target.read_text(encoding="utf-8")

    edit = UniversalFileEditCommand()
    write = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "start_line": 1,
                            "end_line": 1,
                            "content": "line ONE\n",
                        }
                    ],
                }
            )
        )
        r1 = await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "preview",
                }
            )
        )
        r2 = await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "preview",
                }
            )
        )

    assert isinstance(r1, SuccessResult)
    assert r1.data.get("phase") == "preview"
    assert isinstance(r2, SuccessResult)
    assert r2.data.get("phase") == "preview"
    assert target.read_text(encoding="utf-8") == before
    assert "line ONE" in str(r1.data.get("diff", ""))


@pytest.mark.asyncio
async def test_text_preview_commit_close_roundtrip(tmp_path: Path) -> None:
    """Verify test text preview commit close roundtrip."""
    rel = "notes/sample.txt"
    sid, target = await _open_text(tmp_path, rel)

    edit = UniversalFileEditCommand()
    write = UniversalFileWriteCommand()
    close = UniversalFileCloseCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "start_line": 2,
                            "end_line": 2,
                            "content": "line TWO\n",
                        }
                    ],
                }
            )
        )
        preview_write = await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "preview",
                }
            )
        )
        assert target.read_text(encoding="utf-8") == "line one\nline two\n"
        commit_write = await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "commit",
                }
            )
        )
        await close.execute(
            **close.validate_params({"project_id": _PROJECT_UUID, "session_id": sid})
        )

    assert isinstance(preview_write, SuccessResult)
    assert preview_write.data.get("phase") == "preview"
    assert isinstance(commit_write, SuccessResult)
    assert commit_write.data.get("phase") == "committed"
    assert target.read_text(encoding="utf-8") == "line one\nline TWO\n"


@pytest.mark.asyncio
async def test_text_second_edit_after_preview_before_commit(tmp_path: Path) -> None:
    """Line replace after preview must apply to draft, not committed canonical."""
    rel = "notes/sample.txt"
    sid, target = await _open_text(tmp_path, rel)

    edit = UniversalFileEditCommand()
    write = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "start_line": 1,
                            "end_line": 1,
                            "content": "first edit\n",
                        }
                    ],
                }
            )
        )
        await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "preview",
                }
            )
        )
        assert target.read_text(encoding="utf-8") == "line one\nline two\n"

        await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "start_line": 2,
                            "end_line": 2,
                            "content": "second edit\n",
                        }
                    ],
                }
            )
        )
        commit = await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "commit",
                }
            )
        )

    assert isinstance(commit, SuccessResult)
    assert commit.data.get("phase") == "committed"
    assert target.read_text(encoding="utf-8") == "first edit\nsecond edit\n"
    assert "second edit" in str(commit.data.get("diff", ""))


@pytest.mark.asyncio
async def test_text_edit_rejects_stale_line_number_after_prior_edit(
    tmp_path: Path,
) -> None:
    """Out-of-range start_line after a prior edit must fail, not corrupt the draft."""
    rel = "notes/sample.txt"
    sid, target = await _open_text(tmp_path, rel)

    edit = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        first = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "start_line": 1,
                            "content": "inserted\n",
                        }
                    ],
                }
            )
        )
        assert isinstance(first, SuccessResult)
        assert first.data.get("line_count") == 3

        stale = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "start_line": 10,
                            "end_line": 10,
                            "content": "wrong target\n",
                        }
                    ],
                }
            )
        )

    assert isinstance(stale, ErrorResult)
    assert stale.code == "LINE_OUT_OF_RANGE"
    assert target.read_text(encoding="utf-8") == "line one\nline two\n"


@pytest.mark.asyncio
async def test_text_edit_anchor_mismatch_rejects_stale_coordinates(
    tmp_path: Path,
) -> None:
    """Verify test text edit anchor mismatch rejects stale coordinates."""
    rel = "notes/sample.txt"
    sid, _target = await _open_text(tmp_path, rel)

    edit = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        result = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "start_line": 2,
                            "end_line": 2,
                            "content": "updated\n",
                            "anchor_head": "wrong",
                            "anchor_tail": "wrong",
                        }
                    ],
                }
            )
        )

    assert isinstance(result, ErrorResult)
    assert result.code == "ANCHOR_MISMATCH"
