"""
Block E step 09: Phase 1–2 UUID migration mapping (legacy INTEGER SQLite fixture).

Uses raw SQLite INTEGER PK schema (legacy) — not post-sync_uuid logical schema — so mapping
parity matches migration step 09.

This module wires migration helpers against raw :class:`sqlite3.Connection` only;
``_LegacySQLiteMigrConn`` is a minimal shim with ``_fetchone`` / ``_execute`` for those calls.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from code_analysis.core.database.migrations.uuid_identity_migration_common import (
    MANDATORY_SOURCE_TO_MIGRATION,
    make_mapping_lookup_closure,
    map_polymorphic_entity_id_to_new_uuid,
    run_uuid_migration_phase2_build_mappings,
)
from code_analysis.core.database.migrations.uuid_identity_migration_postgres import (
    create_mapping_tables_postgres,
)

# FK checks off; minimal INTEGER PK tables matching migration sources (subset of prod DDL).
_LEGACY_INTEGER_SCHEMA_SQL = """
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
    path TEXT NOT NULL DEFAULT ''
);

CREATE TABLE classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    name TEXT,
    line INTEGER DEFAULT 1
);

CREATE TABLE methods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL,
    name TEXT,
    line INTEGER DEFAULT 1
);

CREATE TABLE functions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    name TEXT,
    line INTEGER DEFAULT 1
);

CREATE TABLE entity_cross_ref (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_type TEXT DEFAULT 'call',
    caller_class_id INTEGER,
    callee_class_id INTEGER
);

CREATE TABLE imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    name TEXT DEFAULT ''
);

CREATE TABLE issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER,
    project_id TEXT,
    issue_type TEXT DEFAULT ''
);

CREATE TABLE usages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    line INTEGER DEFAULT 1,
    usage_type TEXT DEFAULT 'ref',
    target_type TEXT DEFAULT 'x',
    target_name TEXT DEFAULT 'n'
);

CREATE TABLE code_content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    content TEXT DEFAULT ''
);

CREATE TABLE ast_trees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    ast_json TEXT DEFAULT '{}',
    ast_hash TEXT DEFAULT 'h',
    file_mtime REAL DEFAULT 0
);

CREATE TABLE cst_trees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    cst_code TEXT DEFAULT '',
    cst_hash TEXT DEFAULT 'h',
    file_mtime REAL DEFAULT 0
);

CREATE TABLE vector_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    vector_id INTEGER NOT NULL,
    vector_dim INTEGER NOT NULL DEFAULT 384
);

CREATE TABLE code_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    chunk_uuid TEXT NOT NULL DEFAULT 'cu',
    chunk_type TEXT DEFAULT 't',
    chunk_text TEXT DEFAULT '',
    vector_id INTEGER
);

CREATE TABLE code_duplicates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    duplicate_hash TEXT DEFAULT 'x'
);

CREATE TABLE duplicate_occurrences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    duplicate_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    start_line INTEGER DEFAULT 1,
    end_line INTEGER DEFAULT 1
);

CREATE TABLE comprehensive_analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    file_mtime REAL DEFAULT 0,
    results_json TEXT DEFAULT '{}',
    summary_json TEXT DEFAULT '{}'
);

CREATE TABLE file_tree_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    source_payload TEXT DEFAULT '',
    file_mtime REAL DEFAULT 0
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
    file_path TEXT NOT NULL
);
"""


class _LegacySQLiteMigrConn:
    """Minimal SQLite connection wrapper used by Phase 1–2 migration helpers."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Initialize the instance."""
        self._conn = conn
        self._driver_type = "sqlite"

    def _execute(self, sql: str, params=None) -> None:
        """Return execute."""
        self._conn.execute(sql, params or ())

    def _fetchone(self, sql: str, params=None):
        """Return fetchone."""
        cur = self._conn.execute(sql, params or ())
        return cur.fetchone()

    def _fetchall(self, sql: str, params=None):
        """Return fetchall."""
        cur = self._conn.execute(sql, params or ())
        return cur.fetchall()

    def _commit(self) -> None:
        """Return commit."""
        self._conn.commit()


def _scalar(db: _LegacySQLiteMigrConn, sql: str, params: tuple = ()) -> int:
    """Return scalar."""
    r = db._fetchone(sql, params)
    if not r:
        return 0
    return int(r[0])


def _read_map_old_to_new(db: _LegacySQLiteMigrConn, mig_tbl: str) -> dict[int, str]:
    """Return read map old to new."""
    rows = db._fetchall(f"SELECT old_id, new_id FROM {mig_tbl}")
    out: dict[int, str] = {}
    for row in rows:
        out[int(row[0])] = str(row[1])
    return out


