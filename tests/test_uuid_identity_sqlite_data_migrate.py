"""
SQLite UUID migration Phases 3–5 / Phase 6 (Step 11 Block E): dry-run, integration, FTS rebuild.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any

import pytest

from code_analysis.core.database.migrations.uuid_identity_migration_common import (
    UuidMigrationError,
)
from code_analysis.core.database.migrations.uuid_identity_migration import (
    run_uuid_migration_phase2_build_mappings,
)
from code_analysis.core.database.migrations.uuid_identity_postgres_data_migrate import (
    MIGRATED_TABLES_COPY_ORDER,
)
from code_analysis.core.database.migrations.uuid_identity_sqlite_data_migrate import (
    build_copy_insert_sql_sqlite,
    build_shadow_table_ddl_sqlite,
    run_uuid_migration_phase6_swap_sqlite,
    run_uuid_migration_phases_3_to_5_sqlite,
)
from code_analysis.core.database.schema_creation_migrate import (
    run_uuid_migration_phases_3_to_5_sqlite as facade_sqlite_p345,
)

# Legacy INTEGER PK business tables; TEXT UUID for projects / watch_dirs (Group 1).
# Columns align with Phase 4 INSERT…SELECT from uuid_identity_postgres_data_migrate.
_LEGACY_P345_SCHEMA = """
PRAGMA foreign_keys=OFF;

CREATE TABLE watch_dirs (
    id TEXT PRIMARY KEY,
    name TEXT
);

CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    root_path TEXT,
    watch_dir_id TEXT
);

CREATE TABLE files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    watch_dir_id TEXT,
    path TEXT NOT NULL DEFAULT '',
    relative_path TEXT,
    lines INTEGER,
    last_modified REAL,
    has_docstring INTEGER,
    deleted INTEGER DEFAULT 0,
    original_path TEXT,
    version_dir TEXT,
    needs_chunking INTEGER DEFAULT 0,
    created_at REAL,
    updated_at REAL
);

CREATE TABLE classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    name TEXT,
    line INTEGER DEFAULT 1,
    end_line INTEGER,
    cst_node_id TEXT,
    docstring TEXT,
    bases TEXT,
    created_at REAL
);

CREATE TABLE methods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL,
    name TEXT,
    line INTEGER DEFAULT 1,
    end_line INTEGER,
    cst_node_id TEXT,
    args TEXT,
    docstring TEXT,
    is_abstract INTEGER DEFAULT 0,
    has_pass INTEGER DEFAULT 0,
    has_not_implemented INTEGER DEFAULT 0,
    complexity INTEGER,
    created_at REAL
);

CREATE TABLE functions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    name TEXT,
    line INTEGER DEFAULT 1,
    end_line INTEGER,
    cst_node_id TEXT,
    args TEXT,
    docstring TEXT,
    complexity INTEGER,
    created_at REAL
);

CREATE TABLE entity_cross_ref (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caller_class_id INTEGER,
    caller_method_id INTEGER,
    caller_function_id INTEGER,
    callee_class_id INTEGER,
    callee_method_id INTEGER,
    callee_function_id INTEGER,
    ref_type TEXT DEFAULT 'call',
    file_id INTEGER,
    line INTEGER,
    created_at REAL
);

CREATE TABLE imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    name TEXT DEFAULT '',
    module TEXT,
    import_type TEXT DEFAULT 'direct',
    line INTEGER DEFAULT 1,
    created_at REAL
);

CREATE TABLE issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER,
    project_id TEXT,
    class_id INTEGER,
    function_id INTEGER,
    method_id INTEGER,
    issue_type TEXT DEFAULT '',
    line INTEGER,
    description TEXT,
    metadata TEXT,
    created_at REAL
);

CREATE TABLE usages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    line INTEGER DEFAULT 1,
    usage_type TEXT DEFAULT 'ref',
    target_type TEXT DEFAULT 'x',
    target_class TEXT,
    target_name TEXT DEFAULT 'n',
    context TEXT,
    created_at REAL
);

