"""
Rest (remaining) table definitions for code_analysis database schema.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict


def get_tables_rest() -> Dict[str, Any]:
    """Return rest tables dict: code_duplicates, duplicate_occurrences, comprehensive_analysis_results, file_watcher_stats, vectorization_stats, indexing_errors, indexing_worker_stats, file_tree_snapshots, file_tree_snapshot_roots, file_tree_snapshot_nodes, project_activity_locks, client_sessions, session_file_locks, roles, role_permissions, session_roles."""
    return {
        "code_duplicates": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "project_id", "type": "UUID", "not_null": True},
                {"name": "duplicate_hash", "type": "TEXT", "not_null": True},
                {"name": "similarity", "type": "REAL", "not_null": True},
                {
                    "name": "created_at",
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
                }
            ],
            "unique_constraints": [{"columns": ["project_id", "duplicate_hash"]}],
            "check_constraints": [],
        },
        "duplicate_occurrences": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "duplicate_id", "type": "UUID", "not_null": True},
                {"name": "file_id", "type": "UUID", "not_null": True},
                {"name": "start_line", "type": "INTEGER", "not_null": True},
                {"name": "end_line", "type": "INTEGER", "not_null": True},
                {"name": "code_snippet", "type": "TEXT", "not_null": False},
                {"name": "ast_node_id", "type": "INTEGER", "not_null": False},
                {
                    "name": "created_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
            ],
            "foreign_keys": [
                {
                    "columns": ["duplicate_id"],
                    "references_table": "code_duplicates",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["file_id"],
                    "references_table": "files",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": [],
            "check_constraints": [],
        },
        "comprehensive_analysis_results": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "file_id", "type": "UUID", "not_null": True},
                {"name": "project_id", "type": "UUID", "not_null": True},
                {"name": "file_mtime", "type": "REAL", "not_null": True},
                {"name": "results_json", "type": "TEXT", "not_null": True},
                {"name": "summary_json", "type": "TEXT", "not_null": True},
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
                    "columns": ["file_id"],
                    "references_table": "files",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["project_id"],
                    "references_table": "projects",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": [{"columns": ["file_id", "file_mtime"]}],
            "check_constraints": [],
        },
        "file_watcher_stats": {
            "columns": [
                {
                    "name": "cycle_id",
                    "type": "TEXT",
                    "not_null": True,
                    "primary_key": True,
                },
                {
                    "name": "cycle_start_time",
                    "type": "REAL",
                    "not_null": True,
                },
                {"name": "cycle_end_time", "type": "REAL", "not_null": False},
                {
                    "name": "files_total_at_start",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "0",
                },
                {
                    "name": "files_added",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "0",
                },
                {
                    "name": "files_processed",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "0",
                },
                {
                    "name": "files_skipped",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "0",
                },
                {
                    "name": "files_failed",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "0",
                },
                {
                    "name": "files_changed",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "0",
                },
                {
                    "name": "files_deleted",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "0",
                },
                {
                    "name": "total_processing_time_seconds",
                    "type": "REAL",
                    "not_null": True,
                    "default": "0.0",
                },
                {
                    "name": "average_processing_time_seconds",
                    "type": "REAL",
                    "not_null": False,
                },
                {
                    "name": "last_updated",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
                {
                    "name": "current_project_id",
                    "type": "TEXT",
                    "not_null": False,
                },
            ],
            "foreign_keys": [],
            "unique_constraints": [],
            "check_constraints": [],
        },
        "vectorization_stats": {
            "columns": [
                {
                    "name": "cycle_id",
                    "type": "TEXT",
                    "not_null": True,
                    "primary_key": True,
                },
                {
                    "name": "cycle_start_time",
                    "type": "REAL",
                    "not_null": True,
                },
                {"name": "cycle_end_time", "type": "REAL", "not_null": False},
                {
                    "name": "chunks_total_at_start",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "0",
                },
                {
                    "name": "chunks_processed",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "0",
                },
                {
                    "name": "chunks_skipped",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "0",
                },
                {
                    "name": "chunks_failed",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "0",
                },
                {
                    "name": "files_total_at_start",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "0",
                },
                {
                    "name": "files_vectorized",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "0",
                },
                {
                    "name": "total_processing_time_seconds",
                    "type": "REAL",
                    "not_null": True,
                    "default": "0.0",
                },
                {
                    "name": "average_processing_time_seconds",
                    "type": "REAL",
                    "not_null": False,
                },
                {
                    "name": "last_updated",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
            ],
            "foreign_keys": [],
            "unique_constraints": [],
            "check_constraints": [],
        },
        "indexing_errors": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "project_id", "type": "UUID", "not_null": True},
                {"name": "file_path", "type": "TEXT", "not_null": True},
                {"name": "error_type", "type": "TEXT", "not_null": False},
                {"name": "error_message", "type": "TEXT", "not_null": False},
                {
                    "name": "created_at",
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
                }
            ],
            "unique_constraints": [{"columns": ["project_id", "file_path"]}],
            "check_constraints": [],
        },
        "indexing_worker_stats": {
            "columns": [
                {
                    "name": "cycle_id",
                    "type": "TEXT",
                    "not_null": True,
                    "primary_key": True,
                },
                {
                    "name": "cycle_start_time",
                    "type": "REAL",
                    "not_null": True,
                },
                {"name": "cycle_end_time", "type": "REAL", "not_null": False},
                {
                    "name": "files_total_at_start",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "0",
                },
                {
                    "name": "files_indexed",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "0",
                },
                {
                    "name": "files_failed",
                    "type": "INTEGER",
                    "not_null": True,
                    "default": "0",
                },
                {
                    "name": "total_processing_time_seconds",
                    "type": "REAL",
                    "not_null": True,
                    "default": "0.0",
                },
                {
                    "name": "average_processing_time_seconds",
                    "type": "REAL",
                    "not_null": False,
                },
                {
                    "name": "last_updated",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
            ],
            "foreign_keys": [],
            "unique_constraints": [],
            "check_constraints": [],
        },
        "file_tree_snapshots": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "file_id", "type": "UUID", "not_null": True},
                {"name": "project_id", "type": "UUID", "not_null": True},
                {"name": "source_payload", "type": "TEXT", "not_null": True},
                {"name": "file_mtime", "type": "REAL", "not_null": True},
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
                    "columns": ["file_id"],
                    "references_table": "files",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["project_id"],
                    "references_table": "projects",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": [{"columns": ["file_id"]}],
            "check_constraints": [],
        },
        "file_tree_snapshot_roots": {
            "columns": [
                {
                    "name": "snapshot_id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "root_node_id", "type": "TEXT", "not_null": True},
            ],
            "foreign_keys": [
                {
                    "columns": ["snapshot_id"],
                    "references_table": "file_tree_snapshots",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": [],
            "check_constraints": [],
        },
        "file_tree_snapshot_nodes": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "snapshot_id", "type": "UUID", "not_null": True},
                {"name": "node_id", "type": "TEXT", "not_null": True},
                {"name": "parent_node_id", "type": "TEXT", "not_null": False},
                {"name": "child_index", "type": "INTEGER", "not_null": True},
            ],
            "foreign_keys": [
                {
                    "columns": ["snapshot_id"],
                    "references_table": "file_tree_snapshots",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": [
                {"columns": ["snapshot_id", "node_id"]},
                {"columns": ["snapshot_id", "parent_node_id", "child_index"]},
            ],
            "check_constraints": [],
        },
        "project_activity_locks": {
            "columns": [
                {
                    "name": "project_id",
                    "type": "TEXT",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "owner_type", "type": "TEXT", "not_null": True},
                {"name": "owner_id", "type": "TEXT", "not_null": True},
                {"name": "activity", "type": "TEXT", "not_null": True},
                {"name": "acquired_at", "type": "REAL", "not_null": True},
                {"name": "heartbeat_at", "type": "REAL", "not_null": True},
                {"name": "lease_until", "type": "REAL", "not_null": True},
            ],
            "foreign_keys": [],
            "unique_constraints": [],
            "check_constraints": [],
        },
        "client_sessions": {
            "columns": [
                {
                    "name": "session_id",
                    "type": "TEXT",
                    "not_null": True,
                    "primary_key": True,
                },
                {
                    "name": "comment",
                    "type": "TEXT",
                    "not_null": True,
                    "default": "''",
                },
                {
                    "name": "created_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
                {
                    "name": "last_active_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
            ],
            "foreign_keys": [],
            "unique_constraints": [],
            "check_constraints": [],
        },
        "session_file_locks": {
            "columns": [
                {"name": "session_id", "type": "TEXT", "not_null": True},
                {"name": "project_id", "type": "UUID", "not_null": True},
                {"name": "file_id", "type": "UUID", "not_null": True},
                {
                    "name": "locked_at",
                    "type": "REAL",
                    "not_null": False,
                    "default": "julianday('now')",
                },
            ],
            "foreign_keys": [
                {
                    "columns": ["session_id"],
                    "references_table": "client_sessions",
                    "references_columns": ["session_id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["project_id"],
                    "references_table": "projects",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["file_id"],
                    "references_table": "files",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": [
                {"columns": ["session_id", "project_id", "file_id"]}
            ],
            "check_constraints": [],
        },
        "roles": {
            "columns": [
                {
                    "name": "role_id",
                    "type": "TEXT",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "name", "type": "TEXT", "not_null": True},
            ],
            "foreign_keys": [],
            "unique_constraints": [{"columns": ["name"]}],
            "check_constraints": [],
        },
        "role_permissions": {
            "columns": [
                {"name": "role_id", "type": "TEXT", "not_null": True},
                {"name": "command_name", "type": "TEXT", "not_null": True},
                {"name": "server_uuid", "type": "TEXT", "not_null": True},
            ],
            "foreign_keys": [
                {
                    "columns": ["role_id"],
                    "references_table": "roles",
                    "references_columns": ["role_id"],
                    "on_delete": "CASCADE",
                }
            ],
            "unique_constraints": [
                {"columns": ["role_id", "command_name", "server_uuid"]}
            ],
            "check_constraints": [],
        },
        "session_roles": {
            "columns": [
                {"name": "session_id", "type": "TEXT", "not_null": True},
                {"name": "role_id", "type": "TEXT", "not_null": True},
            ],
            "foreign_keys": [
                {
                    "columns": ["session_id"],
                    "references_table": "client_sessions",
                    "references_columns": ["session_id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["role_id"],
                    "references_table": "roles",
                    "references_columns": ["role_id"],
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": [{"columns": ["session_id", "role_id"]}],
            "check_constraints": [],
        },
        "subordinate_sessions": {
            "columns": [
                {"name": "parent_session_id", "type": "TEXT", "not_null": True},
                {"name": "subordinate_session_id", "type": "TEXT", "not_null": True},
                {"name": "server_uuid", "type": "TEXT", "not_null": True},
                {
                    "name": "comment",
                    "type": "TEXT",
                    "not_null": True,
                    "default": "''",
                },
            ],
            "foreign_keys": [
                {
                    "columns": ["parent_session_id"],
                    "references_table": "client_sessions",
                    "references_columns": ["session_id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["subordinate_session_id"],
                    "references_table": "client_sessions",
                    "references_columns": ["session_id"],
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": [
                {
                    "columns": [
                        "parent_session_id",
                        "subordinate_session_id",
                        "server_uuid",
                    ]
                }
            ],
            "check_constraints": [],
        },
    }
