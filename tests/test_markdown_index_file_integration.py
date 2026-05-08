"""
Integration: Markdown index_file persists ``code_chunks`` as DocBlock / docs_markdown.

Indexed Markdown bodies are mirrored into ``code_content`` / FTS so ``fulltext_search`` can find them (Group 08).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pytest

from code_analysis.core.database_client.protocol import ErrorResult, SuccessResult
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers
from tests.sqlite_inprocess_database import sqlite_inprocess_database_client


DOCS_INDEXING_ENABLED = {
    "enabled": True,
    "roots": ["docs"],
    "include": ["**/*.md"],
    "exclude": [],
}


@pytest.fixture
def tmp_root():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def project_id() -> str:
    return str(uuid.uuid4())


def test_index_file_markdown_persists_docblock_chunks(tmp_root: Path, project_id: str):
    """Eligible .md via index_file yields code_chunks with chunk_type DocBlock."""
    db_path = tmp_root / "t.db"
    backup_dir = tmp_root / "bk"
    original = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    client = None
    try:
        client = sqlite_inprocess_database_client(db_path, backup_dir=backup_dir)
        client.execute(
            "INSERT INTO projects (id, root_path, name, updated_at) "
            "VALUES (?, ?, ?, julianday('now'))",
            (project_id, str(tmp_root.resolve()), tmp_root.name),
        )

        doc_dir = tmp_root / "docs"
        doc_dir.mkdir(parents=True)
        md_path = doc_dir / "hello.md"
        body = "# Title\n\nParagraph with enough text for doc chunking pipeline test.\n"
        md_path.write_text(body, encoding="utf-8")

        mtime = os.path.getmtime(md_path)
        file_id = client.add_file(
            str(md_path.resolve()),
            lines=len(body.splitlines()),
            last_modified=mtime,
            has_docstring=True,
            project_id=project_id,
        )
        client.execute(
            "UPDATE files SET needs_chunking = 1 WHERE id = ?",
            (file_id,),
        )
    finally:
        if client is not None:
            client.disconnect()
        if original is None:
            os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
        else:
            os.environ["CODE_ANALYSIS_DB_WORKER"] = original

    srv_cfg = tmp_root / "srv_config.json"
    srv_cfg.write_text("{}", encoding="utf-8")

    driver = create_driver(
        "sqlite",
        {"path": str(db_path), "backup_dir": str(backup_dir.resolve())},
    )
    try:
        handlers = RPCHandlers(driver)
        res = handlers.handle_index_file(
            {
                "file_path": str(md_path.resolve()),
                "project_id": project_id,
                "docs_indexing": DOCS_INDEXING_ENABLED,
                "server_config_path": str(srv_cfg),
            }
        )
        assert isinstance(res, SuccessResult)
        assert res.data is not None
        assert res.data.get("success") is True

        r = driver.execute(
            """
            SELECT cc.chunk_type, cc.source_type, cc.chunk_text
            FROM code_chunks cc
            JOIN files f ON f.id = cc.file_id
            WHERE f.path = ?
            """,
            (str(md_path.resolve()),),
            None,
        )
        rows = r.get("data") or []
        assert len(rows) >= 1
        assert rows[0].get("chunk_type") == "DocBlock"
        assert rows[0].get("source_type") == "docs_markdown"
        assert "Title" in (rows[0].get("chunk_text") or "")
    finally:
        driver.disconnect()


def test_index_file_markdown_without_docs_indexing_returns_error(
    tmp_root: Path, project_id: str
):
    """Markdown without docs_indexing RPC param yields configuration error (analyze_file)."""
    db_path = tmp_root / "u.db"
    backup_dir = tmp_root / "bk2"
    md_path = tmp_root / "readme.md"
    original = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    client = None
    try:
        client = sqlite_inprocess_database_client(db_path, backup_dir=backup_dir)
        client.execute(
            "INSERT INTO projects (id, root_path, name, updated_at) "
            "VALUES (?, ?, ?, julianday('now'))",
            (project_id, str(tmp_root.resolve()), tmp_root.name),
        )
        md_path.write_text("# x\n", encoding="utf-8")
        mtime = os.path.getmtime(md_path)
        client.add_file(
            str(md_path.resolve()),
            1,
            mtime,
            True,
            project_id,
        )
    finally:
        if client is not None:
            client.disconnect()
        if original is None:
            os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
        else:
            os.environ["CODE_ANALYSIS_DB_WORKER"] = original

    driver = create_driver(
        "sqlite",
        {"path": str(db_path), "backup_dir": str(backup_dir.resolve())},
    )
    try:
        handlers = RPCHandlers(driver)
        res = handlers.handle_index_file(
            {
                "file_path": str(md_path.resolve()),
                "project_id": project_id,
            }
        )
        assert isinstance(res, ErrorResult)
        assert res.description
    finally:
        driver.disconnect()


@pytest.mark.asyncio
async def test_index_file_markdown_under_running_asyncio_loop(
    tmp_root: Path, project_id: str
) -> None:
    """Regression: Markdown index must succeed when RPC runs on an asyncio thread.

    In-process ``index_file`` (PostgreSQL worker or this sqlite test) can execute
    on the same thread as a running event loop; Markdown persistence must not call
    :func:`asyncio.run` on that thread.
    """
    db_path = tmp_root / "async_loop.db"
    backup_dir = tmp_root / "bk_async"
    original = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    client = None
    try:
        client = sqlite_inprocess_database_client(db_path, backup_dir=backup_dir)
        client.execute(
            "INSERT INTO projects (id, root_path, name, updated_at) "
            "VALUES (?, ?, ?, julianday('now'))",
            (project_id, str(tmp_root.resolve()), tmp_root.name),
        )

        doc_dir = tmp_root / "docs"
        doc_dir.mkdir(parents=True)
        md_path = doc_dir / "async_loop.md"
        body = "# Async loop case\n\nEnough text for doc chunking under asyncio.\n"
        md_path.write_text(body, encoding="utf-8")

        mtime = os.path.getmtime(md_path)
        file_id = client.add_file(
            str(md_path.resolve()),
            lines=len(body.splitlines()),
            last_modified=mtime,
            has_docstring=True,
            project_id=project_id,
        )
        client.execute(
            "UPDATE files SET needs_chunking = 1 WHERE id = ?",
            (file_id,),
        )
    finally:
        if client is not None:
            client.disconnect()
        if original is None:
            os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
        else:
            os.environ["CODE_ANALYSIS_DB_WORKER"] = original

    srv_cfg = tmp_root / "srv_config_async.json"
    srv_cfg.write_text("{}", encoding="utf-8")

    driver = create_driver(
        "sqlite",
        {"path": str(db_path), "backup_dir": str(backup_dir.resolve())},
    )
    try:
        handlers = RPCHandlers(driver)
        res = handlers.handle_index_file(
            {
                "file_path": str(md_path.resolve()),
                "project_id": project_id,
                "docs_indexing": DOCS_INDEXING_ENABLED,
                "server_config_path": str(srv_cfg),
            }
        )
        assert isinstance(res, SuccessResult)
        assert res.data is not None
        assert res.data.get("success") is True

        r = driver.execute(
            """
            SELECT COUNT(*) AS n
            FROM code_chunks cc
            JOIN files f ON f.id = cc.file_id
            WHERE f.path = ?
            """,
            (str(md_path.resolve()),),
            None,
        )
        rows = r.get("data") or []
        assert int(rows[0].get("n") or 0) >= 1
    finally:
        driver.disconnect()
