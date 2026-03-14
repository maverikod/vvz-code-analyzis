"""
SQL generation helpers for schema sync.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

from .schema_sync_models import IndexDef


def generate_create_table_sql(
    schema_definition: Dict[str, Any],
    table_name: str,
    *,
    relax_cst_node_id_not_null: bool = False,
) -> str:
    """Generate CREATE TABLE SQL for a table from schema definition."""
    table_def = schema_definition["tables"][table_name]
    columns = table_def["columns"]

    col_defs = []
    for col in columns:
        col_sql = f"{col['name']} {col['type']}"
        if col.get("primary_key"):
            col_sql += " PRIMARY KEY"
        if col.get("autoincrement"):
            col_sql += " AUTOINCREMENT"
        is_relaxed_cst_col = (
            relax_cst_node_id_not_null and col.get("name") == "cst_node_id"
        )
        if (
            col.get("not_null")
            and not col.get("primary_key")
            and not is_relaxed_cst_col
        ):
            col_sql += " NOT NULL"
        if col.get("default"):
            default_val = col["default"]
            if "julianday" in default_val or "(" in default_val:
                if not default_val.strip().startswith("("):
                    default_val = f"({default_val})"
            col_sql += f" DEFAULT {default_val}"
        col_defs.append(col_sql)

    for fk in table_def.get("foreign_keys", []):
        fk_cols = ", ".join(fk["columns"])
        ref_cols = ", ".join(fk["references_columns"])
        on_delete = fk.get("on_delete", "")
        fk_sql = (
            f"FOREIGN KEY ({fk_cols}) REFERENCES {fk['references_table']}({ref_cols})"
        )
        if on_delete:
            fk_sql += f" ON DELETE {on_delete}"
        col_defs.append(fk_sql)

    for uc in table_def.get("unique_constraints", []):
        uc_cols = ", ".join(uc["columns"])
        col_defs.append(f"UNIQUE ({uc_cols})")

    return f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(col_defs)})"


def generate_create_index_sql(index_def: IndexDef) -> str:
    """Generate CREATE INDEX SQL from index definition."""
    unique_str = "UNIQUE " if index_def.unique else ""
    columns_str = ", ".join(index_def.columns)
    where_clause = f" WHERE {index_def.where_clause}" if index_def.where_clause else ""
    return f"CREATE {unique_str}INDEX IF NOT EXISTS {index_def.name} ON {index_def.table} ({columns_str}){where_clause}"


def tables_recreate_order(
    schema_definition: Dict[str, Any], table_names: Set[str]
) -> List[str]:
    """
    Return table names in FK-safe order for recreation (parents before children).
    Tables that are not in schema_definition are appended at the end.
    """
    tables = schema_definition.get("tables", {})
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
