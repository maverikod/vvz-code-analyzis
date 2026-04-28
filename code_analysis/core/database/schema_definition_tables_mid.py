"""
Mid-layer table definitions for code_analysis database schema (imports through code_chunks).

Identity and FK columns to core entities use logical UUID (PostgreSQL native UUID;
SQLite canonical TEXT via schema_sync_sql). Polymorphic references (Option A):
``code_content.entity_id`` and ``vector_index.entity_id`` are logical UUID without
FK enforcement; ``entity_type`` selects the semantic target table.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict


def get_tables_mid() -> Dict[str, Any]:
    """Return mid tables dict: imports, issues, usages, code_content, ast_trees, cst_trees, vector_index, code_chunks."""
    return {
        "imports": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "file_id", "type": "UUID", "not_null": True},
                {"name": "name", "type": "TEXT", "not_null": True},
                {"name": "module", "type": "TEXT", "not_null": False},
                {"name": "import_type", "type": "TEXT", "not_null": True},
                {"name": "line", "type": "INTEGER", "not_null": True},
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
            "unique_constraints": [],
            "check_constraints": [],
        },
        "issues": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "file_id", "type": "UUID", "not_null": False},
                {"name": "project_id", "type": "UUID", "not_null": False},
                {"name": "class_id", "type": "UUID", "not_null": False},
                {"name": "function_id", "type": "UUID", "not_null": False},
                {"name": "method_id", "type": "UUID", "not_null": False},
                {"name": "issue_type", "type": "TEXT", "not_null": True},
                {"name": "line", "type": "INTEGER", "not_null": False},
                {"name": "description", "type": "TEXT", "not_null": False},
                {"name": "metadata", "type": "TEXT", "not_null": False},
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
                },
                {
                    "columns": ["project_id"],
                    "references_table": "projects",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["class_id"],
                    "references_table": "classes",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["function_id"],
                    "references_table": "functions",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["method_id"],
                    "references_table": "methods",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": [],
            "check_constraints": [],
        },
        "usages": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "file_id", "type": "UUID", "not_null": True},
                {"name": "line", "type": "INTEGER", "not_null": True},
                {"name": "usage_type", "type": "TEXT", "not_null": True},
                {"name": "target_type", "type": "TEXT", "not_null": True},
                {"name": "target_class", "type": "TEXT", "not_null": False},
                {"name": "target_name", "type": "TEXT", "not_null": True},
                {"name": "context", "type": "TEXT", "not_null": False},
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
            "unique_constraints": [],
            "check_constraints": [],
        },
        "code_content": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "file_id", "type": "UUID", "not_null": True},
                {"name": "entity_type", "type": "TEXT", "not_null": True},
                {
                    "name": "entity_id",
                    "type": "UUID",
                    "not_null": False,
                },
                {"name": "entity_name", "type": "TEXT", "not_null": False},
                {"name": "content", "type": "TEXT", "not_null": True},
                {"name": "docstring", "type": "TEXT", "not_null": False},
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
            "unique_constraints": [],
            "check_constraints": [],
        },
        "ast_trees": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "file_id", "type": "UUID", "not_null": True},
                {"name": "project_id", "type": "UUID", "not_null": True},
                {"name": "ast_json", "type": "TEXT", "not_null": True},
                {"name": "ast_hash", "type": "TEXT", "not_null": True},
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
            "unique_constraints": [{"columns": ["file_id", "ast_hash"]}],
            "check_constraints": [],
        },
        "cst_trees": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "file_id", "type": "UUID", "not_null": True},
                {"name": "project_id", "type": "UUID", "not_null": True},
                {"name": "cst_code", "type": "TEXT", "not_null": True},
                {"name": "cst_hash", "type": "TEXT", "not_null": True},
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
            "unique_constraints": [{"columns": ["file_id", "cst_hash"]}],
            "check_constraints": [],
        },
        "vector_index": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "project_id", "type": "UUID", "not_null": True},
                {"name": "entity_type", "type": "TEXT", "not_null": True},
                {
                    "name": "entity_id",
                    "type": "UUID",
                    "not_null": True,
                },
                {"name": "vector_id", "type": "INTEGER", "not_null": True},
                {"name": "vector_dim", "type": "INTEGER", "not_null": True},
                {"name": "embedding_model", "type": "TEXT", "not_null": False},
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
            "unique_constraints": [
                {"columns": ["project_id", "entity_type", "entity_id"]}
            ],
            "check_constraints": [],
        },
        "code_chunks": {
            "columns": [
                {
                    "name": "id",
                    "type": "UUID",
                    "not_null": True,
                    "primary_key": True,
                },
                {"name": "file_id", "type": "UUID", "not_null": True},
                {"name": "project_id", "type": "UUID", "not_null": True},
                {"name": "chunk_uuid", "type": "TEXT", "not_null": True},
                {"name": "chunk_type", "type": "TEXT", "not_null": True},
                {"name": "chunk_text", "type": "TEXT", "not_null": True},
                {"name": "chunk_ordinal", "type": "INTEGER", "not_null": False},
                {"name": "vector_id", "type": "INTEGER", "not_null": False},
                {"name": "embedding_model", "type": "TEXT", "not_null": False},
                {"name": "bm25_score", "type": "REAL", "not_null": False},
                {"name": "embedding_vector", "type": "TEXT", "not_null": False},
                {"name": "token_count", "type": "INTEGER", "not_null": False},
                {"name": "class_id", "type": "UUID", "not_null": False},
                {"name": "function_id", "type": "UUID", "not_null": False},
                {"name": "method_id", "type": "UUID", "not_null": False},
                {"name": "line", "type": "INTEGER", "not_null": False},
                {"name": "ast_node_type", "type": "TEXT", "not_null": False},
                {"name": "source_type", "type": "TEXT", "not_null": False},
                {
                    "name": "binding_level",
                    "type": "INTEGER",
                    "not_null": False,
                    "default": "0",
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
                {
                    "name": "vectorization_skipped",
                    "type": "INTEGER",
                    "not_null": False,
                    "default": "0",
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
                {
                    "columns": ["class_id"],
                    "references_table": "classes",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["function_id"],
                    "references_table": "functions",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
                {
                    "columns": ["method_id"],
                    "references_table": "methods",
                    "references_columns": ["id"],
                    "on_delete": "CASCADE",
                },
            ],
            "unique_constraints": [{"columns": ["chunk_uuid"]}],
            "check_constraints": [],
        },
    }
