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
                deleted BOOLEAN DEFAULT 0,
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
    from .schema_creation_uuid import run_migrate_to_uuid_projects
    from .schema_creation_migrate import run_migrate_schema

    run_migrate_to_uuid_projects(db)
    run_migrate_schema(db)
    # Create indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_projects_root_path ON projects(root_path)",
        "CREATE INDEX IF NOT EXISTS idx_projects_deleted ON projects(deleted) WHERE deleted = 1",
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
        "CREATE INDEX IF NOT EXISTS idx_files_deleted_project_id ON files(deleted, project_id)",
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