CREATE TABLE code_content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    entity_name TEXT,
    content TEXT DEFAULT '',
    docstring TEXT,
    created_at REAL
);

CREATE TABLE ast_trees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    ast_json TEXT DEFAULT '{}',
    ast_hash TEXT DEFAULT 'h',
    file_mtime REAL DEFAULT 0,
    created_at REAL,
    updated_at REAL
);

CREATE TABLE cst_trees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    cst_code TEXT DEFAULT '',
    cst_hash TEXT DEFAULT 'h',
    file_mtime REAL DEFAULT 0,
    created_at REAL,
    updated_at REAL
);

CREATE TABLE vector_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    vector_id INTEGER NOT NULL,
    vector_dim INTEGER NOT NULL DEFAULT 384,
    embedding_model TEXT,
    created_at REAL
);

CREATE TABLE code_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    chunk_uuid TEXT NOT NULL DEFAULT 'cu',
    chunk_type TEXT DEFAULT 't',
    chunk_text TEXT DEFAULT '',
    chunk_ordinal INTEGER,
    vector_id INTEGER,
    embedding_model TEXT,
    bm25_score REAL,
    embedding_vector TEXT,
    token_count INTEGER,
    class_id INTEGER,
    function_id INTEGER,
    method_id INTEGER,
    line INTEGER,
    ast_node_type TEXT,
    source_type TEXT,
    binding_level INTEGER DEFAULT 0,
    created_at REAL,
    updated_at REAL,
    vectorization_skipped INTEGER DEFAULT 0
);

CREATE TABLE code_duplicates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    duplicate_hash TEXT DEFAULT 'x',
    similarity REAL NOT NULL DEFAULT 1.0,
    created_at REAL
);

CREATE TABLE duplicate_occurrences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    duplicate_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    start_line INTEGER DEFAULT 1,
    end_line INTEGER DEFAULT 1,
    code_snippet TEXT,
    ast_node_id INTEGER,
    created_at REAL
);

CREATE TABLE comprehensive_analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    file_mtime REAL DEFAULT 0,
    results_json TEXT DEFAULT '{}',
    summary_json TEXT DEFAULT '{}',
    created_at REAL,
    updated_at REAL
);

CREATE TABLE file_tree_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    source_payload TEXT DEFAULT '',
    file_mtime REAL DEFAULT 0,
    created_at REAL,
    updated_at REAL
);

CREATE TABLE file_tree_snapshot_roots (
    snapshot_id INTEGER NOT NULL PRIMARY KEY,
    root_node_id TEXT NOT NULL
);

CREATE TABLE file_tree_snapshot_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL,
    node_id TEXT NOT NULL,
    parent_node_id TEXT,
    child_index INTEGER DEFAULT 0
);

CREATE TABLE indexing_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    error_type TEXT,
    error_message TEXT,
    created_at REAL
);
"""


class _SqliteDb:
    """Represent SqliteDb."""

    _driver_type = "sqlite"

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Initialize the instance."""
        self._conn = conn

    def _execute(self, sql: str, params: Any = None) -> None:
        """Return execute."""
        self._conn.execute(sql, params or ())

    def _fetchone(self, sql: str, params: Any = None):
        """Return fetchone."""
        return self._conn.execute(sql, params or ()).fetchone()

    def _fetchall(self, sql: str, params: Any = None):
        """Return fetchall."""
        return self._conn.execute(sql, params or ()).fetchall()

    def _commit(self) -> None:
        """Return commit."""
        self._conn.commit()


def _scalar(db: _SqliteDb, sql: str) -> int:
    """Return scalar."""
    r = db._fetchone(sql)
    if not r:
        return 0
    return int(r[0])


