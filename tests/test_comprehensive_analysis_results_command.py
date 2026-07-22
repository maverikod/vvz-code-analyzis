"""
Tests for get_comprehensive_analysis_results command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.command_metadata_helpers import REQUIRED_METADATA_KEYS
from code_analysis.commands.comprehensive_analysis_results_mcp.command import (
    ComprehensiveAnalysisResultsMCPCommand,
)


PROJECT_ID = "550e8400-e29b-41d4-a716-446655440000"


class _FakeAnalysisResultsDb:
    """Minimal DatabaseClient-shaped fake for direct command tests."""

    def __init__(
        self,
        *,
        rows: Optional[List[Dict[str, Any]]] = None,
        saved_by_file_id: Optional[Dict[str, Dict[str, Any]]] = None,
        file_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        """Initialize fake rows and lookup tables used by command tests."""
        self.rows = rows or []
        self.saved_by_file_id = saved_by_file_id or {}
        self.file_by_id = file_by_id or {}
        self.disconnect_count = 0
        self.requested_saved_file_ids: List[str] = []

    def get_project_file_rows(
        self, project_id: str, include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """Return project file rows and assert the command uses active rows."""
        assert project_id == PROJECT_ID
        assert include_deleted is False
        return list(self.rows)

    def get_comprehensive_analysis_results(
        self, file_id: str, file_mtime: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """Return saved analysis results keyed by file id."""
        assert file_mtime is None
        self.requested_saved_file_ids.append(file_id)
        return self.saved_by_file_id.get(file_id)

    def get_file_by_id(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Return one file row by id."""
        return self.file_by_id.get(file_id)

    def disconnect(self) -> None:
        """Track that command closes its database handle."""
        self.disconnect_count += 1


def _saved(
    *,
    missing_docstrings: Optional[List[Dict[str, Any]]] = None,
    stubs: Optional[List[Dict[str, Any]]] = None,
    total_missing_docstrings: int = 0,
) -> Dict[str, Any]:
    """Build one saved comprehensive_analysis DB payload."""
    missing_docstrings = missing_docstrings or []
    stubs = stubs or []
    return {
        "results": {
            "missing_docstrings": missing_docstrings,
            "stubs": stubs,
            "placeholders": [],
        },
        "summary": {
            "total_missing_docstrings": total_missing_docstrings,
            "total_stubs": len(stubs),
        },
        "file_mtime": 123.5,
        "analysis_date": "2026-06-26 10:00:00",
    }


def _cmd_with_db(
    tmp_path: Path,
    db: _FakeAnalysisResultsDb,
) -> ComprehensiveAnalysisResultsMCPCommand:
    """Create command instance patched to use a fake project root and DB."""
    cmd = ComprehensiveAnalysisResultsMCPCommand()
    cmd._resolve_project_root = lambda project_id: tmp_path  # type: ignore[method-assign]
    cmd._open_database = lambda: db  # type: ignore[method-assign]
    return cmd


def _project_row(file_id: str, rel: str) -> Dict[str, Any]:
    """Return a files table row fixture."""
    return {
        "id": file_id,
        "project_id": PROJECT_ID,
        "path": f"/repo/{rel}",
        "relative_path": rel,
        "deleted": 0,
    }


@pytest.fixture(autouse=True)
def _skip_project_lookup() -> Any:
    """Avoid real DB access in BaseMCPCommand project-id validation."""
    with patch.object(BaseMCPCommand, "_validate_project_id_exists", return_value=None):
        yield


