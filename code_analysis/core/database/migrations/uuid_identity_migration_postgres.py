"""
PostgreSQL DDL for UUID migration mapping tables — native ``new_id UUID``.

Row copy, shadow UUID tables, validation, and optional swap live in
:mod:`code_analysis.core.database.migrations.uuid_identity_postgres_data_migrate`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List


def create_mapping_tables_postgres() -> List[str]:
    """``CREATE TABLE IF NOT EXISTS uuid_migration_*`` for PostgreSQL."""
    tmpl = """
CREATE TABLE IF NOT EXISTS {name} (
    old_id INTEGER NOT NULL PRIMARY KEY,
    new_id UUID NOT NULL UNIQUE
);"""
    names = (
        "uuid_migration_files",
        "uuid_migration_classes",
        "uuid_migration_methods",
        "uuid_migration_functions",
        "uuid_migration_entity_cross_ref",
        "uuid_migration_imports",
        "uuid_migration_issues",
        "uuid_migration_usages",
        "uuid_migration_code_content",
        "uuid_migration_ast_trees",
        "uuid_migration_cst_trees",
        "uuid_migration_vector_index",
        "uuid_migration_code_chunks",
        "uuid_migration_code_duplicates",
        "uuid_migration_duplicate_occurrences",
        "uuid_migration_comprehensive_analysis_results",
        "uuid_migration_file_tree_snapshots",
        "uuid_migration_file_tree_snapshot_nodes",
        "uuid_migration_indexing_errors",
    )
    return [tmpl.format(name=n).strip() for n in names]
