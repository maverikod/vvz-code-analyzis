"""
SearchMCPCommand global-search (project_id=None) schema/validation coverage
(bug — search(project_id=None) = all projects).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json

import pytest

from code_analysis.commands.search_mcp_command import SearchMCPCommand
from code_analysis.core.exceptions import ValidationError
from code_analysis.core.search_session.directory import (
    provision_search_session_directory,
)


def test_schema_project_id_is_nullable_and_not_required() -> None:
    """project_id: ["string", "null"], not in required (only "query" is)."""
    schema = SearchMCPCommand.get_schema()
    assert schema["properties"]["project_id"]["type"] == ["string", "null"]
    assert schema["required"] == ["query"]


def test_validate_params_global_search_omitted_project_id_ok() -> None:
    """Omitting project_id entirely -> validates fine, project_id stays None."""
    cmd = SearchMCPCommand()
    params = cmd.validate_params({"query": "foo"})
    assert params.get("project_id") is None


def test_validate_params_global_search_explicit_null_ok() -> None:
    """Explicit project_id=None -> validates fine, same as omission."""
    cmd = SearchMCPCommand()
    params = cmd.validate_params({"project_id": None, "query": "foo"})
    assert params.get("project_id") is None


def test_validate_params_global_search_with_grep_fails_loud() -> None:
    """project_id=None + enable_grep=true -> ValidationError, not a silent no-op."""
    cmd = SearchMCPCommand()
    with pytest.raises(ValidationError, match="grep requires project_id"):
        cmd.validate_params({"query": "foo", "enable_grep": True})


def test_validate_params_explicit_project_id_still_checks_existence(monkeypatch) -> None:
    """Explicit project_id still goes through the normal existence check."""
    calls = []

    def _fake_validate(project_id: str) -> None:
        calls.append(project_id)

    monkeypatch.setattr(
        "code_analysis.commands.search_mcp_command.BaseMCPCommand._validate_project_id_exists",
        staticmethod(_fake_validate),
    )
    cmd = SearchMCPCommand()
    cmd.validate_params({"project_id": "pid-1", "query": "foo"})
    assert calls == ["pid-1"]


def test_read_session_notes_missing_file_returns_empty_list(tmp_path) -> None:
    """No notes.json yet -> empty list, not an error."""
    layout = provision_search_session_directory(
        sessions_root=tmp_path / "sessions", search_id="s1"
    )
    assert SearchMCPCommand._read_session_notes(layout) == []


def test_read_session_notes_reads_written_notes(tmp_path) -> None:
    """notes.json with a notes list -> returned as strings."""
    layout = provision_search_session_directory(
        sessions_root=tmp_path / "sessions", search_id="s2"
    )
    (layout.root / "notes.json").write_text(
        json.dumps({"notes": ["semantic phase skipped: FAISS backend"]})
    )
    assert SearchMCPCommand._read_session_notes(layout) == [
        "semantic phase skipped: FAISS backend"
    ]
