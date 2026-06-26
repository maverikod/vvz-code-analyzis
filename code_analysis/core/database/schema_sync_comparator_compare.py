"""
Schema comparison logic for SchemaComparator.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, List, Set, Tuple

from .schema_sync_models import ColumnDef, IndexDef, SchemaDiff, TableDiff

logger = logging.getLogger(__name__)


class SchemaCompareOps:
    """Comparison operations for schema sync (driver + schema_definition -> SchemaDiff)."""

    def __init__(
        self,
        driver: Any,
        schema_definition: Dict[str, Any],
        snapshot_tables: Tuple[str, ...],
    ) -> None:
        """Initialize the instance."""
        self.driver = driver
        self.schema_definition = schema_definition
        self.snapshot_tables = snapshot_tables

    def get_current_tables(self) -> Set[str]:
        """Get current table names from database."""
        result = self.driver.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return {row["name"] for row in result}

    def validate_snapshot_invariants(self, current_tables: Set[str]) -> None:
        """Validate snapshot/root/node invariants; raise RuntimeError if broken."""
        if "file_tree_snapshot_roots" in current_tables:
            try:
                rows = self.driver.fetchall(
                    "SELECT snapshot_id, COUNT(*) AS c FROM file_tree_snapshot_roots "
                    "GROUP BY snapshot_id HAVING COUNT(*) > 1"
                )
                if rows:
                    raise RuntimeError(
                        "Snapshot invariant violated: multiple roots per snapshot "
                        "(file_tree_snapshot_roots has duplicate snapshot_id)"
                    )
            except RuntimeError:
                raise
            except Exception as e:
                raise RuntimeError(
                    "Snapshot invariant check failed for file_tree_snapshot_roots"
                ) from e

        if "file_tree_snapshot_nodes" in current_tables:
            try:
                rows = self.driver.fetchall(
                    "SELECT snapshot_id, parent_node_id, child_index, COUNT(*) AS c "
                    "FROM file_tree_snapshot_nodes "
                    "GROUP BY snapshot_id, parent_node_id, child_index HAVING COUNT(*) > 1"
                )
                if rows:
                    raise RuntimeError(
                        "Snapshot invariant violated: duplicate sibling order "
                        "(file_tree_snapshot_nodes has duplicate "
                        "snapshot_id, parent_node_id, child_index); "
                        "sync path rejects invalid ordering"
                    )
            except RuntimeError:
                raise
            except Exception as e:
                raise RuntimeError(
                    "Snapshot invariant check failed for file_tree_snapshot_nodes"
                ) from e

    def get_current_virtual_tables(self) -> Dict[str, Dict[str, Any]]:
        """Get current virtual tables from database."""
        result = self.driver.fetchall(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql LIKE '%USING%'"
        )
        virtual_tables = {}
        for row in result:
            sql = row["sql"]
            name = row["name"]
            virtual_tables[name] = {"sql": sql, "name": name}
        return virtual_tables

    def virtual_table_changed(
        self, current: Dict[str, Any], expected: Dict[str, Any]
    ) -> bool:
        """Check if virtual table definition changed."""
        current_sql = current.get("sql", "").upper()
        expected_type = expected.get("type", "").upper()
        expected_columns = set(expected.get("columns", []))
        expected_options = expected.get("options", {})

        if expected_type not in current_sql:
            return True
        for col in expected_columns:
            if col.upper() not in current_sql:
                return True
        if expected_type == "FTS5":
            content_table = expected_options.get("content")
            if content_table:
                if f"CONTENT='{content_table.upper()}'" not in current_sql:
                    return True
        return False

    def compare_table(self, table_name: str) -> TableDiff:
        """Compare table structure."""
        current_cols = self.get_table_columns(table_name)
        expected_cols_def = self.schema_definition["tables"][table_name]["columns"]
        expected_cols = {
            col["name"]: ColumnDef(
                name=col["name"],
                type=col["type"],
                not_null=col.get("not_null", False),
                default=col.get("default"),
                primary_key=col.get("primary_key", False),
                autoincrement=col.get("autoincrement", False),
            )
            for col in expected_cols_def
        }

        missing_columns = []
        extra_columns = []
        type_changes: List[Tuple[str, str, str]] = []
        constraint_changes: List[str] = []

        for col_name, col_def in expected_cols.items():
            if col_name not in current_cols:
                missing_columns.append(col_def)
        for col_name in current_cols:
            if col_name not in expected_cols:
                extra_columns.append(col_name)
        for col_name, col_def in expected_cols.items():
            if col_name in current_cols:
                current_type = current_cols[col_name]["type"]
                if current_type.upper() != col_def.type.upper():
                    type_changes.append((col_name, current_type, col_def.type))
        for col_name, col_def in expected_cols.items():
            if col_def.primary_key:
                continue
            if col_name in current_cols and col_def.not_null:
                if not current_cols[col_name]["not_null"]:
                    constraint_changes.append(f"{col_name} NOT NULL")

        return TableDiff(
            missing_columns=missing_columns,
            extra_columns=extra_columns,
            type_changes=type_changes,
            constraint_changes=constraint_changes,
        )

    def get_table_columns(self, table_name: str) -> Dict[str, Dict[str, Any]]:
        """Get current table columns from database."""
        result = self.driver.fetchall(f"PRAGMA table_info({table_name})")
        columns = {}
        for row in result:
            columns[row["name"]] = {
                "name": row["name"],
                "type": row["type"],
                "not_null": bool(row["notnull"]),
                "default": row["dflt_value"],
                "primary_key": bool(row["pk"]),
            }
        return columns

    def column_has_nulls(self, table_name: str, column_name: str) -> bool:
        """Return True if the column has any NULL values."""
        try:
            row = self.driver.fetchone(
                f"SELECT 1 FROM {table_name} WHERE {column_name} IS NULL LIMIT 1"
            )
            return row is not None
        except Exception:
            return True

    def compare_indexes(self) -> List[IndexDef]:
        """Compare indexes using PRAGMA commands."""
        expected_indexes = self.schema_definition.get("indexes", [])
        missing_indexes = []
        current_indexes = self.get_current_indexes()

        for index_def_dict in expected_indexes:
            index_def = IndexDef(
                name=index_def_dict["name"],
                table=index_def_dict["table"],
                columns=index_def_dict["columns"],
                unique=index_def_dict.get("unique", False),
                where_clause=index_def_dict.get("where_clause"),
            )
            table_indexes = current_indexes.get(index_def.table, {})
            if index_def.name not in table_indexes:
                missing_indexes.append(index_def)
            else:
                current_idx = table_indexes[index_def.name]
                if not self._indexes_match(current_idx, index_def):
                    missing_indexes.append(index_def)
        return missing_indexes

    def get_current_indexes(self) -> Dict[str, Dict[str, IndexDef]]:
        """Get current indexes from database."""
        indexes: Dict[str, Dict[str, IndexDef]] = {}
        tables = self.get_current_tables()
        for table_name in tables:
            index_list = self.driver.fetchall(f"PRAGMA index_list({table_name})")
            table_indexes: Dict[str, IndexDef] = {}
            for idx_row in index_list:
                idx_name = idx_row["name"]
                if idx_name.startswith("sqlite_autoindex_"):
                    continue
                idx_info = self.driver.fetchall(f"PRAGMA index_info({idx_name})")
                columns = [row["name"] for row in idx_info]
                unique = bool(idx_row.get("unique", 0))
                table_indexes[idx_name] = IndexDef(
                    name=idx_name,
                    table=table_name,
                    columns=columns,
                    unique=unique,
                    where_clause=None,
                )
            if table_indexes:
                indexes[table_name] = table_indexes
        return indexes

    def _indexes_match(self, current: IndexDef, expected: IndexDef) -> bool:
        """Return indexes match."""
        return (
            current.table == expected.table
            and current.columns == expected.columns
            and current.unique == expected.unique
        )

    def find_extra_indexes(self) -> List[str]:
        """Find indexes that exist in DB but not in expected schema."""
        expected_indexes = {
            idx["name"] for idx in self.schema_definition.get("indexes", [])
        }
        current_indexes = self.get_current_indexes()
        extra = []
        for table_name, table_indexes in current_indexes.items():
            for idx_name in table_indexes:
                if idx_name not in expected_indexes:
                    extra.append(idx_name)
        return extra

    def compare_constraints(self) -> Dict[str, List[str]]:
        """Compare constraints (PK, FK, unique). Returns table -> list of descriptions."""
        constraint_diffs: Dict[str, List[str]] = {}
        expected_tables = self.schema_definition.get("tables", {})

        for table_name in expected_tables:
            changes = []
            expected_pk_cols = [
                col["name"]
                for col in expected_tables[table_name]["columns"]
                if col.get("primary_key", False)
            ]
            try:
                current_cols = self.get_table_columns(table_name)
                current_pk_cols = [
                    col_name
                    for col_name, col_info in current_cols.items()
                    if col_info.get("primary_key", False)
                ]
                if set(expected_pk_cols) != set(current_pk_cols):
                    changes.append(
                        f"Primary key changed: {current_pk_cols} -> {expected_pk_cols}"
                    )
            except Exception:
                pass
            try:
                expected_fks = expected_tables[table_name].get("foreign_keys", [])
                current_fks = self.get_current_foreign_keys(table_name)
                if not self._foreign_keys_match(expected_fks, current_fks):
                    changes.append("Foreign key constraints changed")
            except Exception:
                pass
            try:
                expected_unique = expected_tables[table_name].get(
                    "unique_constraints", []
                )
                current_unique = self.get_current_unique_constraints(table_name)
                if not self._unique_constraints_match(expected_unique, current_unique):
                    changes.append("Unique constraints changed")
            except Exception:
                pass
            if changes:
                constraint_diffs[table_name] = changes
        return constraint_diffs

    def get_current_foreign_keys(self, table_name: str) -> List[Dict[str, Any]]:
        """Get current foreign keys for a table."""
        try:
            fk_list = self.driver.fetchall(f"PRAGMA foreign_key_list({table_name})")
            return [
                {
                    "columns": [row["from"]],
                    "references_table": row["table"],
                    "references_columns": [row["to"]],
                    "on_delete": row.get("on_delete", ""),
                }
                for row in fk_list
            ]
        except Exception:
            return []

    def get_current_unique_constraints(
        self, table_name: str
    ) -> List[Dict[str, List[str]]]:
        """Get current unique constraints for a table."""
        try:
            out = []
            for idx_row in self.driver.fetchall(f"PRAGMA index_list({table_name})"):
                if idx_row["name"].startswith("sqlite_autoindex_") or not idx_row.get(
                    "unique", 0
                ):
                    continue
                cols = [
                    r["name"]
                    for r in self.driver.fetchall(
                        f"PRAGMA index_info({idx_row['name']})"
                    )
                ]
                if cols:
                    out.append({"columns": cols})
            return out
        except Exception:
            return []

    def _foreign_keys_match(
        self, expected: List[Dict[str, Any]], current: List[Dict[str, Any]]
    ) -> bool:
        """Return foreign keys match."""
        if len(expected) != len(current):
            return False

        def _fk_key(d: Dict[str, Any]) -> tuple:
            """Return fk key."""
            return (
                tuple(d["columns"]),
                d["references_table"],
                tuple(d["references_columns"]),
                d.get("on_delete", ""),
            )

        def _norm(fks: List[Dict[str, Any]]) -> list:
            """Return norm."""
            return [
                {
                    "columns": tuple(sorted(fk["columns"])),
                    "references_table": fk["references_table"],
                    "references_columns": tuple(sorted(fk["references_columns"])),
                    "on_delete": fk.get("on_delete", ""),
                }
                for fk in fks
            ]

        return sorted(_norm(expected), key=_fk_key) == sorted(
            _norm(current), key=_fk_key
        )

    def _unique_constraints_match(
        self,
        expected: List[Dict[str, List[str]]],
        current: List[Dict[str, List[str]]],
    ) -> bool:
        """Return unique constraints match."""
        if len(expected) != len(current):
            return False
        expected_sets = {tuple(sorted(uc["columns"])) for uc in expected}
        current_sets = {tuple(sorted(uc["columns"])) for uc in current}
        return expected_sets == current_sets

    def compare_schemas(self) -> SchemaDiff:
        """Compare current DB schema with expected schema; return SchemaDiff."""
        current_tables = self.get_current_tables()
        expected_tables = set(self.schema_definition.get("tables", {}).keys())
        current_virtual_tables = self.get_current_virtual_tables()
        expected_virtual_tables = self.schema_definition.get("virtual_tables", [])
        diff = SchemaDiff(
            missing_tables=expected_tables - current_tables,
            extra_tables=current_tables - expected_tables,
            table_diffs={},
            missing_indexes=[],
            extra_indexes=[],
            constraint_diffs={},
            missing_virtual_tables={},
            changed_virtual_tables={},
        )
        for table_name in expected_tables & current_tables:
            table_diff = self.compare_table(table_name)
            if table_diff.has_changes():
                diff.table_diffs[table_name] = table_diff

        for vt_def in expected_virtual_tables:
            vt_name = vt_def["name"]
            if vt_name not in current_virtual_tables:
                diff.missing_virtual_tables[vt_name] = vt_def
            else:
                current_vt = current_virtual_tables[vt_name]
                if self.virtual_table_changed(current_vt, vt_def):
                    diff.changed_virtual_tables[vt_name] = vt_def
        diff.missing_indexes = self.compare_indexes()
        diff.extra_indexes = self.find_extra_indexes()
        diff.constraint_diffs = self.compare_constraints()
        if current_tables & set(self.snapshot_tables):
            self.validate_snapshot_invariants(current_tables)
        return diff