@pytest.fixture(autouse=True)
def _patch_domain_files_to_fake_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route domain free-function call sites back to ``_FakeAnalysisResultsDb`` methods.

    The command calls the driver-direct free functions (stage-2 layer
    collapse), which read through ``driver.select``/``driver.execute`` -
    primitives ``_FakeAnalysisResultsDb`` does not implement (it exposes the
    old bound-method shape directly). Redirect the call sites to the fake's
    own methods instead of exercising real SQL composition.
    """
    monkeypatch.setattr(
        "code_analysis.commands.comprehensive_analysis_results_mcp.command.get_file_by_id",
        lambda driver, file_id: driver.get_file_by_id(file_id),
    )
    monkeypatch.setattr(
        "code_analysis.commands.comprehensive_analysis_results_mcp.command.get_project_file_rows",
        lambda driver, project_id, include_deleted=False: driver.get_project_file_rows(
            project_id, include_deleted=include_deleted
        ),
    )
    monkeypatch.setattr(
        "code_analysis.commands.comprehensive_analysis_results_mcp.command."
        "get_comprehensive_analysis_results",
        lambda driver, file_id, file_mtime=None: driver.get_comprehensive_analysis_results(
            file_id, file_mtime=file_mtime
        ),
    )


@pytest.mark.asyncio
async def test_project_result_key_returns_only_non_empty_saved_findings(
    tmp_path: Path,
) -> None:
    """Project-wide lookup returns saved missing_docstrings and filters empty rows."""
    rows = [
        _project_row("f1", "pkg/alpha.py"),
        _project_row("f2", "pkg/beta.py"),
        _project_row("f3", "pkg/gamma.py"),
    ]
    db = _FakeAnalysisResultsDb(
        rows=rows,
        saved_by_file_id={
            "f1": _saved(
                missing_docstrings=[
                    {"type": "file", "name": "pkg/alpha.py", "line": 1},
                    {"type": "function", "name": "load_alpha", "line": 8},
                ],
                total_missing_docstrings=2,
            ),
            "f2": _saved(missing_docstrings=[]),
            "f3": _saved(
                missing_docstrings=[
                    {"type": "class", "name": "Gamma", "line": 4},
                ],
                total_missing_docstrings=1,
            ),
        },
    )
    cmd = _cmd_with_db(tmp_path, db)

    result = await cmd.execute(
        project_id=PROJECT_ID,
        result_key="missing_docstrings",
    )

    assert isinstance(result, SuccessResult)
    assert result.data["result_key"] == "missing_docstrings"
    assert [item["file_id"] for item in result.data["items"]] == ["f1", "f3"]
    assert result.data["items"][0]["results"][1]["name"] == "load_alpha"
    assert result.data["items"][1]["summary"]["total_missing_docstrings"] == 1
    assert result.data["summary"] == {
        "files_scanned": 3,
        "files_with_saved_results": 3,
        "files_returned": 2,
        "total_matches": 2,
        "total_findings": 3,
    }
    assert result.data["pagination"] == {
        "limit": 100,
        "offset": 0,
        "total_matches": 2,
        "has_more": False,
    }
    assert db.requested_saved_file_ids == ["f1", "f2", "f3"]
    assert db.disconnect_count == 1


@pytest.mark.asyncio
async def test_project_result_key_can_include_empty_rows_and_paginate(
    tmp_path: Path,
) -> None:
    """include_empty keeps rows with empty selected lists before pagination."""
    rows = [
        _project_row("f1", "pkg/alpha.py"),
        _project_row("f2", "pkg/beta.py"),
        _project_row("f3", "pkg/gamma.py"),
    ]
    db = _FakeAnalysisResultsDb(
        rows=rows,
        saved_by_file_id={
            "f1": _saved(missing_docstrings=[{"type": "file", "line": 1}]),
            "f2": _saved(missing_docstrings=[]),
            "f3": _saved(missing_docstrings=[{"type": "class", "line": 3}]),
        },
    )
    cmd = _cmd_with_db(tmp_path, db)

    result = await cmd.execute(
        project_id=PROJECT_ID,
        result_key="missing_docstrings",
        include_empty=True,
        include_summary=False,
        limit=2,
        offset=1,
    )

    assert isinstance(result, SuccessResult)
    assert [item["file_id"] for item in result.data["items"]] == ["f2", "f3"]
    assert result.data["items"][0]["results"] == []
    assert "summary" not in result.data["items"][0]
    assert result.data["pagination"] == {
        "limit": 2,
        "offset": 1,
        "total_matches": 3,
        "has_more": False,
    }
    assert result.data["summary"]["total_findings"] == 2


@pytest.mark.asyncio
async def test_file_id_lookup_returns_full_saved_results_when_result_key_omitted(
    tmp_path: Path,
) -> None:
    """file_id mode resolves one file and returns full results_json."""
    row = _project_row("f1", "pkg/alpha.py")
    db = _FakeAnalysisResultsDb(
        file_by_id={"f1": row},
        saved_by_file_id={
            "f1": _saved(
                missing_docstrings=[{"type": "function", "name": "f", "line": 2}],
                stubs=[{"type": "pass", "name": "todo", "line": 8}],
                total_missing_docstrings=1,
            )
        },
    )
    cmd = _cmd_with_db(tmp_path, db)

    result = await cmd.execute(project_id=PROJECT_ID, file_id="f1")

    assert isinstance(result, SuccessResult)
    assert result.data["result_key"] is None
    assert result.data["items"][0]["file_id"] == "f1"
    assert result.data["items"][0]["results"]["stubs"][0]["name"] == "todo"
    assert result.data["summary"]["files_scanned"] == 1
    assert result.data["summary"]["total_findings"] == 0
    assert db.requested_saved_file_ids == ["f1"]
    assert db.disconnect_count == 1


@pytest.mark.asyncio
async def test_file_path_lookup_uses_resolver_and_returns_selected_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """file_path mode delegates path resolution and then reads saved analysis by file id."""
    row = _project_row("resolved-file-id", "pkg/resolved.py")
    db = _FakeAnalysisResultsDb(
        saved_by_file_id={
            "resolved-file-id": _saved(
                stubs=[{"type": "ellipsis", "name": "later", "line": 9}],
            )
        },
    )
    calls: List[Dict[str, Any]] = []

    def _resolve_project_file_record(**kwargs: Any) -> Dict[str, Any]:
        """Capture resolver arguments and return the prepared project row."""
        calls.append(kwargs)
        return {"file_record": row}

    monkeypatch.setattr(
        "code_analysis.commands.comprehensive_analysis_results_mcp.command.resolve_project_file_record",
        _resolve_project_file_record,
    )
    cmd = _cmd_with_db(tmp_path, db)

    result = await cmd.execute(
        project_id=PROJECT_ID,
        file_path="pkg/resolved.py",
        result_key="stubs",
    )

    assert isinstance(result, SuccessResult)
    assert calls[0]["db"] is db
    assert calls[0]["project_id"] == PROJECT_ID
    assert calls[0]["project_root"] == tmp_path
    assert calls[0]["file_path"] == "pkg/resolved.py"
    assert result.data["items"][0]["file_id"] == "resolved-file-id"
    assert result.data["items"][0]["results"] == [
        {"type": "ellipsis", "name": "later", "line": 9}
    ]
    assert db.disconnect_count == 1


@pytest.mark.asyncio
async def test_execute_rejects_mutually_exclusive_file_id_and_file_path(
    tmp_path: Path,
) -> None:
    """file_id and file_path together fail direct command validation."""
    db = _FakeAnalysisResultsDb()
    cmd = _cmd_with_db(tmp_path, db)

    result = await cmd.execute(
        project_id=PROJECT_ID,
        file_id="f1",
        file_path="pkg/alpha.py",
    )

    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "either file_id or file_path" in result.message
    assert db.disconnect_count == 0


@pytest.mark.asyncio
async def test_execute_rejects_unknown_result_key_before_db_read(tmp_path: Path) -> None:
    """result_key is schema-enforced and invalid values do not touch the DB."""
    db = _FakeAnalysisResultsDb()
    cmd = _cmd_with_db(tmp_path, db)

    result = await cmd.execute(project_id=PROJECT_ID, result_key="not_a_result")

    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "must be one of" in result.message
    assert db.requested_saved_file_ids == []
    assert db.disconnect_count == 0


@pytest.mark.asyncio
async def test_execute_rejects_invalid_limit_and_offset(tmp_path: Path) -> None:
    """Manual semantic validation covers min/max constraints documented in schema."""
    cmd = _cmd_with_db(tmp_path, _FakeAnalysisResultsDb())

    too_large = await cmd.execute(project_id=PROJECT_ID, limit=1001)
    negative_offset = await cmd.execute(project_id=PROJECT_ID, offset=-1)

    assert isinstance(too_large, ErrorResult)
    assert too_large.code == "VALIDATION_ERROR"
    assert "limit" in too_large.message
    assert isinstance(negative_offset, ErrorResult)
    assert negative_offset.code == "VALIDATION_ERROR"
    assert "offset" in negative_offset.message


@pytest.mark.asyncio
async def test_project_lookup_with_no_saved_rows_returns_empty_success(
    tmp_path: Path,
) -> None:
    """A project can have indexed files but no saved comprehensive analysis rows yet."""
    db = _FakeAnalysisResultsDb(
        rows=[
            _project_row("f1", "pkg/alpha.py"),
            _project_row("f2", "pkg/beta.py"),
        ],
        saved_by_file_id={},
    )
    cmd = _cmd_with_db(tmp_path, db)

    result = await cmd.execute(
        project_id=PROJECT_ID,
        result_key="missing_docstrings",
    )

    assert isinstance(result, SuccessResult)
    assert result.data["items"] == []
    assert result.data["summary"] == {
        "files_scanned": 2,
        "files_with_saved_results": 0,
        "files_returned": 0,
        "total_matches": 0,
        "total_findings": 0,
    }
    assert result.data["pagination"]["has_more"] is False
    assert db.requested_saved_file_ids == ["f1", "f2"]
    assert db.disconnect_count == 1


def test_schema_and_metadata_are_exposed_for_help() -> None:
    """Schema and metadata contain the public API contract for MCP help."""
    schema = ComprehensiveAnalysisResultsMCPCommand.get_schema()
    assert schema["required"] == ["project_id"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["result_key"]["enum"]
    assert "missing_docstrings" in schema["properties"]["result_key"]["enum"]
    assert schema["properties"]["limit"]["maximum"] == 1000

    meta = ComprehensiveAnalysisResultsMCPCommand.metadata()
    for key in REQUIRED_METADATA_KEYS:
        assert key in meta, f"missing metadata key: {key}"
    assert meta["name"] == "get_comprehensive_analysis_results"
    assert "comprehensive_analysis_results" in meta["detailed_description"]
    assert "missing_docstrings" in str(meta["usage_examples"])
