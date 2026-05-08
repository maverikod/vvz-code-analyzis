"""
Group 08: ``fulltext_search`` finds indexed Markdown; semantic filters ``docs_markdown``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from code_analysis.commands.semantic_search_mcp import (
    _omit_semantic_hit_for_docs_markdown,
)
from code_analysis.core.database_client.protocol import SuccessResult
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
def tmp_root() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def project_id() -> str:
    return str(uuid.uuid4())


def test_omit_semantic_hit_docs_markdown_when_vectorize_off() -> None:
    assert _omit_semantic_hit_for_docs_markdown(
        "docs_markdown",
        docs_markdown_vectorize_enabled=False,
    )


def test_omit_semantic_hit_docs_markdown_when_vectorize_on() -> None:
    assert not _omit_semantic_hit_for_docs_markdown(
        "docs_markdown",
        docs_markdown_vectorize_enabled=True,
    )


def test_omit_semantic_hit_non_docs_source_never_omitted() -> None:
    assert not _omit_semantic_hit_for_docs_markdown(
        "docstring",
        docs_markdown_vectorize_enabled=False,
    )


def test_indexed_markdown_fulltext_search_finds_body_token(
    tmp_root: Path, project_id: str
) -> None:
    """After index_file, ``full_text_search`` matches unique body text in ``code_content``."""
    db_path = tmp_root / "ft.db"
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
        md_path = doc_dir / "guide.md"
        unique = "xyZZyUniqueMdFulltextToken42"
        body = f"# Guide\n\nParagraph with enough text. {unique}\n"
        md_path.write_text(body, encoding="utf-8")

        mtime = os.path.getmtime(md_path)
        client.add_file(
            str(md_path.resolve()),
            lines=len(body.splitlines()),
            last_modified=mtime,
            has_docstring=True,
            project_id=project_id,
        )
        client.execute(
            "UPDATE files SET needs_chunking = 1 WHERE path = ?",
            (str(md_path.resolve()),),
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
        handlers = RPCHandlers(driver)  # type: ignore[arg-type]
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
    finally:
        driver.disconnect()

    reader = sqlite_inprocess_database_client(db_path, backup_dir=backup_dir)
    try:
        rows = (
            reader.execute(
                "SELECT COUNT(*) AS c FROM code_content WHERE entity_type = 'file'"
            ).get("data")
            or []
        )
        assert int(rows[0].get("c") or 0) >= 1
        hits = reader.full_text_search(unique, project_id, limit=20)
        assert any(unique in str(h.get("content") or "") for h in hits)
    finally:
        reader.disconnect()
