"""
Core table definitions for code_analysis database schema (db_settings through entity_cross_ref).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict


def get_tables_core() -> Dict[str, Any]:
    """Return core tables dict: db_settings, watch_dirs, watch_dir_paths, projects, files, classes, methods, functions, entity_cross_ref."""
    return {
        "db_settings": {
            "columns": [
                {
                    "name": "key",
                    "type": "TEXT",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "value", "type": "TEXT", "not_null": True},
                {
                    "name": "updated_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
            ],
            "foreign_keys": [],
            "unique_constraints": [],
            "check_constraints": [],
        },
        "runtime_lock_sessions": {
            "columns": [
                {
                    "name": "session_id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "pid", "type": "INTEGER", "not_null": True},
                {"name": "listener_url", "type": "TEXT", "not_null": False},
                {"name": "role", "type": "TEXT", "not_null": True},
                {"name": "hostname", "type": "TEXT", "not_null": False},
                {
                    "name": "started_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
                {
                    "name": "updated_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
            ],
            "foreign_keys": [],
            "unique_constraints": [{"columns": ["pid"]}],
            "check_constraints": [],
        },
        "watch_dirs": {
            "columns": [
                {
                    "name": "server_instance_id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "name", "type": "TEXT", "not_null": False},
                {
                    "name": "created_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
                {
                    "name": "updated_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
                {
                    "name": "deleted",
                    "type": "BOOLEAN",
                    "not_null": False,
                    "default": "0",
                },
            ],
            "foreign_keys": [],
            # Composite PK is (server_instance_id, id), but a watch directory id is
            # a globally-unique UUID by design (the watch dir is the top of the
            # chain; project/file copies may live inside, but the dir id is unique).
            # Declare id UNIQUE so single-column FKs that reference watch_dirs(id)
            # (e.g. files.watch_dir_id) are valid on PostgreSQL and pass SQLite
            # foreign_keys=ON checks.
            "unique_constraints": [{"columns": ["id"]}],
            "check_constraints": [],
        },
        "watch_dir_paths": {
            "columns": [
                {
                    "name": "server_instance_id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {
                    "name": "watch_dir_id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "absolute_path", "type": "TEXT", "not_null": False},
                {
                    "name": "created_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
                {
                    "name": "updated_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
            ],
            "foreign_keys": [
                {
                    "columns": ["server_instance_id", "watch_dir_id"],
                    "references_table": "watch_dirs",
                    "references_columns": ["server_instance_id", "id"],
                    "on_delete": "CASCADE",
                }
            ],
            "unique_constraints": [],
            "check_constraints": [],
        },
        "projects": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {
                    "name": "server_instance_id",
                    "type": "UUID",
                    "not_null": True,
                },
                {"name": "root_path", "type": "TEXT", "not_null": True},
                {"name": "name", "type": "TEXT", "not_null": False},
                {"name": "comment", "type": "TEXT", "not_null": False},
                {"name": "watch_dir_id", "type": "UUID", "not_null": False},
                {
                    "name": "created_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
                {
                    "name": "updated_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
                {
                    "name": "deleted",
                    "type": "BOOLEAN",
                    "not_null": False,
                    "default": "0",
                },
                {
                    "name": "processing_paused",
                    "type": "BOOLEAN",
                    "not_null": False,
                    "default": "0",
                },
            ],
            "foreign_keys": [
                {
                    "columns": ["server_instance_id", "watch_dir_id"],
                    "references_table": "watch_dirs",
                    "references_columns": ["server_instance_id", "id"],
                    "on_delete": "SET NULL",
                }
            ],
            "unique_constraints": [
                {"columns": ["server_instance_id", "watch_dir_id", "root_path"]}
            ],
            "check_constraints": [],
        },
        "files": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "project_id", "type": "UUID", "not_null": True},
                {"name": "watch_dir_id", "type": "UUID", "not_null": False},
                {"name": "path", "type": "TEXT", "not_null": True},
                {"name": "relative_path", "type": "TEXT", "not_null": False},
                {"name": "lines", "type": "INTEGER", "not_null": False},
                {"name": "last_modified", "type": "REAL", "not_null": False},
                {"name": "has_docstring", "type": "BOOLEAN", "not_null": False},
                {"name": "tree_checksum", "type": "TEXT", "not_null": False},
                {
                    "name": "deleted",
                    "type": "BOOLEAN",
                    "not_null": False,
                    "default": "0",
                },
                {"name": "original_path", "type": "TEXT", "not_null": False},
                {"name": "version_dir", "type": "TEXT", "not_null": False},
                {
                    "name": "needs_chunking",
                    "type": "INTEGER",
                    "not_null": False,
                    "default": "0",
                },
                {
                    "name": "editing_pid",
                    "type": "INTEGER",
                    "not_null": False,
                },
                {
                    "name": "created_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
                {
                    "name": "updated_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
            ],
            "foreign_keys": [
                {
                    "columns": ["project_id"],
                    "references_table": "projects",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["watch_dir_id"],
                    "references_table": "watch_dirs",
                    "references_columns": ["id"],
                    "on_delete": "SET NULL",
                },
            ],
            "unique_constraints": [{"columns": ["project_id", "path"]}],
            "check_constraints": [],
        },
        "file_advisory_lock_leases": {
            "columns": [
                {"name": "session_id", "type": "UUID", "not_null": True},
                {"name": "project_id", "type": "UUID", "not_null": True},
                {"name": "file_path", "type": "TEXT", "not_null": True},
                {"name": "lock_mode", "type": "TEXT", "not_null": True},
                {
                    "name": "locked_since",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
                {
                    "name": "updated_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
                {
                    "name": "refcount",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "1",
                },
            ],
            "foreign_keys": [
                {
                    "columns": ["session_id"],
                    "references_table": "runtime_lock_sessions",
                    "references_columns": ["session_id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["project_id"],
                    "references_table": "projects",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": [
                {"columns": ["session_id", "project_id", "file_path", "lock_mode"]}
            ],
            "check_constraints": [
                "lock_mode IN ('exclusive', 'shared')",
                "refcount > 0",
            ],
        },
        "classes": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "file_id", "type": "UUID", "not_null": True},
                {"name": "name", "type": "TEXT", "not_null": True},
                {"name": "line", "type": "INTEGER", "not_null": True},
                {"name": "end_line", "type": "INTEGER", "not_null": False},
                {"name": "cst_node_id", "type": "TEXT", "not_null": False},
                {"name": "docstring", "type": "TEXT", "not_null": False},
                {"name": "bases", "type": "TEXT", "not_null": False},
                {
                    "name": "created_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
            ],
            "foreign_keys": [
                {
                    "columns": ["file_id"],
                    "references_table": "files",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                }
            ],
            "unique_constraints": [{"columns": ["file_id", "name", "line"]}],
            "check_constraints": [],
        },
        "methods": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "class_id", "type": "UUID", "not_null": True},
                {"name": "name", "type": "TEXT", "not_null": True},
                {"name": "line", "type": "INTEGER", "not_null": True},
                {"name": "end_line", "type": "INTEGER", "not_null": False},
                {"name": "cst_node_id", "type": "TEXT", "not_null": False},
                {"name": "args", "type": "TEXT", "not_null": False},
                {"name": "docstring", "type": "TEXT", "not_null": False},
                {
                    "name": "is_abstract",
                    "type": "BOOLEAN",
                    "not_null": False,
                    "default": "0",
                },
                {
                    "name": "has_pass",
                    "type": "BOOLEAN",
                    "not_null": False,
                    "default": "0",
                },
                {
                    "name": "has_not_implemented",
                    "type": "BOOLEAN",
                    "not_null": False,
                    "default": "0",
                },
                {"name": "complexity", "type": "INTEGER", "not_null": False},
                {
                    "name": "created_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
            ],
            "foreign_keys": [
                {
                    "columns": ["class_id"],
                    "references_table": "classes",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                }
            ],
            "unique_constraints": [{"columns": ["class_id", "name", "line"]}],
            "check_constraints": [],
        },
        "functions": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "file_id", "type": "UUID", "not_null": True},
                {"name": "name", "type": "TEXT", "not_null": True},
                {"name": "line", "type": "INTEGER", "not_null": True},
                {"name": "end_line", "type": "INTEGER", "not_null": False},
                {"name": "cst_node_id", "type": "TEXT", "not_null": False},
                {"name": "args", "type": "TEXT", "not_null": False},
                {"name": "docstring", "type": "TEXT", "not_null": False},
                {"name": "complexity", "type": "INTEGER", "not_null": False},
                {
                    "name": "created_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
            ],
            "foreign_keys": [
                {
                    "columns": ["file_id"],
                    "references_table": "files",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                }
            ],
            "unique_constraints": [{"columns": ["file_id", "name", "line"]}],
            "check_constraints": [],
        },
        "entity_cross_ref": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "caller_class_id", "type": "UUID", "not_null": False},
                {"name": "caller_method_id", "type": "UUID", "not_null": False},
                {
                    "name": "caller_function_id",
                    "type": "UUID",
                    "not_null": False,
                },
                {"name": "callee_class_id", "type": "UUID", "not_null": False},
                {"name": "callee_method_id", "type": "UUID", "not_null": False},
                {
                    "name": "callee_function_id",
                    "type": "UUID",
                    "not_null": False,
                },
                {"name": "ref_type", "type": "TEXT", "not_null": True},
                {"name": "file_id", "type": "UUID", "not_null": False},
                {"name": "line", "type": "INTEGER", "not_null": False},
                {
                    "name": "created_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
            ],
            "foreign_keys": [
                {
                    "columns": ["caller_class_id"],
                    "references_table": "classes",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["caller_method_id"],
                    "references_table": "methods",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["caller_function_id"],
                    "references_table": "functions",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["callee_class_id"],
                    "references_table": "classes",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["callee_method_id"],
                    "references_table": "methods",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["callee_function_id"],
                    "references_table": "functions",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["file_id"],
                    "references_table": "files",
                    "references_columns": ["id"],
                    "on_delete": "SET NULL",
                },
            ],
            "unique_constraints": [],
            "check_constraints": [],
        },
    }
