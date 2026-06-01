"""
Integration tests for session_git_* MCP commands (C-014).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.universal_file_edit.errors import SESSION_NOT_FOUND
from code_analysis.commands.universal_file_edit.session_git_diff_command import (
    SessionGitDiffCommand,
)
from code_analysis.commands.universal_file_edit.session_git_log_command import (
    SessionGitLogCommand,
)
from code_analysis.commands.universal_file_edit.session_git_revert_command import (
    SessionGitRevertCommand,
)
from code_analysis.commands.universal_file_edit.session_git_show_command import (
    SessionGitShowCommand,
)
from code_analysis.commands.universal_file_edit.session_git_status_command import (
    SessionGitStatusCommand,
)
from code_analysis.core.edit_session.edit_session import EditSession
from code_analysis.core.tree_lifecycle.builder import TreeBuilder
from code_analysis.core.tree_lifecycle.checksum import compute_content_checksum

PROJECT_ID = "00000000-0000-0000-0000-000000000013"
REL = "session/git_demo.json"
INITIAL_JSON = '{"value": 1}\n'


@pytest.fixture
def mutated_json_session(tmp_path: Path) -> Generator[EditSession, None, None]:
    source = tmp_path / REL
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(INITIAL_JSON, encoding="utf-8")
    checksum = compute_content_checksum(INITIAL_JSON)
    TreeBuilder.build(
        content=INITIAL_JSON,
        source_abs=source,
        file_path=REL,
        content_checksum=checksum,
    )
    session = EditSession.open(
        source_abs=source,
        project_root=tmp_path,
        file_path=REL,
    )
    try:
        session.apply_valid_tree_mutation(
            lambda t: t.replace('"value": 1', '"value": 2')
        )
        yield session
    finally:
        if session.is_open:
            session.close()


@pytest.mark.asyncio
async def test_session_git_log_returns_commits(
    mutated_json_session: EditSession,
) -> None:
    cmd = SessionGitLogCommand()
    res = await cmd.execute(
        project_id=PROJECT_ID,
        session_id=mutated_json_session.session_id,
    )
    assert isinstance(res, SuccessResult)
    commits = res.data["commits"]
    assert len(commits) >= 2
    for entry in commits:
        assert {"hash", "message", "timestamp"}.issubset(entry.keys())
    assert len(commits[0]["hash"]) == 40
    int(commits[0]["hash"], 16)


@pytest.mark.asyncio
async def test_session_git_diff_tree_mode(
    mutated_json_session: EditSession,
) -> None:
    commits = mutated_json_session.session_repo.log()
    rev_new = commits[0].hash
    rev_old = commits[1].hash
    cmd = SessionGitDiffCommand()
    res = await cmd.execute(
        project_id=PROJECT_ID,
        session_id=mutated_json_session.session_id,
        mode="tree",
        rev_a=rev_old,
        rev_b=rev_new,
    )
    assert isinstance(res, SuccessResult)
    diff = res.data["diff"]
    assert "tree@" in diff or "---" in diff


@pytest.mark.asyncio
async def test_session_git_diff_source_mode(
    mutated_json_session: EditSession,
) -> None:
    rev_a = mutated_json_session.session_repo.log()[-1].hash
    res = await SessionGitDiffCommand().execute(
        project_id=PROJECT_ID,
        session_id=mutated_json_session.session_id,
        mode="source",
        rev_a=rev_a,
    )
    assert isinstance(res, SuccessResult)
    assert "in-session-source" in res.data["diff"]


@pytest.mark.asyncio
async def test_session_git_show(mutated_json_session: EditSession) -> None:
    rev = mutated_json_session.session_repo.log()[0].hash
    res = await SessionGitShowCommand().execute(
        project_id=PROJECT_ID,
        session_id=mutated_json_session.session_id,
        rev=rev,
    )
    assert isinstance(res, SuccessResult)
    content = res.data["content"]
    assert "---TREE---" in content or "value" in content


@pytest.mark.asyncio
async def test_session_git_status(mutated_json_session: EditSession) -> None:
    res = await SessionGitStatusCommand().execute(
        project_id=PROJECT_ID,
        session_id=mutated_json_session.session_id,
    )
    assert isinstance(res, SuccessResult)
    assert res.data["clean"] is True


@pytest.mark.asyncio
async def test_missing_session_id_errors() -> None:
    bogus = "00000000-0000-4000-8000-000000000099"
    rev = "a" * 40
    cases = [
        (SessionGitLogCommand, {"project_id": PROJECT_ID, "session_id": bogus}),
        (
            SessionGitDiffCommand,
            {
                "project_id": PROJECT_ID,
                "session_id": bogus,
                "mode": "tree",
                "rev_a": rev,
                "rev_b": "b" * 40,
            },
        ),
        (
            SessionGitShowCommand,
            {"project_id": PROJECT_ID, "session_id": bogus, "rev": rev},
        ),
        (SessionGitStatusCommand, {"project_id": PROJECT_ID, "session_id": bogus}),
        (
            SessionGitRevertCommand,
            {"project_id": PROJECT_ID, "session_id": bogus, "rev": rev},
        ),
    ]
    for cmd_cls, params in cases:
        res = await cmd_cls().execute(**params)
        assert isinstance(res, ErrorResult)
        assert res.code == SESSION_NOT_FOUND
