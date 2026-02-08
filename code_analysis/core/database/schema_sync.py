"""
Schema synchronization module.

Compares database schema with expected schema and generates migration SQL.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from dataclasses import dataclass
from typing import Dict, List, Set, Any, Optional, Tuple
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class ColumnDef:
    """Column definition."""

    name: str
    type: str
    not_null: bool = False
    default: Optional[str] = None
    primary_key: bool = False
    autoincrement: bool = False


@dataclass
class IndexDef:
    """Index definition."""

    name: str
    table: str
    columns: List[str]
    unique: bool = False
    where_clause: Optional[str] = None


@dataclass
class TableDiff:
    """Table structure differences."""

    missing_columns: List[ColumnDef]
    extra_columns: List[str]  # column names
    type_changes: List[Tuple[str, str, str]]  # (col_name, old_type, new_type)
    constraint_changes: List[str]

    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(
            self.missing_columns
            or self.extra_columns
            or self.type_changes
            or self.constraint_changes
        )


@dataclass
class SchemaDiff:
    """Schema differences."""

    missing_tables: Set[str]
    extra_tables: Set[str]
    table_diffs: Dict[str, TableDiff]  # table_name -> TableDiff
    missing_indexes: List[IndexDef]
    extra_indexes: List[str]  # index names
    constraint_diffs: Dict[str, List[str]]  # table_name -> constraint changes
    missing_virtual_tables: Dict[
        str, Dict[str, Any]
    ]  # virtual table name -> definition
    changed_virtual_tables: Dict[
        str, Dict[str, Any]
    ]  # virtual table name -> new definition

    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(
            self.missing_tables
            or self.extra_tables
            or self.table_diffs
            or self.missing_indexes
            or self.extra_indexes
            or self.constraint_diffs
            or self.missing_virtual_tables
            or self.changed_virtual_tables
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
        self.schema_definition = schema_definition

    def compare_schemas(self) -> SchemaDiff:
        """Compare current DB schema with expected schema."""
        # Get current schema from DB
        current_tables = self._get_current_tables()
        expected_tables = set(self.schema_definition.get("tables", {}).keys())

        # Get virtual tables
        current_virtual_tables = self._get_current_virtual_tables()
        expected_virtual_tables = self.schema_definition.get("virtual_tables", [])

        # Compare tables
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

        # Compare columns, indexes, constraints for each table
        for table_name in expected_tables & current_tables:
            table_diff = self._compare_table(table_name)
            if table_diff.has_changes():
                diff.table_diffs[table_name] = table_diff

        # Compare virtual tables
        for vt_def in expected_virtual_tables:
            vt_name = vt_def["name"]
            if vt_name not in current_virtual_tables:
                diff.missing_virtual_tables[vt_name] = vt_def
            else:
                # Check if virtual table definition changed
                current_vt = current_virtual_tables[vt_name]
                if self._virtual_table_changed(current_vt, vt_def):
                    diff.changed_virtual_tables[vt_name] = vt_def

        # Compare indexes
        diff.missing_indexes = self._compare_indexes()
        diff.extra_indexes = self._find_extra_indexes()

        # Compare constraints
        diff.constraint_diffs = self._compare_constraints()

        return diff

    def _get_current_tables(self) -> Set[str]:
        """Get current table names from database."""
        result = self.driver.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return {row["name"] for row in result}

    def _get_current_virtual_tables(self) -> Dict[str, Dict[str, Any]]:
        """Get current virtual tables from database."""
        result = self.driver.fetchall(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql LIKE '%USING%'"
        )
        virtual_tables = {}
        for row in result:
            # Parse virtual table definition from SQL
            # This is a simplified parser - may need enhancement
            sql = row["sql"]
            name = row["name"]
            # Extract type (FTS5, etc.) and columns from SQL
            # For now, store raw SQL for comparison
            virtual_tables[name] = {"sql": sql, "name": name}
        return virtual_tables

    def _virtual_table_changed(
        self, current: Dict[str, Any], expected: Dict[str, Any]
    ) -> bool:
        """Check if virtual table definition changed."""
        # Compare columns, type, options
        current_sql = current.get("sql", "").upper()
        expected_type = expected.get("type", "").upper()
        expected_columns = set(expected.get("columns", []))
        expected_options = expected.get("options", {})

        # Check type
        if expected_type not in current_sql:
            return True

        # Check columns - extract from SQL or compare with expected
        # For FTS5, columns are listed in CREATE VIRTUAL TABLE statement
        # Simple check: if any expected column is missing from SQL, consider changed
        for col in expected_columns:
            if col.upper() not in current_sql:
                return True

        # For FTS5 with content table, check if content option matches
        if expected_type == "FTS5":
            content_table = expected_options.get("content")
            if content_table:
                # Check if content='table_name' is in SQL
                if f"CONTENT='{content_table.upper()}'" not in current_sql:
                    return True

        # If we get here, basic structure matches
        # Note: This is a simplified check - full comparison would require SQL parsing
        # For safety, we could return True to force recreation, but for now return False
        # if basic structure matches
        return False

    def _compare_table(self, table_name: str) -> TableDiff:
        """Compare table structure."""
        current_cols = self._get_table_columns(table_name)
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
        type_changes = []
        constraint_changes = []

        # Check for missing columns
        for col_name, col_def in expected_cols.items():
            if col_name not in current_cols:
                missing_columns.append(col_def)

        # Check for extra columns
        for col_name in current_cols:
            if col_name not in expected_cols:
                extra_columns.append(col_name)

        # Check for type changes
        for col_name, col_def in expected_cols.items():
            if col_name in current_cols:
                current_type = current_cols[col_name]["type"]
                if current_type.upper() != col_def.type.upper():
                    type_changes.append((col_name, current_type, col_def.type))

        return TableDiff(
            missing_columns=missing_columns,
            extra_columns=extra_columns,
            type_changes=type_changes,
            constraint_changes=constraint_changes,
        )

    def _get_table_columns(self, table_name: str) -> Dict[str, Dict[str, Any]]:
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

    def _compare_indexes(self) -> List[IndexDef]:
        """Compare indexes using PRAGMA commands."""
        expected_indexes = self.schema_definition.get("indexes", [])
        missing_indexes = []

        # Get current indexes for each table
        current_indexes = self._get_current_indexes()

        for index_def_dict in expected_indexes:
            index_def = IndexDef(
                name=index_def_dict["name"],
                table=index_def_dict["table"],
                columns=index_def_dict["columns"],
                unique=index_def_dict.get("unique", False),
                where_clause=index_def_dict.get("where_clause"),
            )

            # Check if index exists with same definition
            table_indexes = current_indexes.get(index_def.table, {})
            if index_def.name not in table_indexes:
                missing_indexes.append(index_def)
            else:
                # Compare definition
                current_idx = table_indexes[index_def.name]
                if not self._indexes_match(current_idx, index_def):
                    missing_indexes.append(index_def)

        return missing_indexes

    def _get_current_indexes(self) -> Dict[str, Dict[str, IndexDef]]:
        """Get current indexes from database."""
        # Returns: {table_name: {index_name: IndexDef}}
        indexes: Dict[str, Dict[str, IndexDef]] = {}

        # Get all tables
        tables = self._get_current_tables()
        for table_name in tables:
            # Get indexes for this table
            index_list = self.driver.fetchall(f"PRAGMA index_list({table_name})")
            table_indexes: Dict[str, IndexDef] = {}

            for idx_row in index_list:
                idx_name = idx_row["name"]
                # Skip auto-generated indexes
                if idx_name.startswith("sqlite_autoindex_"):
                    continue

                # Get index columns
                idx_info = self.driver.fetchall(f"PRAGMA index_info({idx_name})")
                columns = [row["name"] for row in idx_info]

                # Check if unique
                unique = bool(idx_row.get("unique", 0))

                table_indexes[idx_name] = IndexDef(
                    name=idx_name,
                    table=table_name,
                    columns=columns,
                    unique=unique,
                    where_clause=None,  # WHERE clause not available via PRAGMA
                )

            if table_indexes:
                indexes[table_name] = table_indexes

        return indexes

    def _indexes_match(self, current: IndexDef, expected: IndexDef) -> bool:
        """Check if two index definitions match."""
        return (
            current.table == expected.table
            and current.columns == expected.columns
            and current.unique == expected.unique
        )

    def _find_extra_indexes(self) -> List[str]:
        """Find indexes that exist in DB but not in expected schema."""
        expected_indexes = {
            idx["name"] for idx in self.schema_definition.get("indexes", [])
        }
        current_indexes = self._get_current_indexes()

        extra = []
        for table_name, table_indexes in current_indexes.items():
            for idx_name in table_indexes:
                if idx_name not in expected_indexes:
                    extra.append(idx_name)

        return extra

    def _compare_constraints(self) -> Dict[str, List[str]]:
        """
        Compare constraints (PK, FK, unique, check).

        Returns:
            Dictionary mapping table names to lists of constraint change descriptions.
            Empty dict if no constraint changes detected.
        """
        constraint_diffs: Dict[str, List[str]] = {}
        expected_tables = self.schema_definition.get("tables", {})

        for table_name in expected_tables:
            changes = []

            # Compare primary keys
            expected_pk_cols = [
                col["name"]
                for col in expected_tables[table_name]["columns"]
                if col.get("primary_key", False)
            ]
            try:
                current_cols = self._get_table_columns(table_name)
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
                # Table might not exist yet
                pass

            # Compare foreign keys
            expected_fks = expected_tables[table_name].get("foreign_keys", [])
            try:
                current_fks = self._get_current_foreign_keys(table_name)
                if not self._foreign_keys_match(expected_fks, current_fks):
                    changes.append("Foreign key constraints changed")
            except Exception:
                pass

            # Compare unique constraints
            expected_unique = expected_tables[table_name].get("unique_constraints", [])
            try:
                current_unique = self._get_current_unique_constraints(table_name)
                if not self._unique_constraints_match(expected_unique, current_unique):
                    changes.append("Unique constraints changed")
            except Exception:
                pass

            if changes:
                constraint_diffs[table_name] = changes

        return constraint_diffs

    def _get_current_foreign_keys(self, table_name: str) -> List[Dict[str, Any]]:
        """Get current foreign keys for a table using PRAGMA foreign_key_list."""
        try:
            fk_list = self.driver.fetchall(f"PRAGMA foreign_key_list({table_name})")
            fks = []
            for row in fk_list:
                fks.append(
                    {
                        "columns": [row["from"]],
                        "references_table": row["table"],
                        "references_columns": [row["to"]],
                        "on_delete": row.get("on_delete", ""),
                    }
                )
            return fks
        except Exception:
            return []

    def _get_current_unique_constraints(
        self, table_name: str
    ) -> List[Dict[str, List[str]]]:
        """Get current unique constraints for a table."""
        try:
            # Get unique indexes (excluding auto-generated ones)
            index_list = self.driver.fetchall(f"PRAGMA index_list({table_name})")
            unique_constraints = []

            for idx_row in index_list:
                idx_name = idx_row["name"]
                # Skip auto-generated indexes
                if idx_name.startswith("sqlite_autoindex_"):
                    continue

                # Check if unique
                if idx_row.get("unique", 0):
                    # Get index columns
                    idx_info = self.driver.fetchall(f"PRAGMA index_info({idx_name})")
                    columns = [row["name"] for row in idx_info]
                    if columns:
                        unique_constraints.append({"columns": columns})

            return unique_constraints
        except Exception:
            return []

    def _foreign_keys_match(
        self, expected: List[Dict[str, Any]], current: List[Dict[str, Any]]
    ) -> bool:
        """Check if foreign key constraints match."""
        if len(expected) != len(current):
            return False

        # Normalize and compare
        expected_normalized = []
        for fk in expected:
            expected_normalized.append(
                {
                    "columns": tuple(sorted(fk["columns"])),
                    "references_table": fk["references_table"],
                    "references_columns": tuple(sorted(fk["references_columns"])),
                    "on_delete": fk.get("on_delete", ""),
                }
            )

        current_normalized = []
        for fk in current:
            current_normalized.append(
                {
                    "columns": tuple(sorted(fk["columns"])),
                    "references_table": fk["references_table"],
                    "references_columns": tuple(sorted(fk["references_columns"])),
                    "on_delete": fk.get("on_delete", ""),
                }
            )

        return sorted(expected_normalized) == sorted(current_normalized)

    def _unique_constraints_match(
        self, expected: List[Dict[str, List[str]]], current: List[Dict[str, List[str]]]
    ) -> bool:
        """Check if unique constraints match."""
        if len(expected) != len(current):
            return False

        expected_sets = {tuple(sorted(uc["columns"])) for uc in expected}
        current_sets = {tuple(sorted(uc["columns"])) for uc in current}

        return expected_sets == current_sets

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
                    # Check if column has NULLs (would need to query DB)
                    # For now, just warn
                    warnings.append(
                        f"Adding NOT NULL column {table_name}.{col_def.name} - ensure no NULLs exist"
                    )

        return {"compatible": True, "error": None, "warnings": warnings}

    def _recreate_virtual_table(
        self, table_name: str, virtual_table_def: Dict[str, Any]
    ) -> List[str]:
        """
        Generate SQL to recreate virtual table (FTS5) with data preservation.

        For FTS5 tables with external content (content='table_name'), data is stored
        in the content table, not in the FTS5 table itself. SQLite will automatically
        rebuild the index from the content table when the FTS5 table is recreated.

        Args:
            table_name: Name of virtual table
            virtual_table_def: Virtual table definition from schema

        Returns:
            List of SQL statements for recreation with data preservation
        """
        statements = []
        options = virtual_table_def.get("options", {})
        has_external_content = "content" in options

        if has_external_content:
            # For FTS5 with external content, data is in the content table
            # We just need to drop and recreate - SQLite will rebuild index automatically
            statements.append(f"DROP TABLE IF EXISTS {table_name}")

            # Create new virtual table
            columns = ", ".join(virtual_table_def["columns"])
            options_str = ", ".join([f"{k}='{v}'" for k, v in options.items()])
            if options_str:
                create_sql = f"CREATE VIRTUAL TABLE {table_name} USING {virtual_table_def['type']}({columns}, {options_str})"
            else:
                create_sql = f"CREATE VIRTUAL TABLE {table_name} USING {virtual_table_def['type']}({columns})"
            statements.append(create_sql)
            # Note: SQLite will automatically rebuild the FTS5 index from the content table
        else:
            # For FTS5 without external content, data is stored in the FTS5 table itself
            # We need to backup and restore data
            temp_table = f"temp_{table_name}"

            # Backup data
            statements.append(
                f"CREATE TEMP TABLE {temp_table} AS SELECT * FROM {table_name}"
            )

            # Drop virtual table
            statements.append(f"DROP TABLE IF EXISTS {table_name}")

            # Create new virtual table
            columns = ", ".join(virtual_table_def["columns"])
            options_str = ", ".join([f"{k}='{v}'" for k, v in options.items()])
            if options_str:
                create_sql = f"CREATE VIRTUAL TABLE {table_name} USING {virtual_table_def['type']}({columns}, {options_str})"
            else:
                create_sql = f"CREATE VIRTUAL TABLE {table_name} USING {virtual_table_def['type']}({columns})"
            statements.append(create_sql)

            # Restore data
            statements.append(f"INSERT INTO {table_name} SELECT * FROM {temp_table}")

            # Drop temp table
            statements.append(f"DROP TABLE {temp_table}")

        return statements

    def _generate_create_table_sql(self, table_name: str) -> str:
        """Generate CREATE TABLE SQL for a table."""
        table_def = self.schema_definition["tables"][table_name]
        columns = table_def["columns"]

        col_defs = []
        for col in columns:
            col_sql = f"{col['name']} {col['type']}"
            if col.get("primary_key"):
                col_sql += " PRIMARY KEY"
            if col.get("autoincrement"):
                col_sql += " AUTOINCREMENT"
            if col.get("not_null") and not col.get("primary_key"):
                col_sql += " NOT NULL"
            if col.get("default"):
                default_val = col["default"]
                # For function-based defaults (like julianday('now')), wrap in parentheses
                # SQLite requires DEFAULT (function()) syntax for functions
                # Check if it's a function call (contains parentheses or function name)
                if "julianday" in default_val or "(" in default_val:
                    # If it already has parentheses, use as is
                    if default_val.strip().startswith(
                        "("
                    ) and default_val.strip().endswith(")"):
                        # Already wrapped in parentheses
                        pass
                    elif not default_val.strip().startswith("("):
                        # Function call without parentheses - add them
                        default_val = f"({default_val})"
                col_sql += f" DEFAULT {default_val}"
            col_defs.append(col_sql)

        # Add foreign keys
        for fk in table_def.get("foreign_keys", []):
            fk_cols = ", ".join(fk["columns"])
            ref_cols = ", ".join(fk["references_columns"])
            on_delete = fk.get("on_delete", "")
            fk_sql = f"FOREIGN KEY ({fk_cols}) REFERENCES {fk['references_table']}({ref_cols})"
            if on_delete:
                fk_sql += f" ON DELETE {on_delete}"
            col_defs.append(fk_sql)

        # Add unique constraints
        for uc in table_def.get("unique_constraints", []):
            uc_cols = ", ".join(uc["columns"])
            col_defs.append(f"UNIQUE ({uc_cols})")

        return f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(col_defs)})"

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
        new_table_sql = self._generate_create_table_sql(table_name)
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
        """Generate CREATE INDEX SQL."""
        unique_str = "UNIQUE " if index_def.unique else ""
        columns_str = ", ".join(index_def.columns)
        where_clause = (
            f" WHERE {index_def.where_clause}" if index_def.where_clause else ""
        )
        return f"CREATE {unique_str}INDEX IF NOT EXISTS {index_def.name} ON {index_def.table} ({columns_str}){where_clause}"

    def _tables_recreate_order(self, table_names: Set[str]) -> List[str]:
        """
        Return table names in FK-safe order for recreation (parents before children).
        Tables that are not in schema_definition are appended at the end.
        """
        tables = self.schema_definition.get("tables", {})
        deps: Dict[str, Set[str]] = {}
        for t in table_names:
            refs = set()
            for fk in tables.get(t, {}).get("foreign_keys", []):
                r = fk.get("references_table")
                if r and r in table_names:
                    refs.add(r)
            deps[t] = refs
        result: List[str] = []
        remaining = set(table_names)
        while remaining:
            chosen = None
            for t in remaining:
                if deps[t] <= set(result):
                    chosen = t
                    break
            if chosen is None:
                result.extend(remaining)
                break
            result.append(chosen)
            remaining.discard(chosen)
        return result

    def generate_migration_sql(self, diff: SchemaDiff) -> List[str]:
        """
        Generate SQL statements to apply schema changes.

        Handles:
        - CREATE TABLE for missing tables
        - ALTER TABLE ADD COLUMN for missing columns
        - Table recreation for type changes (with data migration)
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
        ordered_recreate = (
            self._tables_recreate_order(tables_with_type_changes)
            if tables_with_type_changes
            else []
        )
        for table_name in ordered_recreate:
            table_diff = diff.table_diffs[table_name]
            try:
                current_columns = set(self._get_table_columns(table_name).keys())
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
