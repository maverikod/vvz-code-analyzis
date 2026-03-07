"""
Schema creation and migrations for CodeDatabase.
Extracted from base.py to keep file size under limit.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def run_create_schema(db: Any) -> None:
    """Create database schema if it doesn't exist."""
    # All operations use driver interface - no direct connection access

    # Create watch_dirs table first (projects reference it)
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS watch_dirs (
                id TEXT PRIMARY KEY,
                name TEXT,
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now'))
            )
        """
    )

    # Create watch_dir_paths table (maps watch_dir_id to absolute path)
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS watch_dir_paths (
                watch_dir_id TEXT PRIMARY KEY,
                absolute_path TEXT,
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (watch_dir_id) REFERENCES watch_dirs(id) ON DELETE CASCADE
            )
        """
    )

    # Create projects table (references watch_dirs)
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                root_path TEXT UNIQUE NOT NULL,
                name TEXT,
                comment TEXT,
                watch_dir_id TEXT,
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (watch_dir_id) REFERENCES watch_dirs(id) ON DELETE SET NULL
            )
        """
    )
    # Create index on watch_dir_id for performance
    try:
        db._execute(
            """
            CREATE INDEX IF NOT EXISTS idx_projects_watch_dir_id 
            ON projects(watch_dir_id)
            """
        )
    except Exception:
        pass  # Index might already exist
    # Files table: one project, path unique per project
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                watch_dir_id TEXT,
                path TEXT NOT NULL,
                relative_path TEXT,
                lines INTEGER,
                last_modified REAL,
                has_docstring BOOLEAN,
                deleted BOOLEAN DEFAULT 0,
                original_path TEXT,
                version_dir TEXT,
                needs_chunking INTEGER DEFAULT 0,
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (watch_dir_id) REFERENCES watch_dirs(id) ON DELETE SET NULL,
                UNIQUE(project_id, path)
            )
        """
    )
    # Create partial index for deleted files (only indexes deleted=1)
    try:
        db._execute(
            """
            CREATE INDEX IF NOT EXISTS idx_files_deleted 
            ON files(deleted) WHERE deleted = 1
            """
        )
    except Exception:
        pass  # Index might already exist
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                line INTEGER NOT NULL,
                end_line INTEGER,
                cst_node_id TEXT,
                docstring TEXT,
                bases TEXT,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                UNIQUE(file_id, name, line)
            )
        """
    )
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                line INTEGER NOT NULL,
                end_line INTEGER,
                cst_node_id TEXT,
                args TEXT,
                docstring TEXT,
                is_abstract BOOLEAN DEFAULT 0,
                has_pass BOOLEAN DEFAULT 0,
                has_not_implemented BOOLEAN DEFAULT 0,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
                UNIQUE(class_id, name, line)
            )
        """
    )
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS functions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                line INTEGER NOT NULL,
                end_line INTEGER,
                cst_node_id TEXT,
                args TEXT,
                docstring TEXT,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                UNIQUE(file_id, name, line)
            )
        """
    )
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                module TEXT,
                import_type TEXT NOT NULL,
                line INTEGER NOT NULL,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            )
        """
    )
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER,
                project_id TEXT,
                class_id INTEGER,
                function_id INTEGER,
                method_id INTEGER,
                issue_type TEXT NOT NULL,
                line INTEGER,
                description TEXT,
                metadata TEXT,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
                FOREIGN KEY (function_id) REFERENCES functions(id) ON DELETE CASCADE,
                FOREIGN KEY (method_id) REFERENCES methods(id) ON DELETE CASCADE
            )
        """
    )
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS usages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                line INTEGER NOT NULL,
                usage_type TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_class TEXT,
                target_name TEXT NOT NULL,
                context TEXT,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            )
        """
    )
    db._execute(
        """
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
        """
    )
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS code_content (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER,
                entity_name TEXT,
                content TEXT NOT NULL,
                docstring TEXT,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            )
        """
    )
    db._execute(
        """
            CREATE VIRTUAL TABLE IF NOT EXISTS code_content_fts USING fts5(
                entity_type,
                entity_name,
                content,
                docstring,
                content_rowid='rowid',
                content='code_content'
            )
        """
    )
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS ast_trees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                project_id TEXT NOT NULL,
                ast_json TEXT NOT NULL,
                ast_hash TEXT NOT NULL,
                file_mtime REAL NOT NULL,
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(file_id, ast_hash)
            )
        """
    )
    # Check if file_mtime column exists using driver interface
    table_info = db._get_table_info("ast_trees")
    columns = {col["name"]: col["type"] for col in table_info}
    if "file_mtime" not in columns:
        try:
            db._execute(
                "ALTER TABLE ast_trees ADD COLUMN file_mtime REAL NOT NULL DEFAULT 0"
            )
            db._commit()
        except Exception:
            pass  # Column might already exist

    # Create CST trees table for source code storage
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS cst_trees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                project_id TEXT NOT NULL,
                cst_code TEXT NOT NULL,
                cst_hash TEXT NOT NULL,
                file_mtime REAL NOT NULL,
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(file_id, cst_hash)
            )
        """
    )
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS vector_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                vector_id INTEGER NOT NULL,
                vector_dim INTEGER NOT NULL,
                embedding_model TEXT,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(project_id, entity_type, entity_id)
            )
        """
    )
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS code_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                project_id TEXT NOT NULL,
                chunk_uuid TEXT NOT NULL,
                chunk_type TEXT NOT NULL,
                chunk_text TEXT NOT NULL,
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
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
                FOREIGN KEY (function_id) REFERENCES functions(id) ON DELETE CASCADE,
                FOREIGN KEY (method_id) REFERENCES methods(id) ON DELETE CASCADE,
                UNIQUE(chunk_uuid)
            )
        """
    )
    # Try to add missing columns (if table already exists)
    try:
        db._execute("ALTER TABLE code_chunks ADD COLUMN bm25_score REAL")
        logger.info("Added bm25_score column to code_chunks table")
    except Exception:
        pass
    try:
        db._execute("ALTER TABLE code_chunks ADD COLUMN embedding_vector TEXT")
        logger.info("Added embedding_vector column to code_chunks table")
    except Exception:
        pass
    try:
        db._execute(
            "ALTER TABLE code_chunks ADD COLUMN binding_level INTEGER DEFAULT 0"
        )
        logger.info("Added binding_level column to code_chunks table")
    except Exception:
        pass
    try:
        db._execute(
            "ALTER TABLE code_chunks ADD COLUMN updated_at REAL DEFAULT (julianday('now'))"
        )
        logger.info("Added updated_at column to code_chunks table")
    except Exception:
        pass
    try:
        db._execute("ALTER TABLE code_chunks ADD COLUMN token_count INTEGER")
        logger.info("Added token_count column to code_chunks table")
    except Exception:
        pass
    # Create code_duplicates table
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS code_duplicates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                duplicate_hash TEXT NOT NULL,
                similarity REAL NOT NULL,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(project_id, duplicate_hash)
            )
        """
    )
    # Create duplicate_occurrences table
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS duplicate_occurrences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                duplicate_id INTEGER NOT NULL,
                file_id INTEGER NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                code_snippet TEXT,
                ast_node_id INTEGER,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (duplicate_id) REFERENCES code_duplicates(id) ON DELETE CASCADE,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            )
        """
    )
    # Create comprehensive_analysis_results table
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS comprehensive_analysis_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                project_id TEXT NOT NULL,
                file_mtime REAL NOT NULL,
                results_json TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(file_id, file_mtime)
            )
        """
    )
    # Create file_watcher_stats table for tracking file watcher cycle statistics
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS file_watcher_stats (
                cycle_id TEXT PRIMARY KEY,
                cycle_start_time REAL NOT NULL,
                cycle_end_time REAL,
                files_total_at_start INTEGER NOT NULL DEFAULT 0,
                files_added INTEGER NOT NULL DEFAULT 0,
                files_processed INTEGER NOT NULL DEFAULT 0,
                files_skipped INTEGER NOT NULL DEFAULT 0,
                files_failed INTEGER NOT NULL DEFAULT 0,
                files_changed INTEGER NOT NULL DEFAULT 0,
                files_deleted INTEGER NOT NULL DEFAULT 0,
                total_processing_time_seconds REAL NOT NULL DEFAULT 0.0,
                average_processing_time_seconds REAL,
                current_project_id TEXT,
                last_updated REAL DEFAULT (julianday('now'))
            )
        """
    )
    # Create vectorization_stats table for tracking vectorization cycle statistics
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS vectorization_stats (
                cycle_id TEXT PRIMARY KEY,
                cycle_start_time REAL NOT NULL,
                cycle_end_time REAL,
                chunks_total_at_start INTEGER NOT NULL DEFAULT 0,
                chunks_processed INTEGER NOT NULL DEFAULT 0,
                chunks_skipped INTEGER NOT NULL DEFAULT 0,
                chunks_failed INTEGER NOT NULL DEFAULT 0,
                files_total_at_start INTEGER NOT NULL DEFAULT 0,
                files_vectorized INTEGER NOT NULL DEFAULT 0,
                total_processing_time_seconds REAL NOT NULL DEFAULT 0.0,
                average_processing_time_seconds REAL,
                last_updated REAL DEFAULT (julianday('now'))
            )
        """
    )
    # Create indexing_worker_stats table for tracking indexing cycle statistics.
    # Canonical schema for driver auto-create/migrate: database_driver_pkg.drivers.sqlite
    # INDEXING_WORKER_STATS_COLUMNS (keep in sync when adding columns).
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS indexing_worker_stats (
                cycle_id TEXT PRIMARY KEY,
                cycle_start_time REAL NOT NULL,
                cycle_end_time REAL,
                files_total_at_start INTEGER NOT NULL DEFAULT 0,
                files_indexed INTEGER NOT NULL DEFAULT 0,
                files_failed INTEGER NOT NULL DEFAULT 0,
                total_processing_time_seconds REAL NOT NULL DEFAULT 0.0,
                average_processing_time_seconds REAL,
                last_updated REAL DEFAULT (julianday('now'))
            )
        """
    )
    db._execute(
        """
            CREATE TABLE IF NOT EXISTS indexing_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                error_type TEXT,
                error_message TEXT,
                created_at REAL DEFAULT (julianday('now')),
                UNIQUE(project_id, file_path)
            )
        """
    )
    db._commit()
    run_migrate_to_uuid_projects(db)
    run_migrate_schema(db)
    # Create indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_projects_root_path ON projects(root_path)",
        "CREATE INDEX IF NOT EXISTS idx_files_project ON files(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_files_path ON files(path)",
        "CREATE INDEX IF NOT EXISTS idx_indexing_errors_project_path ON indexing_errors(project_id, file_path)",
        "CREATE INDEX IF NOT EXISTS idx_classes_name ON classes(name)",
        "CREATE INDEX IF NOT EXISTS idx_classes_file ON classes(file_id)",
        "CREATE INDEX IF NOT EXISTS idx_methods_name ON methods(name)",
        "CREATE INDEX IF NOT EXISTS idx_methods_class ON methods(class_id)",
        "CREATE INDEX IF NOT EXISTS idx_functions_name ON functions(name)",
        "CREATE INDEX IF NOT EXISTS idx_functions_file ON functions(file_id)",
        "CREATE INDEX IF NOT EXISTS idx_imports_file ON imports(file_id)",
        "CREATE INDEX IF NOT EXISTS idx_imports_name ON imports(name)",
        "CREATE INDEX IF NOT EXISTS idx_issues_type ON issues(issue_type)",
        "CREATE INDEX IF NOT EXISTS idx_issues_file ON issues(file_id)",
        "CREATE INDEX IF NOT EXISTS idx_usages_file ON usages(file_id)",
        "CREATE INDEX IF NOT EXISTS idx_usages_target ON usages(target_type, target_name)",
        "CREATE INDEX IF NOT EXISTS idx_usages_class_name ON usages(target_class, target_name)",
        "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_caller_class ON entity_cross_ref(caller_class_id) WHERE caller_class_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_caller_method ON entity_cross_ref(caller_method_id) WHERE caller_method_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_caller_function ON entity_cross_ref(caller_function_id) WHERE caller_function_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_callee_class ON entity_cross_ref(callee_class_id) WHERE callee_class_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_callee_method ON entity_cross_ref(callee_method_id) WHERE callee_method_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_callee_function ON entity_cross_ref(callee_function_id) WHERE callee_function_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_file ON entity_cross_ref(file_id)",
        "CREATE INDEX IF NOT EXISTS idx_code_content_file ON code_content(file_id)",
        "CREATE INDEX IF NOT EXISTS idx_code_content_entity ON code_content(entity_type, entity_id)",
        "CREATE INDEX IF NOT EXISTS idx_ast_trees_file ON ast_trees(file_id)",
        "CREATE INDEX IF NOT EXISTS idx_ast_trees_project ON ast_trees(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_ast_trees_hash ON ast_trees(ast_hash)",
        "CREATE INDEX IF NOT EXISTS idx_vector_index_project ON vector_index(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_vector_index_entity ON vector_index(entity_type, entity_id)",
        "CREATE INDEX IF NOT EXISTS idx_vector_index_vector_id ON vector_index(vector_id)",
        "CREATE INDEX IF NOT EXISTS idx_code_chunks_file ON code_chunks(file_id)",
        "CREATE INDEX IF NOT EXISTS idx_code_chunks_project ON code_chunks(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_code_chunks_uuid ON code_chunks(chunk_uuid)",
        "CREATE INDEX IF NOT EXISTS idx_code_chunks_vector ON code_chunks(vector_id)",
        "CREATE INDEX IF NOT EXISTS idx_code_chunks_not_vectorized ON code_chunks(project_id, id) WHERE vector_id IS NULL",
        "CREATE INDEX IF NOT EXISTS idx_code_chunks_created_at ON code_chunks(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_code_chunks_project_embedding_model ON code_chunks(project_id) WHERE embedding_model IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_files_deleted ON files(deleted) WHERE deleted = 1",
        "CREATE INDEX IF NOT EXISTS idx_files_updated_at ON files(updated_at)",
        "CREATE INDEX IF NOT EXISTS idx_files_needs_indexing ON files(project_id, updated_at) WHERE (deleted = 0 OR deleted IS NULL) AND needs_chunking = 1",
        "CREATE INDEX IF NOT EXISTS idx_code_duplicates_project ON code_duplicates(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_code_duplicates_hash ON code_duplicates(duplicate_hash)",
        "CREATE INDEX IF NOT EXISTS idx_duplicate_occurrences_duplicate ON duplicate_occurrences(duplicate_id)",
        "CREATE INDEX IF NOT EXISTS idx_duplicate_occurrences_file ON duplicate_occurrences(file_id)",
        "CREATE INDEX IF NOT EXISTS idx_file_watcher_stats_start_time ON file_watcher_stats(cycle_start_time)",
        "CREATE INDEX IF NOT EXISTS idx_vectorization_stats_start_time ON vectorization_stats(cycle_start_time)",
        "CREATE INDEX IF NOT EXISTS idx_indexing_worker_stats_start_time ON indexing_worker_stats(cycle_start_time)",
    ]
    for index_sql in indexes:
        db._execute(index_sql)
    db._commit()


def run_migrate_to_uuid_projects(db: Any) -> None:
    """Migrate projects table from INTEGER to UUID4 if needed."""
    # Use driver interface to get table info
    table_info = db._get_table_info("projects")
    columns = {col["name"]: col["type"] for col in table_info}
    if "id" in columns and columns["id"] == "INTEGER":
        logger.info("Migrating projects table to UUID4...")
        db._execute(
            """
            CREATE TABLE IF NOT EXISTS projects_new (
                id TEXT PRIMARY KEY,
                root_path TEXT UNIQUE NOT NULL,
                name TEXT,
                comment TEXT,
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now'))
            )
        """
        )
        old_projects = db._fetchall(
            "SELECT id, root_path, name, created_at, updated_at FROM projects"
        )
        for row in old_projects:
            old_id = row["id"]
            root_path = row["root_path"]
            name = row["name"]
            created_at = row["created_at"]
            updated_at = row["updated_at"]
            new_id = str(uuid.uuid4())
            db._execute(
                """
                INSERT INTO projects_new (
                    id, root_path, name, comment, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    new_id,
                    root_path,
                    name,
                    f"Migrated from project_id {old_id}",
                    created_at,
                    updated_at,
                ),
            )
            db._execute(
                "UPDATE files SET project_id = ? WHERE project_id = ?",
                (new_id, old_id),
            )
        db._execute("DROP TABLE projects")
        db._execute("ALTER TABLE projects_new RENAME TO projects")
        db._execute("PRAGMA foreign_keys = OFF")
        db._execute(
            """
            CREATE TABLE IF NOT EXISTS files_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                path TEXT NOT NULL,
                lines INTEGER,
                last_modified REAL,
                has_docstring BOOLEAN,
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(project_id, path)
            )
        """
        )
        db._execute(
            """
            INSERT INTO files_new (id, project_id, path, lines, last_modified, has_docstring, created_at, updated_at)
            SELECT id, project_id, path, lines, last_modified, has_docstring, created_at, updated_at FROM files
            """
        )
        db._execute("DROP TABLE files")
        db._execute("ALTER TABLE files_new RENAME TO files")
        db._execute("PRAGMA foreign_keys = ON")
        db._commit()
        logger.info("Migration to UUID4 completed")
    if "comment" not in columns:
        try:
            db._execute("ALTER TABLE projects ADD COLUMN comment TEXT")
            db._commit()
        except Exception:
            pass


def run_migrate_schema(db: Any) -> None:
    """
    Migrate database schema - add missing columns, update structure.
    Called on every database initialization to ensure schema is up to date.
    """
    # Use driver interface to get table info
    issues_table_info = db._get_table_info("issues")
    issues_columns = {col["name"]: col["type"] for col in issues_table_info}
    if "project_id" not in issues_columns:
        try:
            logger.info("Migrating issues table: adding project_id column")
            db._execute("ALTER TABLE issues ADD COLUMN project_id TEXT")
            db._execute(
                """
                UPDATE issues
                SET project_id = (
                    SELECT f.project_id
                    FROM files f
                    WHERE f.id = issues.file_id
                )
                WHERE file_id IS NOT NULL
            """
            )
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

    # Deletion mark is only in files table; projects are considered trashed when
    # all their files have deleted=1 (checked via EXISTS on files).

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

    # Create index after adding deleted column
    if "deleted" in files_columns or "deleted" not in files_columns:
        try:
            db._execute(
                """
                CREATE INDEX IF NOT EXISTS idx_files_deleted 
                ON files(deleted) WHERE deleted = 1
                """
            )
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
            db._execute(
                """
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
                """
            )
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
