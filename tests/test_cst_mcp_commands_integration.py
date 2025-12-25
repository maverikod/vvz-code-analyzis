"""
Integration tests for CST MCP commands: query_cst and compose_cst_module.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_analysis.commands.cst_compose_module_command import ComposeCSTModuleCommand
from code_analysis.commands.query_cst_command import QueryCSTCommand


@pytest.mark.asyncio
async def test_query_cst_finds_return(tmp_path: Path) -> None:
    root = tmp_path
    target = root / "m.py"
    target.write_text(
        "\n".join(
            [
                "def f(x: int) -> int:",
                "    y = x + 1",
                "    return y",
                "",
            ]
        ),
        encoding="utf-8",
    )

    cmd = QueryCSTCommand()
    result = await cmd.execute(
        root_dir=str(root),
        file_path=str(target),
        selector='smallstmt[type="Return"]',
        include_code=False,
    )
    payload = result.to_dict()
    assert payload["success"] is True
    matches = payload["data"]["matches"]
    assert len(matches) == 1
    assert matches[0]["kind"] == "smallstmt"
    assert matches[0]["type"] == "Return"


@pytest.mark.asyncio
async def test_compose_cst_module_can_replace_by_cst_query(tmp_path: Path) -> None:
    root = tmp_path
    target = root / "m.py"
    target.write_text(
        "\n".join(
            [
                "def f(x: int) -> int:",
                "    y = x + 1",
                "    return y",
                "",
            ]
        ),
        encoding="utf-8",
    )

    cmd = ComposeCSTModuleCommand()
    result = await cmd.execute(
        root_dir=str(root),
        file_path=str(target),
        ops=[
            {
                "selector": {"kind": "cst_query", "query": 'smallstmt[type="Return"]'},
                "new_code": "return 123",
            }
        ],
        apply=True,
        create_backup=True,
        return_source=True,
        return_diff=True,
    )
    payload = result.to_dict()
    assert payload["success"] is True
    assert payload["data"]["compiled"] is True
    assert "return 123" in payload["data"]["source"]
    assert target.read_text(encoding="utf-8").find("return 123") != -1
    assert payload["data"]["backup_path"] is not None
# End of file
