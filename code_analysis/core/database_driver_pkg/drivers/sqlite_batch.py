"""
Batch query parsing and grouping for SQLite driver.

Recognizes multiple statements in one SQL text and groups consecutive
same-statement operations for native executemany. Preserves order of
queries and results.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List, Optional, Tuple

# Type: one (sql, params) or a group (sql, [params1, params2, ...]) for executemany
_SingleRun = Tuple[str, Optional[tuple]]
_ManyRun = Tuple[str, List[tuple]]
_BatchRun = Tuple[
    str, _SingleRun | _ManyRun
]  # "single" | "many", (sql, params) or (sql, [params])


def split_batch_sql(sql: str) -> List[str]:
    """Split SQL text into individual statements by semicolon.

    Semicolons inside string literals are not supported; do not use
    semicolons inside single-quoted strings in batch SQL.

    Args:
        sql: SQL text, possibly containing multiple statements.

    Returns:
        List of non-empty stripped statements.
    """
    if not sql or not sql.strip():
        return []
    parts = sql.split(";")
    return [p.strip() for p in parts if p.strip()]


def expand_operations(
    operations: List[Tuple[str, Optional[tuple]]],
) -> List[Tuple[str, Optional[tuple]]]:
    """Expand each operation: one (sql, params) may become several (stmt, params).

    If sql contains ';', it is split into statements. Params apply only
    to the first statement; subsequent statements get params=None.

    Args:
        operations: List of (sql, params) as from execute_batch input.

    Returns:
        Flat list of (stmt, params) preserving logical order.
    """
    expanded: List[Tuple[str, Optional[tuple]]] = []
    for sql, params in operations:
        statements = split_batch_sql(sql)
        if not statements:
            continue
        for i, stmt in enumerate(statements):
            expanded.append((stmt, params if i == 0 else None))
    return expanded


def group_for_executemany(
    expanded: List[Tuple[str, Optional[tuple]]],
) -> List[_BatchRun]:
    """Group consecutive (sql, params) with identical sql for executemany.

    Preserves order: each run is either a single execute or one
    executemany. Results must be assembled one per expanded item.

    Args:
        expanded: Flat list of (sql, params).

    Returns:
        List of ("single", (sql, params)) or ("many", (sql, [params, ...])).
    """
    if not expanded:
        return []
    runs: List[_BatchRun] = []
    i = 0
    while i < len(expanded):
        sql, params = expanded[i]
        # Collect consecutive same-sql with non-None params for executemany
        group_params: List[tuple] = []
        j = i
        while j < len(expanded):
            s, p = expanded[j]
            if s != sql:
                break
            if p is not None:
                group_params.append(p)
            else:
                # Params None: cannot merge into executemany; emit current group and this one
                if group_params:
                    runs.append(("many", (sql, group_params)))
                    group_params = []
                runs.append(("single", (sql, None)))
                j += 1
                break
            j += 1
        if group_params:
            if len(group_params) == 1:
                runs.append(("single", (sql, group_params[0])))
            else:
                runs.append(("many", (sql, group_params)))
        i = j
    return runs


def run_batch_result_counts(runs: List[_BatchRun]) -> List[int]:
    """Return number of result items each run produces (for ordering).

    Args:
        runs: Output of group_for_executemany.

    Returns:
        List of counts: 1 for single, N for many.
    """
    counts: List[int] = []
    for kind, payload in runs:
        if kind == "single":
            counts.append(1)
        else:
            counts.append(len(payload[1]))
    return counts