def _seed_graph(db: _SqliteDb) -> None:
    """Return seed graph."""
    w, p = str(uuid.uuid4()), str(uuid.uuid4())
    db._execute("INSERT INTO watch_dirs (id, name) VALUES (?, ?)", (w, "wd"))
    db._execute(
        "INSERT INTO projects (id, root_path, watch_dir_id) VALUES (?,?,?)",
        (p, "/r", w),
    )
    db._execute(
        "INSERT INTO files (project_id, watch_dir_id, path, relative_path) VALUES (?,?,?,?)",
        (p, w, "m.py", "m.py"),
    )
    db._commit()
    fid = int(db._fetchone("SELECT MAX(id) FROM files")[0])
    db._execute(
        "INSERT INTO classes (file_id, name, line) VALUES (?,?,?)", (fid, "C", 1)
    )
    db._commit()
    cid = int(db._fetchone("SELECT MAX(id) FROM classes")[0])
    cu = str(uuid.uuid4())
    db._execute(
        "INSERT INTO code_chunks (file_id, project_id, chunk_uuid, chunk_type, chunk_text, vector_id) "
        "VALUES (?,?,?,?,?,?)",
        (fid, p, cu, "docstring", "x", 777),
    )
    db._commit()
    chunk_pk = int(db._fetchone("SELECT MAX(id) FROM code_chunks")[0])
    db._execute(
        "INSERT INTO code_content (file_id, entity_type, entity_id, content, entity_name) "
        "VALUES (?,?,?,?,?)",
        (fid, "class", cid, "body", "C"),
    )
    db._execute(
        "INSERT INTO vector_index (project_id, entity_type, entity_id, vector_id, vector_dim) "
        "VALUES (?,?,?,?,?)",
        (p, "chunk", chunk_pk, 9999, 384),
    )
    db._commit()


def test_sqlite_copy_sql_has_no_postgres_casts() -> None:
    """Verify test sqlite copy sql has no postgres casts."""
    for stmt in build_copy_insert_sql_sqlite():
        assert "::" not in stmt


def test_sqlite_shadow_ddl_uses_text_pks_not_postgres_uuid_type() -> None:
    """Verify test sqlite shadow ddl uses text pks not postgres uuid type."""
    ddl = "\n".join(build_shadow_table_ddl_sqlite())
    assert "uuid_mig_new_files" in ddl
    upper = ddl.upper()
    assert "UUID PRIMARY KEY" not in upper
    assert "::" not in ddl


def test_phases_345_dry_run_sql_log_no_execute() -> None:
    """Verify test phases 345 dry run sql log no execute."""

    class _NoExec(_SqliteDb):
        """Represent NoExec."""

        def __init__(self) -> None:
            """Initialize the instance."""
            pass

        def _execute(self, *a: Any, **k: Any) -> None:
            """Return execute."""
            raise AssertionError("dry-run must not execute")

        def _fetchone(self, *a: Any, **k: Any) -> Any:
            """Return fetchone."""
            raise AssertionError("dry-run must not fetch")

        def _commit(self) -> None:
            """Return commit."""
            raise AssertionError("dry-run must not commit")

    stub = _NoExec()
    stub._driver_type = "sqlite"
    report = run_uuid_migration_phases_3_to_5_sqlite(
        stub, dry_run=True, skip_mapping_validation=True
    )
    assert report.backend == "sqlite"
    assert report.statements_executed == 0
    assert any(
        "uuid_mig_new_files" in s and "CREATE TABLE" in s for s in report.sql_log
    )
    assert any("INSERT INTO uuid_mig_new_files" in s for s in report.sql_log)


def test_facade_delegates_to_sqlite_module() -> None:
    """Verify test facade delegates to sqlite module."""

    class _NoExec(_SqliteDb):
        """Represent NoExec."""

        def __init__(self) -> None:
            """Initialize the instance."""
            pass

        def _execute(self, *a: Any, **k: Any) -> None:
            """Return execute."""
            raise AssertionError("dry-run must not execute")

        def _fetchone(self, *a: Any, **k: Any) -> Any:
            """Return fetchone."""
            raise AssertionError("dry-run must not fetch")

        def _commit(self) -> None:
            """Return commit."""
            raise AssertionError("dry-run must not commit")

    stub = _NoExec()
    stub._driver_type = "sqlite"
    r = facade_sqlite_p345(stub, dry_run=True, skip_mapping_validation=True)
    assert r.dry_run is True


