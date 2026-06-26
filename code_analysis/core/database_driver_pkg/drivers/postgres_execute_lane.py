"""
Classify PostgreSQL driver execute / execute_batch SQL for read vs write pool lanes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from code_analysis.core.database_driver_pkg.drivers.sqlite_batch import (
    expand_operations,
    split_batch_sql,
)

# Statements that must use the write pool (conservative; DDL/session mutations included).
_WRITE_STMT_HINT = re.compile(
    r"\b("
    r"INSERT|UPDATE|DELETE|MERGE|TRUNCATE|ALTER|CREATE|DROP|GRANT|REVOKE|CALL|COPY|"
    r"BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE|VACUUM|ANALYZE|REINDEX|"
    r"LISTEN|NOTIFY|CLUSTER|DISCARD|COMMENT\s+ON|"
    r"LOCK\s+TABLE|REFRESH\s+MATERIALIZED|"
    r"SET\s+(ROLE|SESSION\s+AUTHORIZATION|TRANSACTION)"
    r")\b",
    re.IGNORECASE | re.DOTALL,
)


def _strip_sql_comments(sql: str) -> str:
    """Best-effort strip of -- and /* */ comments for classification."""
    out: List[str] = []
    i = 0
    n = len(sql)
    while i < n:
        if i + 1 < n and sql[i : i + 2] == "--":
            while i < n and sql[i] != "\n":
                i += 1
            continue
        if i + 1 < n and sql[i : i + 2] == "/*":
            end = sql.find("*/", i + 2)
            if end == -1:
                break
            i = end + 2
            continue
        out.append(sql[i])
        i += 1
    return "".join(out)


def _statement_needs_write_lane(statement: str) -> bool:
    """Return statement needs write lane."""
    s = _strip_sql_comments(statement).strip()
    if not s:
        return False
    return bool(_WRITE_STMT_HINT.search(s))


def postgres_execute_requires_write_pool(sql: str) -> bool:
    """True if any statement in batched SQL must run on a write pool connection."""
    for stmt in split_batch_sql(sql):
        if _statement_needs_write_lane(stmt):
            return True
    return False


def postgres_batch_requires_write_pool(
    operations: List[Tuple[str, Optional[tuple]]],
) -> bool:
    """True if any expanded batch operation must run on a write pool connection."""
    for stmt, _ in expand_operations(operations):
        if _statement_needs_write_lane(stmt):
            return True
    return False
