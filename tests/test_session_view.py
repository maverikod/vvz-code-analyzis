"""
Tests for session_view core builder and MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.hooks import hooks
from mcp_proxy_adapter.commands.result import SuccessResult

import code_analysis.hooks  # noqa: F401
from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.sessions.session_view_command import SessionViewCommand
from code_analysis.core.client_sessions import (
    create_client_session,
    ensure_client_session_tables,
    open_session_file,
)
from code_analysis.core.subordinate_sessions import (
    create_subordinate_session,
    ensure_subordinate_session_tables,
)
from code_analysis.core.session_view import (
    build_session_view,
    format_project_presentation,
    resolve_server_presentation_for_uuid,
)
from tests.sqlite_in_process_legacy_facade import make_sqlite_in_process_legacy_facade

SERVER_UUID = "880e8400-e29b-41d4-a716-446655440003"
PARENT_ID = "11111111-1111-4111-8111-111111111111"


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _register_session_view_command() -> None:
    """Return register session view command."""
    hooks.execute_custom_commands_hooks(registry)


def test_format_project_presentation_name_and_comment() -> None:
    """Verify test format project presentation name and comment."""
    label = format_project_presentation(
        project_id="pid",
        project_name="demo",
        project_comment="note",
    )
    assert label == "demo — note"


def test_resolve_server_presentation_for_local_uuid() -> None:
    """Verify test resolve server presentation for local uuid."""
    cfg = {
        "registration": {"instance_uuid": SERVER_UUID},
        "server_presentation": {
            "title": "Test Server",
            "description": "d",
            "version": "9",
        },
    }
    pres = resolve_server_presentation_for_uuid(
        SERVER_UUID,
        current_server_uuid=SERVER_UUID,
        app_config=cfg,
    )
    assert pres is not None
    assert pres["title"] == "Test Server"


def test_resolve_server_presentation_foreign_uuid_is_none() -> None:
    """Verify test resolve server presentation foreign uuid is none."""
    assert (
        resolve_server_presentation_for_uuid(
            "99999999-9999-4999-8999-999999999999",
            current_server_uuid=SERVER_UUID,
            app_config={"registration": {"instance_uuid": SERVER_UUID}},
        )
        is None
    )


def test_build_session_view_with_locks_and_subordinates() -> None:
    """Verify test build session view with locks and subordinates."""
    with tempfile.TemporaryDirectory() as td:
        facade, client = make_sqlite_in_process_legacy_facade(Path(td))
        try:
            conn = sqlite3.connect(str(Path(td) / "test.db"))
            conn.row_factory = sqlite3.Row
            ensure_client_session_tables(conn)
            ensure_subordinate_session_tables(conn)
            project_id = str(uuid.uuid4())
            file_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO projects (id, root_path, name, comment) VALUES (?, ?, ?, ?)",
                (project_id, "/tmp/proj", "demo_proj", "demo comment"),
            )
            conn.execute(
                "INSERT INTO files (id, project_id, path, relative_path) "
                "VALUES (?, ?, ?, ?)",
                (file_id, project_id, "/tmp/proj/src/a.py", "src/a.py"),
            )
            conn.commit()
            conn.close()

            parent = create_client_session(facade, comment="leading session")
            parent_id = str(parent["session_id"])
            open_session_file(facade, parent_id, project_id, file_id)
            create_subordinate_session(
                facade,
                parent_session_id=parent_id,
                server_uuid=SERVER_UUID,
                comment="link note",
            )

            view = build_session_view(
                facade,
                parent_id,
                app_config={
                    "registration": {"instance_uuid": SERVER_UUID},
                    "server_presentation": {"title": "Local"},
                },
            )
            assert view["locked_file_count"] == 1
            groups = view["locked_files_by_project"]
            assert len(groups) == 1
            assert groups[0]["project_id"] == project_id
            assert groups[0]["project_presentation"] == "demo_proj — demo comment"
            assert groups[0]["files"][0]["file_id"] == file_id
            assert groups[0]["files"][0]["file_path"] == "src/a.py"

            subs = view["subordinate_sessions"]
            assert len(subs) == 1
            assert subs[0]["session_id"] == parent_id
            assert subs[0]["session_presentation"] == "leading session"
            assert subs[0]["server_presentation"]["title"] == "Local"
            assert subs[0]["link_comment"] == "link note"
        finally:
            client.disconnect()


@pytest.mark.asyncio
async def test_session_view_command_execute() -> None:
    """Verify test session view command execute."""
    payload = {
        "session_id": PARENT_ID,
        "locked_files_by_project": [],
        "locked_file_count": 0,
        "subordinate_sessions": [],
        "subordinate_session_count": 0,
    }
    mock_db = MagicMock()
    config = {
        "registration": {"instance_uuid": SERVER_UUID},
        "security": {"policy": "disabled"},
    }
    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ),
        patch.object(BaseMCPCommand, "_get_raw_config", return_value=config),
        patch(
            "code_analysis.commands.sessions.session_view_command.touch_or_error",
            return_value=None,
        ),
        patch(
            "code_analysis.commands.sessions.session_view_command.enforce_security_policy",
            return_value=None,
        ),
        patch(
            "code_analysis.commands.sessions.session_view_command.build_session_view",
            return_value=payload,
        ) as build_fn,
    ):
        cmd = SessionViewCommand()
        result = await cmd.execute(session_id=PARENT_ID)

    assert isinstance(result, SuccessResult)
    assert result.data == payload
    build_fn.assert_called_once_with(mock_db, PARENT_ID, app_config=config)


def test_session_view_registered() -> None:
    """Verify test session view registered."""
    cls = registry.get_command("session_view")
    assert cls is SessionViewCommand
