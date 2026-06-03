"""
Schema migrations (add columns, etc.) for CodeDatabase. Part of schema_creation split.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def run_migrate_schema(db: Any) -> None:
    """
    Migrate database schema - add missing columns, update structure.
    Called on every database initialization to ensure schema is up to date.
    """
    try:
        db._execute("""
            CREATE TABLE IF NOT EXISTS runtime_lock_sessions (
                session_id TEXT PRIMARY KEY,
                pid INTEGER NOT NULL UNIQUE,
                listener_url TEXT,
                role TEXT NOT NULL,
                hostname TEXT,
                started_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now'))
            )
            """)
        db._execute("""
            CREATE INDEX IF NOT EXISTS idx_runtime_lock_sessions_pid
            ON runtime_lock_sessions(pid)
            """)
        db._execute("""
            CREATE TABLE IF NOT EXISTS file_advisory_lock_leases (
                session_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                lock_mode TEXT NOT NULL,
                locked_since REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now')),
                refcount INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (session_id, project_id, file_path, lock_mode),
                FOREIGN KEY (session_id) REFERENCES runtime_lock_sessions(session_id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                CHECK (lock_mode IN ('exclusive', 'shared')),
                CHECK (refcount > 0)
            )
            """)
        db._execute("""
            CREATE INDEX IF NOT EXISTS idx_file_advisory_lock_leases_file
            ON file_advisory_lock_leases(project_id, file_path)
            """)
        db._execute("""
            CREATE INDEX IF NOT EXISTS idx_file_advisory_lock_leases_session
            ON file_advisory_lock_leases(session_id)
            """)
        db._commit()
    except Exception as e:
        logger.warning("Could not create runtime lock tables/indexes: %s", e)

    # Use driver interface to get table info
    issues_table_info = db._get_table_info("issues")
    issues_columns = {col["name"]: col["type"] for col in issues_table_info}
    if "project_id" not in issues_columns:
        try:
            logger.info("Migrating issues table: adding project_id column")
            db._execute("ALTER TABLE issues ADD COLUMN project_id TEXT")
            db._execute("""
                UPDATE issues
                SET project_id = (
                    SELECT f.project_id
                    FROM files f
                    WHERE f.id = issues.file_id
                )
                WHERE file_id IS NOT NULL
            """)
            db._commit()
            logger.info("Migration completed: issues table now has project_id")
        except Exception as e:
            logger.warning(f"Migration issue (may already exist): {e}")
    # Check if index exists using driver interface
    index_check = db._fetchone(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_issues_project'"
    )
    if not index_check:
        try:
            db._execute(
                "CREATE INDEX IF NOT EXISTS idx_issues_project ON issues(project_id)"
            )
            db._commit()
        except Exception as e:
            logger.warning(f"Could not create index idx_issues_project: {e}")
    chunks_table_info = db._get_table_info("code_chunks")
    chunks_columns = {col["name"]: col["type"] for col in chunks_table_info}
    new_columns = {
        "class_id": "INTEGER",
        "function_id": "INTEGER",
        "method_id": "INTEGER",
        "line": "INTEGER",
        "ast_node_type": "TEXT",
        "source_type": "TEXT",
        "bm25_score": "REAL",
        "embedding_vector": "TEXT",
        "token_count": "INTEGER",
        "binding_level": "INTEGER DEFAULT 0",
        "vectorization_skipped": "INTEGER DEFAULT 0",
    }
    for col_name, col_type in new_columns.items():
        if col_name not in chunks_columns:
            try:
                logger.info(f"Migrating code_chunks table: adding {col_name} column")
                db._execute(f"ALTER TABLE code_chunks ADD COLUMN {col_name} {col_type}")
                db._commit()
            except Exception as e:
                logger.warning(f"Could not add column {col_name} to code_chunks: {e}")

    # Migration: Add deleted, original_path, version_dir columns to files table if they don't exist
    files_table_info = db._get_table_info("files")
    files_columns = {col["name"]: col["type"] for col in files_table_info}
    if "deleted" not in files_columns:
        try:
            logger.info("Migrating files table: adding deleted column")
            db._execute("ALTER TABLE files ADD COLUMN deleted BOOLEAN DEFAULT 0")
            db._commit()
        except Exception as e:
            logger.warning(f"Could not add deleted column to files: {e}")

    # Migration: Add current_project_id column to file_watcher_stats table if it doesn't exist
    try:
        file_watcher_stats_table_info = db._get_table_info("file_watcher_stats")
        file_watcher_stats_columns = {
            col["name"]: col["type"] for col in file_watcher_stats_table_info
        }
        if "current_project_id" not in file_watcher_stats_columns:
            logger.info(
                "Migrating file_watcher_stats table: adding current_project_id column"
            )
            db._execute(
                "ALTER TABLE file_watcher_stats ADD COLUMN current_project_id TEXT"
            )
            db._commit()
    except Exception as e:
        # Table might not exist yet, that's OK
        logger.debug(
            f"Could not check/add current_project_id to file_watcher_stats: {e}"
        )

    # Migration: Add files_total_at_start and files_vectorized columns to vectorization_stats table
    try:
        vectorization_stats_table_info = db._get_table_info("vectorization_stats")
        vectorization_stats_columns = {
            col["name"]: col["type"] for col in vectorization_stats_table_info
        }
        if "files_total_at_start" not in vectorization_stats_columns:
            logger.info(
                "Migrating vectorization_stats table: adding files_total_at_start column"
            )
            db._execute(
                "ALTER TABLE vectorization_stats ADD COLUMN files_total_at_start INTEGER NOT NULL DEFAULT 0"
            )
            db._commit()
        if "files_vectorized" not in vectorization_stats_columns:
            logger.info(
                "Migrating vectorization_stats table: adding files_vectorized column"
            )
            db._execute(
                "ALTER TABLE vectorization_stats ADD COLUMN files_vectorized INTEGER NOT NULL DEFAULT 0"
            )
            db._commit()
    except Exception as e:
        # Table might not exist yet, that's OK
        logger.debug(f"Could not check/add files columns to vectorization_stats: {e}")

    if "original_path" not in files_columns:
        try:
            logger.info("Migrating files table: adding original_path column")
            db._execute("ALTER TABLE files ADD COLUMN original_path TEXT")
            db._commit()
        except Exception as e:
            logger.warning(f"Could not add original_path column to files: {e}")

    if "version_dir" not in files_columns:
        try:
            logger.info("Migrating files table: adding version_dir column")
            db._execute("ALTER TABLE files ADD COLUMN version_dir TEXT")
            db._commit()
        except Exception as e:
            logger.warning(f"Could not add version_dir column to files: {e}")

    # Project-level soft delete (empty projects and explicit tombstone).
    try:
        projects_table_info = db._get_table_info("projects")
        projects_columns = {col["name"]: col["type"] for col in projects_table_info}
    except Exception as e:
        projects_columns = {}
        logger.debug(f"Could not inspect projects table: {e}")
    if "deleted" not in projects_columns:
        try:
            logger.info("Migrating projects table: adding deleted column")
            db._execute("ALTER TABLE projects ADD COLUMN deleted BOOLEAN DEFAULT 0")
            db._commit()
        except Exception as e:
            logger.warning(f"Could not add deleted column to projects: {e}")
    try:
        db._execute("""
            CREATE INDEX IF NOT EXISTS idx_projects_deleted
            ON projects(deleted) WHERE deleted = 1
            """)
        db._commit()
    except Exception as e:
        logger.warning(f"Could not create index idx_projects_deleted: {e}")

    if "needs_chunking" not in files_columns:
        try:
            logger.info("Migrating files table: adding needs_chunking column")
            db._execute("ALTER TABLE files ADD COLUMN needs_chunking INTEGER DEFAULT 0")
            db._commit()
        except Exception as e:
            logger.warning(f"Could not add needs_chunking column to files: {e}")

    if "dataset_id" in files_columns:
        try:
            logger.info(
                "Migrating files table: dropping dataset_id column (datasets removed)"
            )
            db._execute("ALTER TABLE files DROP COLUMN dataset_id")
            db._commit()
        except Exception as e:
            logger.warning(
                f"Could not drop dataset_id from files (SQLite 3.35+ required): {e}"
            )

    if "processing_paused" not in projects_columns:
        try:
            logger.info("Migrating projects table: adding processing_paused column")
            db._execute(
                "ALTER TABLE projects ADD COLUMN processing_paused BOOLEAN DEFAULT 0"
            )
            db._commit()
        except Exception as e:
            logger.warning(f"Could not add processing_paused column to projects: {e}")

    # Create index after adding deleted column
    if "deleted" in files_columns or "deleted" not in files_columns:
        try:
            db._execute("""
                CREATE INDEX IF NOT EXISTS idx_files_deleted 
                ON files(deleted) WHERE deleted = 1
                """)
            db._commit()
            logger.info("Created index idx_files_deleted")
        except Exception as e:
            logger.warning(f"Could not create index idx_files_deleted: {e}")

    # Migration: Add complexity column to functions table if it doesn't exist
    functions_table_info = db._get_table_info("functions")
    functions_columns = {col["name"]: col["type"] for col in functions_table_info}
    if "complexity" not in functions_columns:
        try:
            logger.info("Migrating functions table: adding complexity column")
            db._execute("ALTER TABLE functions ADD COLUMN complexity INTEGER")
            db._commit()
        except Exception as e:
            logger.warning(f"Could not add complexity column to functions: {e}")

    # Migration: Add complexity column to methods table if it doesn't exist
    methods_table_info = db._get_table_info("methods")
    methods_columns = {col["name"]: col["type"] for col in methods_table_info}
    if "complexity" not in methods_columns:
        try:
            logger.info("Migrating methods table: adding complexity column")
            db._execute("ALTER TABLE methods ADD COLUMN complexity INTEGER")
            db._commit()
        except Exception as e:
            logger.warning(f"Could not add complexity column to methods: {e}")

    # Migration: Add end_line to classes, methods, functions (entity cross-ref)
    classes_table_info = db._get_table_info("classes")
    classes_columns = {col["name"]: col["type"] for col in classes_table_info}
    if "end_line" not in classes_columns:
        try:
            logger.info("Migrating classes table: adding end_line column")
            db._execute("ALTER TABLE classes ADD COLUMN end_line INTEGER")
            db._commit()
        except Exception as e:
            logger.warning(f"Could not add end_line column to classes: {e}")
    if "end_line" not in methods_columns:
        try:
            logger.info("Migrating methods table: adding end_line column")
            db._execute("ALTER TABLE methods ADD COLUMN end_line INTEGER")
            db._commit()
        except Exception as e:
            logger.warning(f"Could not add end_line column to methods: {e}")
    if "end_line" not in functions_columns:
        try:
            logger.info("Migrating functions table: adding end_line column")
            db._execute("ALTER TABLE functions ADD COLUMN end_line INTEGER")
            db._commit()
        except Exception as e:
            logger.warning(f"Could not add end_line column to functions: {e}")

    # Migration: Add cst_node_id column to classes, methods, functions (nullable)
    if "cst_node_id" not in classes_columns:
        try:
            logger.info("Migrating classes table: adding cst_node_id column")
            db._execute("ALTER TABLE classes ADD COLUMN cst_node_id TEXT")
            db._commit()
        except Exception as e:
            logger.warning(f"Could not add cst_node_id column to classes: {e}")
    if "cst_node_id" not in methods_columns:
        try:
            logger.info("Migrating methods table: adding cst_node_id column")
            db._execute("ALTER TABLE methods ADD COLUMN cst_node_id TEXT")
            db._commit()
        except Exception as e:
            logger.warning(f"Could not add cst_node_id column to methods: {e}")
    if "cst_node_id" not in functions_columns:
        try:
            logger.info("Migrating functions table: adding cst_node_id column")
            db._execute("ALTER TABLE functions ADD COLUMN cst_node_id TEXT")
            db._commit()
        except Exception as e:
            logger.warning(f"Could not add cst_node_id column to functions: {e}")

    # Migration: Create entity_cross_ref table if not exists (existing DBs)
    entity_cross_ref_check = db._fetchone(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='entity_cross_ref'"
    )
    if not entity_cross_ref_check:
        try:
            logger.info("Migrating: creating entity_cross_ref table")
            db._execute("""
                CREATE TABLE IF NOT EXISTS entity_cross_ref (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    caller_class_id INTEGER NULL,
                    caller_method_id INTEGER NULL,
                    caller_function_id INTEGER NULL,
                    callee_class_id INTEGER NULL,
                    callee_method_id INTEGER NULL,
                    callee_function_id INTEGER NULL,
                    ref_type TEXT NOT NULL,
                    file_id INTEGER NULL,
                    line INTEGER NULL,
                    created_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (caller_class_id) REFERENCES classes(id) ON DELETE CASCADE,
                    FOREIGN KEY (caller_method_id) REFERENCES methods(id) ON DELETE CASCADE,
                    FOREIGN KEY (caller_function_id) REFERENCES functions(id) ON DELETE CASCADE,
                    FOREIGN KEY (callee_class_id) REFERENCES classes(id) ON DELETE CASCADE,
                    FOREIGN KEY (callee_method_id) REFERENCES methods(id) ON DELETE CASCADE,
                    FOREIGN KEY (callee_function_id) REFERENCES functions(id) ON DELETE CASCADE,
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE SET NULL,
                    CHECK (
                        (caller_class_id IS NOT NULL AND caller_method_id IS NULL AND caller_function_id IS NULL)
                        OR (caller_class_id IS NULL AND caller_method_id IS NOT NULL AND caller_function_id IS NULL)
                        OR (caller_class_id IS NULL AND caller_method_id IS NULL AND caller_function_id IS NOT NULL)
                    ),
                    CHECK (
                        (callee_class_id IS NOT NULL AND callee_method_id IS NULL AND callee_function_id IS NULL)
                        OR (callee_class_id IS NULL AND callee_method_id IS NOT NULL AND callee_function_id IS NULL)
                        OR (callee_class_id IS NULL AND callee_method_id IS NULL AND callee_function_id IS NOT NULL)
                    )
                )
                """)
            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_caller_class ON entity_cross_ref(caller_class_id) WHERE caller_class_id IS NOT NULL",
                "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_caller_method ON entity_cross_ref(caller_method_id) WHERE caller_method_id IS NOT NULL",
                "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_caller_function ON entity_cross_ref(caller_function_id) WHERE caller_function_id IS NOT NULL",
                "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_callee_class ON entity_cross_ref(callee_class_id) WHERE callee_class_id IS NOT NULL",
                "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_callee_method ON entity_cross_ref(callee_method_id) WHERE callee_method_id IS NOT NULL",
                "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_callee_function ON entity_cross_ref(callee_function_id) WHERE callee_function_id IS NOT NULL",
                "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_file ON entity_cross_ref(file_id)",
            ]:
                db._execute(idx_sql)
            db._commit()
        except Exception as e:
            logger.warning(f"Could not create entity_cross_ref table: {e}")

    # File-level edit lock (CST / universal_file_replace vs background indexer).
    files_table_info_editing = db._get_table_info("files")
    files_columns_editing = {
        col["name"]: col["type"] for col in files_table_info_editing
    }
    if "editing_pid" not in files_columns_editing:
        try:
            logger.info("Migrating files table: adding editing_pid column")
            db._execute("ALTER TABLE files ADD COLUMN editing_pid INTEGER DEFAULT NULL")
            db._commit()
        except Exception as e:
            logger.warning(f"Could not add editing_pid column to files: {e}")

    try:
        from code_analysis.core.database.migrations.watch_dirs_server_instance import (
            migrate_watch_dirs_server_instance,
        )

        migrate_watch_dirs_server_instance(db)
    except Exception as e:
        logger.warning("watch_dirs_server_instance migration failed: %s", e)

    try:
        from code_analysis.core.database.migrations.projects_root_segment_postgres import (
            migrate_projects_root_segment_postgres,
        )

        migrate_projects_root_segment_postgres(db)
    except Exception as e:
        logger.debug("projects_root_segment_postgres migration skipped: %s", e)

    if getattr(db, "_driver_type", None) != "postgres":
        try:
            db._execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS ux_projects_watch_dir_id_root_path
                ON projects(watch_dir_id, root_path)
                """)
            db._commit()
        except Exception as e:
            logger.debug(
                "SQLite ux_projects_watch_dir_id_root_path index (may conflict until "
                "root_path values are migrated): %s",
                e,
            )


