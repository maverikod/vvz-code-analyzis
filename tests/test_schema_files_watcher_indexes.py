"""
Schema registry includes watcher-oriented files indexes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from code_analysis.core.database.schema_definition_indexes import get_schema_indexes


def test_files_watcher_indexes_in_registry() -> None:
    by_name = {idx["name"]: idx for idx in get_schema_indexes()}
    assert "idx_files_unique_project_path" in by_name
    assert by_name["idx_files_unique_project_path"]["unique"] is True
    assert by_name["idx_files_unique_project_path"]["columns"] == [
        "project_id",
        "path",
    ]
    assert "idx_files_active_project_path" in by_name
    assert "(deleted = 0 OR deleted IS NULL)" in (
        by_name["idx_files_active_project_path"]["where_clause"] or ""
    )
    assert "idx_files_active_project_relative_path" in by_name
    rel = by_name["idx_files_active_project_relative_path"]
    assert rel["columns"] == ["project_id", "relative_path"]
    assert "relative_path IS NOT NULL" in (rel["where_clause"] or "")
