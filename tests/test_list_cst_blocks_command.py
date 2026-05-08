"""Smoke tests for list_cst_blocks MCP command."""

from __future__ import annotations

from code_analysis.commands.list_cst_blocks_command import ListCSTBlocksCommand


def test_list_cst_blocks_schema_requires_project_and_file() -> None:
    schema = ListCSTBlocksCommand.get_schema()
    assert schema["required"] == ["project_id", "file_path"]
    assert "file_path" in schema["properties"]


def test_list_cst_blocks_command_attrs() -> None:
    assert ListCSTBlocksCommand.name == "list_cst_blocks"
    assert ListCSTBlocksCommand.category == "cst"


def test_list_cst_blocks_metadata_rich() -> None:
    meta = ListCSTBlocksCommand.metadata()
    assert meta["name"] == "list_cst_blocks"
    for key in (
        "detailed_description",
        "parameters",
        "return_value",
        "usage_examples",
        "error_cases",
        "best_practices",
        "author",
        "email",
    ):
        assert key in meta
    assert "project_id" in meta["parameters"]
    assert "file_path" in meta["parameters"]
    assert "CST_PARSE_ERROR" in meta["error_cases"]
