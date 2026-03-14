"""
Virtual table (FTS5) recreation SQL for schema sync.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List


def generate_recreate_virtual_table_sql(
    table_name: str, virtual_table_def: Dict[str, Any]
) -> List[str]:
    """
    Generate SQL to recreate virtual table (FTS5) with data preservation.

    For FTS5 tables with external content (content='table_name'), data is stored
    in the content table. SQLite will automatically rebuild the index when the
    FTS5 table is recreated.

    Args:
        table_name: Name of virtual table.
        virtual_table_def: Virtual table definition from schema.

    Returns:
        List of SQL statements for recreation with data preservation.
    """
    statements: List[str] = []
    options = virtual_table_def.get("options", {})
    has_external_content = "content" in options

    if has_external_content:
        statements.append(f"DROP TABLE IF EXISTS {table_name}")
        columns = ", ".join(virtual_table_def["columns"])
        options_str = ", ".join([f"{k}='{v}'" for k, v in options.items()])
        if options_str:
            create_sql = (
                f"CREATE VIRTUAL TABLE {table_name} USING "
                f"{virtual_table_def['type']}({columns}, {options_str})"
            )
        else:
            create_sql = (
                f"CREATE VIRTUAL TABLE {table_name} USING "
                f"{virtual_table_def['type']}({columns})"
            )
        statements.append(create_sql)
    else:
        temp_table = f"temp_{table_name}"
        statements.append(
            f"CREATE TEMP TABLE {temp_table} AS SELECT * FROM {table_name}"
        )
        statements.append(f"DROP TABLE IF EXISTS {table_name}")
        columns = ", ".join(virtual_table_def["columns"])
        options_str = ", ".join([f"{k}='{v}'" for k, v in options.items()])
        if options_str:
            create_sql = (
                f"CREATE VIRTUAL TABLE {table_name} USING "
                f"{virtual_table_def['type']}({columns}, {options_str})"
            )
        else:
            create_sql = (
                f"CREATE VIRTUAL TABLE {table_name} USING "
                f"{virtual_table_def['type']}({columns})"
            )
        statements.append(create_sql)
        statements.append(f"INSERT INTO {table_name} SELECT * FROM {temp_table}")
        statements.append(f"DROP TABLE {temp_table}")

    return statements