def _seed_legacy_graph(db: _LegacySQLiteMigrConn) -> tuple[int, int, int]:
    """Return seed legacy graph."""
    w = str(uuid.uuid4())
    p = str(uuid.uuid4())
    db._execute("INSERT INTO watch_dirs (id, name) VALUES (?, ?)", (w, "wd"))
    db._execute(
        "INSERT INTO projects (id, root_path, watch_dir_id) VALUES (?,?,?)",
        (p, "/r", w),
    )
    db._execute(
        "INSERT INTO files (project_id, watch_dir_id, path) VALUES (?,?,?)",
        (p, w, "m.py"),
    )
    db._commit()
    fid_row = db._fetchone("SELECT MAX(id) FROM files")
    fid = int(fid_row[0])

    db._execute(
        "INSERT INTO classes (file_id, name, line) VALUES (?,?,?)",
        (fid, "C", 1),
    )
    db._commit()
    cid_row = db._fetchone("SELECT MAX(id) FROM classes")
    cid = int(cid_row[0])

    cu = str(uuid.uuid4())
    db._execute(
        "INSERT INTO code_chunks (file_id, project_id, chunk_uuid, chunk_type, chunk_text, vector_id) "
        "VALUES (?,?,?,?,?,?)",
        (fid, p, cu, "docstring", "x", 777),
    )
    db._commit()
    ck_row = db._fetchone("SELECT MAX(id) FROM code_chunks")
    chunk_pk = int(ck_row[0])

    db._execute(
        "INSERT INTO code_content (file_id, entity_type, entity_id, content) "
        "VALUES (?,?,?,?)",
        (fid, "class", cid, "body"),
    )
    db._execute(
        "INSERT INTO vector_index (project_id, entity_type, entity_id, vector_id, vector_dim) "
        "VALUES (?,?,?,?,?)",
        (p, "chunk", chunk_pk, 9999, 384),
    )
    db._commit()

    vx = db._fetchone(
        "SELECT vector_id FROM vector_index WHERE entity_type = ? AND entity_id = ?",
        ("chunk", chunk_pk),
    )
    assert int(vx[0]) == 9999

    return fid, cid, chunk_pk


def test_postgres_migration_ddl_contains_uuid_columns() -> None:
    """Verify test postgres migration ddl contains uuid columns."""
    ddl = "\n".join(create_mapping_tables_postgres())
    assert "uuid_migration_files" in ddl
    assert "uuid_migration_indexing_errors" in ddl
    assert " UUID " in ddl


def test_phase2_legacy_sqlite_mappings_idempotent(tmp_path: Path) -> None:
    """Verify test phase2 legacy sqlite mappings idempotent."""
    path = Path(tmp_path) / "legacy_mig.sqlite"
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_LEGACY_INTEGER_SCHEMA_SQL)
        db = _LegacySQLiteMigrConn(conn)

        fid, cid, chunk_pk = _seed_legacy_graph(db)

        run_uuid_migration_phase2_build_mappings(db, skip_preflight=False)

        mapping_names = [m[1] for m in MANDATORY_SOURCE_TO_MIGRATION]
        for src, mig in MANDATORY_SOURCE_TO_MIGRATION:
            s = _scalar(db, f"SELECT COUNT(*) FROM {src}")
            mm = _scalar(db, f"SELECT COUNT(*) FROM {mig}")
            assert s == mm, (src, mig, s, mm)

        first_files = _read_map_old_to_new(db, "uuid_migration_files")
        assert fid in first_files

        run_uuid_migration_phase2_build_mappings(db, skip_preflight=True)
        second = _read_map_old_to_new(db, "uuid_migration_files")
        assert second == first_files

        assert len(mapping_names) == len(MANDATORY_SOURCE_TO_MIGRATION)

        lookup = make_mapping_lookup_closure(db)
        nc = lookup("classes", cid)
        nf = lookup("files", fid)
        nchk = lookup("code_chunks", chunk_pk)
        assert nc and nf and nchk

        polym = map_polymorphic_entity_id_to_new_uuid(
            "class", cid, lambda t, oid: lookup(t, oid)
        )
        assert polym == nc

        v_after = db._fetchone(
            "SELECT vector_id FROM vector_index WHERE entity_type = ? AND entity_id = ?",
            ("chunk", chunk_pk),
        )
        assert int(v_after[0]) == 9999
    finally:
        conn.close()


def test_preflight_execute_only_db_like_rpc_client() -> None:
    """Preflight must rely on generic ``execute`` only (no private ``_fetchone`` on RPC clients)."""
    from code_analysis.core.database.migrations.uuid_identity_migration_common import (
        run_uuid_migration_preflight_phase1,
    )

    pid = str(uuid.uuid4())
    wid = str(uuid.uuid4())

    class _ExecuteOnlyDb:
        """Represent ExecuteOnlyDb."""

        _driver_type = "postgresql"

        def execute(self, sql: str, params=None):
            """Execute the command."""
            s = " ".join(sql.split()).lower()
            if "count(*)" in s and " from projects" in s and "files" not in s:
                return {"data": [{"n": 1}]}
            if "count(*)" in s and " from watch_dirs" in s:
                return {"data": [{"n": 1}]}
            if "select id from projects" in s:
                return {"data": [{"id": pid}]}
            if "select id from watch_dirs" in s:
                return {"data": [{"id": wid}]}
            if "from files f" in s and "left join projects" in s:
                return {"data": [{"n": 0}]}
            raise AssertionError(f"unexpected sql in fake db: {sql!r}")

    rep = run_uuid_migration_preflight_phase1(_ExecuteOnlyDb(), check_orphan_fks=True)
    assert rep.projects_uuid_ok is True
    assert rep.watch_dirs_uuid_ok is True
    assert not any("Skipping UUID" in w for w in rep.warnings)
    assert not any("_fetchone" in w for w in rep.warnings)