def test_phases_345_integration_row_counts_and_idempotency(tmp_path: Path) -> None:
    """Verify test phases 345 integration row counts and idempotency."""
    path = Path(tmp_path) / "mig.sqlite"
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_LEGACY_P345_SCHEMA)
        db = _SqliteDb(conn)
        _seed_graph(db)
        run_uuid_migration_phase2_build_mappings(db, skip_preflight=True)

        r1 = run_uuid_migration_phases_3_to_5_sqlite(db, skip_mapping_validation=True)
        assert r1.dry_run is False
        assert (
            r1.row_counts_source_vs_shadow["files"][0]
            == r1.row_counts_source_vs_shadow["files"][1]
        )

        r2 = run_uuid_migration_phases_3_to_5_sqlite(db, skip_mapping_validation=True)
        assert (
            r2.row_counts_source_vs_shadow["files"]
            == r1.row_counts_source_vs_shadow["files"]
        )

        new_fid = db._fetchone(
            "SELECT id FROM uuid_mig_new_files LIMIT 1",
        )[0]
        uuid.UUID(str(new_fid))
    finally:
        conn.close()


def test_phase6_swap_requires_confirmation(tmp_path: Path) -> None:
    """Verify test phase6 swap requires confirmation."""
    path = Path(tmp_path) / "x.sqlite"
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_LEGACY_P345_SCHEMA)
        db = _SqliteDb(conn)
        with pytest.raises(UuidMigrationError, match="refused"):
            run_uuid_migration_phase6_swap_sqlite(db)
    finally:
        conn.close()


def test_phase6_drop_recreate_fts_after_swap(tmp_path: Path) -> None:
    """Verify test phase6 drop recreate fts after swap."""
    path = Path(tmp_path) / "fts.sqlite"
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_LEGACY_P345_SCHEMA)
        conn.execute("""
            CREATE VIRTUAL TABLE code_content_fts USING fts5(
                entity_type,
                entity_name,
                content,
                docstring,
                content_rowid='rowid',
                content='code_content'
            )
            """)
        db = _SqliteDb(conn)
        _seed_graph(db)
        run_uuid_migration_phase2_build_mappings(db, skip_preflight=True)
        run_uuid_migration_phases_3_to_5_sqlite(db, skip_mapping_validation=True)

        run_uuid_migration_phase6_swap_sqlite(
            db, migration_tag="tfts", i_confirm_maintenance_swap=True
        )

        row = db._fetchone(
            "SELECT sql FROM sqlite_master WHERE name = 'code_content_fts'"
        )
        assert row is not None and "fts5" in (row[0] or "").lower()

        n_cc = _scalar(db, "SELECT COUNT(*) FROM code_content")
        n_fts = _scalar(db, "SELECT COUNT(*) FROM code_content_fts")
        assert n_cc == n_fts == 1

        legacy_names = [
            f"{t}_int_backup_tfts" for t in reversed(MIGRATED_TABLES_COPY_ORDER)
        ]
        for name in legacy_names:
            assert (
                db._fetchone("SELECT 1 FROM sqlite_master WHERE name = ?", (name,))
                is not None
            )
    finally:
        conn.close()


def test_non_sqlite_backend_rejected() -> None:
    """Verify test non sqlite backend rejected."""

    class _Pg:
        """Represent Pg."""

        _driver_type = "postgresql"

        def _execute(self, *a: Any, **k: Any) -> None:
            """Return execute."""
            return None

        def _fetchone(self, *a: Any, **k: Any) -> Any:
            """Return fetchone."""
            return None

        def _commit(self) -> None:
            """Return commit."""
            return None

    with pytest.raises(UuidMigrationError, match="SQLite-only"):
        run_uuid_migration_phases_3_to_5_sqlite(
            _Pg(), dry_run=True, skip_mapping_validation=True
        )
