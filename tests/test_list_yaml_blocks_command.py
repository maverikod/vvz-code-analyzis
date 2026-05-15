"""
Integration-style tests for list_yaml_blocks (mock DB, tmp_path).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

pytest.importorskip("yaml")

from code_analysis.commands.base_mcp_command import BaseMCPCommand  # noqa: E402
from code_analysis.commands.list_yaml_blocks_command import ListYamlBlocksCommand  # noqa: E402
from code_analysis.core.json_tree.models import stable_node_id_for_pointer  # noqa: E402

_PROJECT_ID = "test-project-id"

_REQUIRED_BLOCK_KEYS = frozenset(
    {"node_id", "yaml_pointer", "kind", "key", "index", "parent_id"}
)


@pytest.fixture
def patched_db_resolve(tmp_path: Path):
    """Avoid real DB; resolve project-relative paths under tmp_path."""
    mock_db = MagicMock()
    mock_db.disconnect = MagicMock()
    mock_proj = MagicMock()
    mock_proj.root_path = str(tmp_path)
    mock_db.get_project.return_value = mock_proj
    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            side_effect=lambda db, pid, fp, **kw: tmp_path / fp,
        ),
    ):
        yield mock_db


@pytest.mark.asyncio
async def test_execute_happy_path_mapping(tmp_path: Path, patched_db_resolve):
    path = tmp_path / "config.yaml"
    path.write_text(
        "key: 7\n" "items:\n" "  - 1\n" "  - 2\n",
        encoding="utf-8",
    )
    result = await ListYamlBlocksCommand().execute(
        project_id=_PROJECT_ID,
        file_path="config.yaml",
    )
    assert isinstance(result, SuccessResult)
    assert result.data is not None
    assert result.data["success"] is True
    assert result.data["total_blocks"] > 0
    blocks = result.data["blocks"]
    for b in blocks:
        assert _REQUIRED_BLOCK_KEYS <= set(b.keys())
    key_blocks = [b for b in blocks if b["yaml_pointer"] == "/key"]
    assert len(key_blocks) == 1
    assert key_blocks[0]["kind"] == "number"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    ["", "# comment only\n"],
)
async def test_execute_empty_document_becomes_mapping_root(
    tmp_path: Path, patched_db_resolve, content: str
):
    path = tmp_path / "empty.yaml"
    path.write_text(content, encoding="utf-8")
    result = await ListYamlBlocksCommand().execute(
        project_id=_PROJECT_ID,
        file_path="empty.yaml",
    )
    assert isinstance(result, SuccessResult)
    blocks = result.data["blocks"]
    root = next(b for b in blocks if b["yaml_pointer"] == "")
    assert root["kind"] == "object"


@pytest.mark.asyncio
async def test_execute_invalid_extension(tmp_path: Path, patched_db_resolve):
    path = tmp_path / "data.json"
    path.write_text("{}", encoding="utf-8")
    result = await ListYamlBlocksCommand().execute(
        project_id=_PROJECT_ID,
        file_path="data.json",
    )
    assert isinstance(result, ErrorResult)
    assert result.code == "INVALID_FILE"


@pytest.mark.asyncio
async def test_execute_file_not_found(tmp_path: Path, patched_db_resolve):
    result = await ListYamlBlocksCommand().execute(
        project_id=_PROJECT_ID,
        file_path="missing.yaml",
    )
    assert isinstance(result, ErrorResult)
    assert result.code == "FILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_execute_invalid_yaml(tmp_path: Path, patched_db_resolve):
    path = tmp_path / "broken.yaml"
    path.write_text("key: [\n", encoding="utf-8")
    result = await ListYamlBlocksCommand().execute(
        project_id=_PROJECT_ID,
        file_path="broken.yaml",
    )
    assert isinstance(result, ErrorResult)
    assert result.code == "INVALID_YAML"


@pytest.mark.asyncio
async def test_node_id_matches_stable_node_id_for_pointer(
    tmp_path: Path, patched_db_resolve
):
    path = tmp_path / "doc.yaml"
    path.write_text("a: 1\n", encoding="utf-8")
    result = await ListYamlBlocksCommand().execute(
        project_id=_PROJECT_ID,
        file_path="doc.yaml",
    )
    assert isinstance(result, SuccessResult)
    blocks = result.data["blocks"]
    a_block = next(b for b in blocks if b["yaml_pointer"] == "/a")
    assert a_block["node_id"] == stable_node_id_for_pointer("/a")
