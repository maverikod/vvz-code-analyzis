"""
Tests for declarative cst_load_file overview.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis.commands.cst_load_file_command import CSTLoadFileCommand


def _make_command(target: Path) -> CSTLoadFileCommand:
    """Return make command."""
    cmd = CSTLoadFileCommand()
    db = MagicMock()
    db.disconnect = MagicMock()
    cmd_any = cast(Any, cmd)
    cmd_any._open_database_from_config = MagicMock(return_value=db)
    cmd_any._resolve_file_path_from_project = MagicMock(return_value=target)
    return cmd


def test_cst_load_file_returns_declarative_overview(tmp_path: Path) -> None:
    """Declarative mode should return overview text and outline nodes."""
    target = tmp_path / "sample.py"
    target.write_text(
        '"""Module docs."""\n\n'
        "import os\n\n"
        "class Service:\n"
        '    """Service docs."""\n'
        "    def run(self) -> None:\n"
        '        """Run docs."""\n'
        "        print('x')\n",
        encoding="utf-8",
    )

    result = asyncio.run(
        _make_command(target).execute(
            project_id=str(uuid.uuid4()),
            file_path="sample.py",
            return_format="declarative",
        )
    )

    assert isinstance(result, SuccessResult)
    data = result.data
    assert "declarative" in data
    assert "outline_nodes" in data
    assert "skeleton" not in data
    assert "module [" in data["declarative"]
    assert "class Service:" in data["declarative"]
    assert "def run(self) -> None:" in data["declarative"]
    assert "Implementation hidden" in data["declarative"]
    assert any(node["kind"] == "class" for node in data["outline_nodes"])
    assert any(node["kind"] == "method" for node in data["outline_nodes"])


def test_cst_load_file_skeleton_alias_returns_declarative_payload(
    tmp_path: Path,
) -> None:
    """Legacy skeleton alias should route to the new declarative response."""
    target = tmp_path / "sample.py"
    target.write_text("def foo():\n    return 1\n", encoding="utf-8")

    result = asyncio.run(
        _make_command(target).execute(
            project_id=str(uuid.uuid4()),
            file_path="sample.py",
            return_format="skeleton",
        )
    )

    assert isinstance(result, SuccessResult)
    data = result.data
    assert "declarative" in data
    assert "outline_nodes" in data
    assert "skeleton" not in data
