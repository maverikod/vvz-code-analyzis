"""
Tests for AnalyzeCommand.analyze_file().

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from code_analysis.commands.analyze import AnalyzeCommand
from code_analysis.core.database import CodeDatabase


class TestAnalyzeFileMethod:
    """Regression tests for MCP-facing single-file analysis API."""

    @pytest.mark.asyncio
    async def test_analyze_file_success_creates_file_record(self) -> None:
        """AnalyzeCommand.analyze_file should analyze a file and persist it in DB."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data").mkdir(parents=True, exist_ok=True)
            db_path = root / "data" / "code_analysis.db"

            db = CodeDatabase(db_path)
            try:
                project_id = db.get_or_create_project(str(root), name="test_project")

                sample = root / "sample.py"
                sample.write_text(
                    '"""Sample file."""\n\n' "def foo() -> int:\n" "    return 1\n",
                    encoding="utf-8",
                )

                cmd = AnalyzeCommand(
                    database=db,
                    project_id=project_id,
                    root_path=str(root),
                    max_lines=400,
                    force=True,
                )

                result = await cmd.analyze_file(sample, force=True)
                assert result["success"] is True
                assert result["project_id"] == project_id
                assert Path(result["file_path"]).resolve() == sample.resolve()

                rec = db.get_file_by_path(str(sample.resolve()), project_id)
                assert rec is not None
            finally:
                db.close()