def run_uuid_migration_phase2(db: Any, *, skip_preflight: bool = False) -> Any:
    """
    Block E — Phase 2 only: populate ``uuid_migration_*`` mapping tables (idempotent).

    Does **not** create new UUID business tables, copy rows, rename/swap tables, or
    touch ``vector_id`` semantics (those are Phases 3–6 / steps 10–11).

    ``file_tree_snapshot_roots`` uses Option A — no mapping table here; remap via
    ``uuid_migration_file_tree_snapshots`` in a later Phase-4 rewrite.

    For full API and polymorphic helpers see :mod:`code_analysis.core.database.migrations`.
    """
    from code_analysis.core.database.migrations import (
        run_uuid_migration_phase2 as _phase2_mappings,
    )

    return _phase2_mappings(db, skip_preflight=skip_preflight)


def run_uuid_migration_phases_3_to_5_postgres(db: Any, **kwargs: Any) -> Any:
    """Facade: PostgreSQL shadow copy + validate — see migrations package."""
    from code_analysis.core.database.migrations.uuid_identity_postgres_data_migrate import (
        run_uuid_migration_phases_3_to_5_postgres as _p345,
    )

    return _p345(db, **kwargs)


def run_uuid_migration_phase6_swap_postgres(db: Any, **kwargs: Any) -> Any:
    """Facade: PostgreSQL table rename swap — destructive; see docstring in implementation."""
    from code_analysis.core.database.migrations.uuid_identity_postgres_data_migrate import (
        run_uuid_migration_phase6_swap_postgres as _p6,
    )

    return _p6(db, **kwargs)


def run_uuid_migration_phases_3_to_5_sqlite(db: Any, **kwargs: Any) -> Any:
    """Facade: SQLite shadow copy + validate — see migrations package."""
    from code_analysis.core.database.migrations.uuid_identity_sqlite_data_migrate import (
        run_uuid_migration_phases_3_to_5_sqlite as _s345,
    )

    return _s345(db, **kwargs)


def run_uuid_migration_phase6_swap_sqlite(db: Any, **kwargs: Any) -> Any:
    """Facade: SQLite rename swap + optional FTS rebuild — destructive; see implementation."""
    from code_analysis.core.database.migrations.uuid_identity_sqlite_data_migrate import (
        run_uuid_migration_phase6_swap_sqlite as _s6,
    )

    return _s6(db, **kwargs)
