"""
Create/drop table helpers for SQLite driver.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from ..exceptions import DriverOperationError


def run_create_table(conn: Any, schema: Dict[str, Any]) -> bool:
    """Create database table from schema dict. Returns True on success."""
    table_name = schema.get("name")
    if not table_name:
        raise DriverOperationError("Table name is required in schema")

    columns = schema.get("columns", [])
    if not columns:
        raise DriverOperationError("At least one column is required")

    column_defs = []
    for col in columns:
        col_name = col.get("name")
        col_type = col.get("type", "TEXT")
        nullable = col.get("nullable", True)
        default = col.get("default")
        primary_key = col.get("primary_key", False)

        col_def = f"{col_name} {col_type}"
        if not nullable:
            col_def += " NOT NULL"
        if default is not None:
            if isinstance(default, str) and "(" not in default:
                col_def += f" DEFAULT '{default}'"
            else:
                col_def += (
                    f" DEFAULT ({default})"
                    if isinstance(default, str)
                    else f" DEFAULT {default}"
                )
        if primary_key:
            col_def += " PRIMARY KEY"
        column_defs.append(col_def)

    constraints = schema.get("constraints", [])
    for constraint in constraints:
        if constraint.get("type") == "primary_key":
            cols = constraint.get("columns", [])
            if cols:
                column_defs.append(f"PRIMARY KEY ({', '.join(cols)})")
        elif constraint.get("type") == "foreign_key":
            cols = constraint.get("columns", [])
            ref_table = constraint.get("references_table")
            ref_cols = constraint.get("references_columns", [])
            if cols and ref_table and ref_cols:
                column_defs.append(
                    f"FOREIGN KEY ({', '.join(cols)}) "
                    f"REFERENCES {ref_table} ({', '.join(ref_cols)})"
                )

    sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(column_defs)})"
    conn.execute(sql)
    conn.commit()
    return True


def run_drop_table(conn: Any, table_name: str) -> bool:
    """Drop database table. Returns True on success."""
    sql = f"DROP TABLE IF EXISTS {table_name}"
    conn.execute(sql)
    conn.commit()
    return True
