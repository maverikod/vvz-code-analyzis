"""
Schema comparator for schema_sync.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import copy
import logging
from typing import Any, Dict, List, Set

from .schema_sync_comparator_compare import SchemaCompareOps
from .schema_sync_models import IndexDef, SchemaDiff, TableDiff
from . import schema_sync_sql
from . import schema_sync_virtual

logger = logging.getLogger(__name__)

# Tables that must have cst_node_id NOT NULL in final schema state (after backfill).
CST_NODE_ID_NOT_NULL_TABLES = ("classes", "functions", "methods")

# Snapshot/root/node tables (Step 02 schema). Invariant checks run when any exist.
FILE_TREE_SNAPSHOT_TABLES = (
    "file_tree_snapshots",
    "file_tree_snapshot_roots",
    "file_tree_snapshot_nodes",
)


class SchemaComparator:
    """
    Compares database schema with expected schema.

    Runs in same process as database driver (in worker process).
    """

    def __init__(self, driver: Any, schema_definition: Dict[str, Any]) -> None:
        """
        Initialize schema comparator.

        Args:
            driver: Database driver instance (SQLiteDriver in worker)
            schema_definition: Schema definition from CodeDatabase._get_schema_definition()
        """
        self.driver = driver
        self.schema_definition = self._apply_final_state_overrides(
            copy.deepcopy(schema_definition)
        )
        self._compare_ops = SchemaCompareOps(
            driver, self.schema_definition, FILE_TREE_SNAPSHOT_TABLES
        )

    def _apply_final_state_overrides(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply final schema state overrides (e.g. cst_node_id NOT NULL after backfill).
        """
        tables = schema.get("tables", {})
        for table_name in CST_NODE_ID_NOT_NULL_TABLES:
            if table_name not in tables:
                continue
            for col in tables[table_name].get("columns", []):
                if col.get("name") == "cst_node_id":
                    col["not_null"] = True
                    break
        return schema

    def compare_schemas(self) -> SchemaDiff:
        """Compare current DB schema with expected schema."""
        return self._compare_ops.compare_schemas()

    def validate_data_compatibility(self, diff: SchemaDiff) -> Dict[str, Any]:
        """
        Validate data compatibility BEFORE making changes.

        Returns:
            {
                "compatible": bool,
                "error": Optional[str],
                "warnings": List[str]
            }
        """
        warnings = []

        # Check if type changes are compatible
        for table_name, table_diff in diff.table_diffs.items():
            for col_name, old_type, new_type in table_diff.type_changes:
                # Basic compatibility check
                # SQLite is flexible with types, but warn about potential issues
                warnings.append(
                    f"Type change in {table_name}.{col_name}: {old_type} -> {new_type}"
                )

        # Check if NOT NULL constraints can be added to columns with NULLs
        for table_name, table_diff in diff.table_diffs.items():
            for col_def in table_diff.missing_columns:
                if col_def.not_null:
                    warnings.append(
                        f"Adding NOT NULL column {table_name}.{col_def.name} - ensure no NULLs exist"
                    )
            for ch in table_diff.constraint_changes:
                if ch.endswith(" NOT NULL"):
                    col_name = ch[: -len(" NOT NULL")].strip()
                    if self._compare_ops.column_has_nulls(table_name, col_name):
                        if (
                            table_name in CST_NODE_ID_NOT_NULL_TABLES
                            and col_name == "cst_node_id"
                        ):
                            warnings.append(
                                "Deferred NOT NULL enforcement for "
                                f"{table_name}.{col_name}: column has NULLs "
                                "(run backfill first)"
                            )
                            continue
                        return {
                            "compatible": False,
                            "error": (
                                f"Cannot enforce NOT NULL on {table_name}.{col_name}: "
                                "column has NULLs (run backfill first)"
                            ),
                            "warnings": warnings,
                        }
                    break

        return {"compatible": True, "error": None, "warnings": warnings}

    def validate_cst_node_id_not_null_state(self) -> Dict[str, Any]:
        """
        Run validation queries: no NULL cst_node_id and constraint active.

        Returns:
            {
                "ok": bool,
                "tables": { table_name: { "null_count": int, "column_not_null": bool } },
                "error": Optional[str]
            }
        """
        result: Dict[str, Any] = {"ok": True, "tables": {}, "error": None}
        for table_name in CST_NODE_ID_NOT_NULL_TABLES:
            if table_name not in self._compare_ops.get_current_tables():
                result["tables"][table_name] = {
                    "null_count": None,
                    "column_not_null": False,
                }
                result["ok"] = False
                continue
            try:
                null_row = self.driver.fetchone(
                    f"SELECT COUNT(*) AS c FROM {table_name} WHERE cst_node_id IS NULL"
                )
                null_count = int(null_row["c"]) if null_row else -1
                current_cols = self._compare_ops.get_table_columns(table_name)
                col_info = current_cols.get("cst_node_id", {})
                column_not_null = bool(col_info.get("not_null", False))
                result["tables"][table_name] = {
                    "null_count": null_count,
                    "column_not_null": column_not_null,
                }
                if null_count != 0 or not column_not_null:
                    result["ok"] = False
            except Exception as e:
                result["tables"][table_name] = {
                    "null_count": None,
                    "column_not_null": False,
                }
                result["ok"] = False
                result["error"] = str(e)
        return result

    def _recreate_virtual_table(
        self, table_name: str, virtual_table_def: Dict[str, Any]
    ) -> List[str]:
        """Generate SQL to recreate virtual table (delegate to schema_sync_virtual)."""
        return schema_sync_virtual.generate_recreate_virtual_table_sql(
            table_name, virtual_table_def
        )

    def _generate_create_table_sql(
        self, table_name: str, *, relax_cst_node_id_not_null: bool = False
    ) -> str:
        """Generate CREATE TABLE SQL for a table (delegate to schema_sync_sql)."""
        return schema_sync_sql.generate_create_table_sql(
            self.schema_definition,
            table_name,
            relax_cst_node_id_not_null=relax_cst_node_id_not_null,
        )

    def _generate_recreate_table_sql(
        self, table_name: str, table_diff: TableDiff, current_columns: Set[str]
    ) -> List[str]:
        """
        Generate SQL to recreate table with data migration.

        Args:
            table_name: Table name (new table will be created with this name)
            table_diff: Table differences
            current_columns: Set of current column names (before migration)

        Returns:
            List of SQL statements
        """
        statements = []
        temp_table = f"temp_{table_name}"

        # Get expected columns from schema definition
        expected_cols = {
            col["name"]
            for col in self.schema_definition["tables"][table_name]["columns"]
        }

        # Find common columns (columns that exist in both old and new schema)
        common_cols = expected_cols & current_columns

        # Create new table with correct structure
        relax_cst_not_null = (
            table_name in CST_NODE_ID_NOT_NULL_TABLES
            and "cst_node_id" in current_columns
            and self._compare_ops.column_has_nulls(table_name, "cst_node_id")
        )
        new_table_sql = schema_sync_sql.generate_create_table_sql(
            self.schema_definition,
            table_name,
            relax_cst_node_id_not_null=relax_cst_not_null,
        )
        statements.append(
            new_table_sql.replace("CREATE TABLE IF NOT EXISTS", "CREATE TABLE")
        )

        # Copy data from temp_table (old table was renamed to temp_table before this method is called).
        # If table has UNIQUE constraint(s), deduplicate by first unique key to avoid UNIQUE violation.
        if common_cols:
            col_list = ", ".join(sorted(common_cols))
            table_def = self.schema_definition["tables"][table_name]
            unique_constraints = table_def.get("unique_constraints", [])
            pk_col = None
            for col in table_def.get("columns", []):
                if col.get("primary_key"):
                    pk_col = col["name"]
                    break
            uc_cols = None
            if unique_constraints and unique_constraints[0]["columns"]:
                uc = unique_constraints[0]["columns"]
                if set(uc) <= common_cols:
                    uc_cols = uc
            if uc_cols and pk_col and pk_col in common_cols:
                partition_by = ", ".join(uc_cols)
                order_by = f"{pk_col} DESC"
                inner_cols = ", ".join(sorted(common_cols))
                statements.append(
                    f"INSERT INTO {table_name} ({col_list}) "
                    f"SELECT {inner_cols} FROM ("
                    f"SELECT {inner_cols}, ROW_NUMBER() OVER (PARTITION BY {partition_by} ORDER BY {order_by}) AS _rn "
                    f"FROM {temp_table}"
                    f") WHERE _rn = 1"
                )
            else:
                statements.append(
                    f"INSERT INTO {table_name} ({col_list}) SELECT {col_list} FROM {temp_table}"
                )

        # Drop old table
        statements.append(f"DROP TABLE {temp_table}")

        return statements

    def _generate_create_index_sql(self, index_def: IndexDef) -> str:
        """Generate CREATE INDEX SQL (delegate to schema_sync_sql)."""
        return schema_sync_sql.generate_create_index_sql(index_def)

    def _tables_recreate_order(self, table_names: Set[str]) -> List[str]:
        """Return table names in FK-safe order (delegate to schema_sync_sql)."""
        return schema_sync_sql.tables_recreate_order(
            self.schema_definition, table_names
        )

    def generate_migration_sql(self, diff: SchemaDiff) -> List[str]:
        """
        Generate SQL statements to apply schema changes.

        Handles:
        - CREATE TABLE for missing tables
        - ALTER TABLE ADD COLUMN for missing columns
        - Table recreation for type changes (with data migration)
        - Table recreation to enforce NOT NULL (e.g. cst_node_id) only when column has no NULLs
        - CREATE INDEX for missing indexes
        - DROP INDEX for extra indexes
        - Virtual table (FTS5) recreation with data preservation
        """
        statements = []

        # Create missing tables
        for table_name in diff.missing_tables:
            statements.append(self._generate_create_table_sql(table_name))

        # Handle table changes (columns, types, constraints).
        # Recreate tables in FK order (parents before children) to avoid FOREIGN KEY errors.
        tables_with_type_changes = {
            name for name, td in diff.table_diffs.items() if td.type_changes
        }
        # Add tables that need NOT NULL enforced (e.g. cst_node_id) only when no NULLs remain.
        tables_with_not_null_to_enforce: Set[str] = set()
        for name, td in diff.table_diffs.items():
            if name in tables_with_type_changes:
                continue
            for ch in td.constraint_changes:
                if ch.endswith(" NOT NULL"):
                    col_name = ch[: -len(" NOT NULL")].strip()
                    if not self._compare_ops.column_has_nulls(name, col_name):
                        tables_with_not_null_to_enforce.add(name)
                    else:
                        logger.warning(
                            "Skipping NOT NULL enforcement for %s.%s: column has NULLs (run backfill first)",
                            name,
                            col_name,
                        )
                    break
        tables_to_recreate = tables_with_type_changes | tables_with_not_null_to_enforce
        ordered_recreate = (
            self._tables_recreate_order(tables_to_recreate)
            if tables_to_recreate
            else []
        )
        for table_name in ordered_recreate:
            table_diff = diff.table_diffs[table_name]
            try:
                current_columns = set(
                    self._compare_ops.get_table_columns(table_name).keys()
                )
            except Exception:
                current_columns = set()
            temp_table = f"temp_{table_name}"
            statements.append(f"ALTER TABLE {table_name} RENAME TO {temp_table}")
            statements.extend(
                self._generate_recreate_table_sql(
                    table_name, table_diff, current_columns
                )
            )

        for table_name, table_diff in diff.table_diffs.items():
            if table_diff.type_changes:
                continue
            # Do not ADD COLUMN for tables we already recreated (new table has all columns).
            if table_name in tables_to_recreate:
                continue
            # Add missing columns (handles ALTER TABLE logic)
            # Note: SQLite doesn't support DEFAULT with functions in ALTER TABLE ADD COLUMN
            for col_def in table_diff.missing_columns:
                col_sql = f"{col_def.name} {col_def.type}"
                if col_def.not_null:
                    col_sql += " NOT NULL"
                if col_def.default:
                    default_val = col_def.default.strip()
                    is_function = (
                        "julianday" in default_val
                        or default_val.startswith("(")
                        or "(" in default_val
                    )
                    if not is_function:
                        col_sql += f" DEFAULT {col_def.default}"
                statements.append(f"ALTER TABLE {table_name} ADD COLUMN {col_sql}")

        # Handle virtual tables (FTS5)
        for (
            virtual_table_name,
            virtual_table_def,
        ) in diff.missing_virtual_tables.items():
            statements.extend(
                self._recreate_virtual_table(virtual_table_name, virtual_table_def)
            )

        # Recreate virtual tables if schema changed
        for (
            virtual_table_name,
            virtual_table_def,
        ) in diff.changed_virtual_tables.items():
            statements.extend(
                self._recreate_virtual_table(virtual_table_name, virtual_table_def)
            )

        # Create missing indexes
        for index_def in diff.missing_indexes:
            statements.append(self._generate_create_index_sql(index_def))

        # Drop extra indexes
        for index_name in diff.extra_indexes:
            statements.append(f"DROP INDEX IF EXISTS {index_name}")

        return statements
