"""
Subordinate session table migration and CRUD on SQLite.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3
import tempfile
import uuid
from pathlib import Path

import pytest

from code_analysis.core.client_sessions import (
    create_client_session,
    ensure_client_session_tables,
)
from code_analysis.core.subordinate_sessions import (
    SubordinateSessionAlreadyExistsError,
    SubordinateSessionNotFoundError,
    create_subordinate_session,
    delete_subordinate_session,
    ensure_subordinate_session_tables,
    get_subordinate_session,
    list_subordinate_sessions,
    update_subordinate_session,
)
from tests.sqlite_in_process_legacy_facade import make_sqlite_in_process_legacy_facade

SERVER_UUID = "880e8400-e29b-41d4-a716-446655440003"


def test_ensure_subordinate_session_tables_idempotent() -> None:
    with tempfile.TemporaryDirectory() as td:
        conn = sqlite3.connect(f"{td}/test.db")
        ensure_client_session_tables(conn)
        ensure_subordinate_session_tables(conn)
        ensure_subordinate_session_tables(conn)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='subordinate_sessions'"
        )
        assert cur.fetchone() is not None
        conn.close()


def test_subordinate_session_crud() -> None:
    with tempfile.TemporaryDirectory() as td:
        facade, client = make_sqlite_in_process_legacy_facade(Path(td))
        try:
            parent = create_client_session(facade, comment="leading")
            parent_id = str(parent["session_id"])

            row = create_subordinate_session(
                facade,
                parent_session_id=parent_id,
                server_uuid=SERVER_UUID,
                comment="worker",
            )
            assert row["comment"] == "worker"
            assert row["parent_session_id"] == parent_id

            fetched = get_subordinate_session(
                facade,
                parent_session_id=parent_id,
                server_uuid=SERVER_UUID,
            )
            assert fetched == row

            updated = update_subordinate_session(
                facade,
                parent_session_id=parent_id,
                server_uuid=SERVER_UUID,
                comment="renamed",
            )
            assert updated["comment"] == "renamed"

            listed = list_subordinate_sessions(facade, parent_session_id=parent_id)
            assert len(listed) == 1
            assert listed[0]["comment"] == "renamed"

            deleted = delete_subordinate_session(
                facade,
                parent_session_id=parent_id,
                server_uuid=SERVER_UUID,
            )
            assert deleted["deleted"] is True
            assert (
                get_subordinate_session(
                    facade,
                    parent_session_id=parent_id,
                    server_uuid=SERVER_UUID,
                )
                is None
            )
        finally:
            client.disconnect()


def test_create_duplicate_raises() -> None:
    with tempfile.TemporaryDirectory() as td:
        facade, client = make_sqlite_in_process_legacy_facade(Path(td))
        try:
            parent = create_client_session(facade, comment="parent")
            kwargs = {
                "parent_session_id": str(parent["session_id"]),
                "server_uuid": SERVER_UUID,
                "comment": "x",
            }
            create_subordinate_session(facade, **kwargs)
            with pytest.raises(SubordinateSessionAlreadyExistsError):
                create_subordinate_session(facade, **kwargs)
        finally:
            client.disconnect()


def test_update_missing_raises() -> None:
    with tempfile.TemporaryDirectory() as td:
        facade, client = make_sqlite_in_process_legacy_facade(Path(td))
        try:
            with pytest.raises(SubordinateSessionNotFoundError):
                update_subordinate_session(
                    facade,
                    parent_session_id=str(uuid.uuid4()),
                    server_uuid=SERVER_UUID,
                    comment="nope",
                )
        finally:
            client.disconnect()
