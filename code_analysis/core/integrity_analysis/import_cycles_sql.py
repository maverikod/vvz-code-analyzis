"""
Three-step SQL batch for circular import detection via chained self-joins.

Step 1: temp edge table + indexes (file_from -> file_to, no self-loops).
Step 2: temp tree table (LEFT JOIN chain up to max_depth).
Step 3: SELECT paths with a duplicate node or closure back to f0.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, List, Sequence, Tuple

from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE, WHERE_FILES_ACTIVE_F

# Temp object names (session-scoped).
TBL_FILE_MODULES = "integrity_file_modules"
TBL_IMPORT_EDGES = "integrity_import_edges"
TBL_IMPORT_TREE = "integrity_import_tree"

IDX_FM_MOD = "idx_integrity_fm_mod"
IDX_FM_FILE = "idx_integrity_fm_file"
IDX_IE_FROM = "idx_integrity_ie_from"
IDX_IE_TO = "idx_integrity_ie_to"

DEFAULT_MAX_CHAIN_DEPTH = 10

SqlPair = Tuple[str, tuple[Any, ...]]


# LIKE patterns are bound as parameters, never inlined: a literal ``%`` in the
# SQL text makes psycopg (PostgreSQL backend) treat ``%/`` / ``%.`` as an invalid
# parameter placeholder and raise "only '%s','%b','%t' are allowed as
# placeholders". As a bound value the ``%`` is data, not a placeholder, and the
# same statement stays valid on SQLite.
LIKE_INIT_PY = "%/__init__.py"
LIKE_DOT_PY = "%.py"


def _path_to_mod_key_sql(path_expr: str) -> str:
    """SQL expression: project-relative ``.py`` path -> dotted module key.

    Contains one ``LIKE ?`` placeholder; the caller must supply ``LIKE_INIT_PY``
    as the corresponding positional parameter (first, since this expression sits
    in the SELECT list ahead of the WHERE clause).
    """
    return f"""
REPLACE(
  REPLACE(
    CASE
      WHEN {path_expr} LIKE ? THEN
        SUBSTR({path_expr}, 1, LENGTH({path_expr}) - 12)
      ELSE
        SUBSTR({path_expr}, 1, LENGTH({path_expr}) - 3)
    END,
  '/', '.'),
'-', '_')
""".strip()


def _import_target_mod_key_sql() -> str:
    """SQL expression for target module key from ``imports`` row."""
    return """
CASE
  WHEN i.import_type IN ('import_from', 'from')
       AND NULLIF(TRIM(COALESCE(i.module, '')), '') IS NOT NULL THEN
    CASE
      WHEN NULLIF(TRIM(COALESCE(i.name, '')), '') IS NOT NULL
      THEN TRIM(i.module) || '.' || TRIM(i.name)
      ELSE TRIM(i.module)
    END
  WHEN NULLIF(TRIM(COALESCE(i.module, '')), '') IS NOT NULL THEN TRIM(i.module)
  WHEN NULLIF(TRIM(COALESCE(i.name, '')), '') IS NOT NULL THEN TRIM(i.name)
  ELSE NULL
END
""".strip()


def build_step1_create_edges_sql(project_id: str) -> List[SqlPair]:
    """Query 1: temp tables, indexes, populate directed import edges."""
    path_expr = "COALESCE(NULLIF(TRIM(f.relative_path), ''), TRIM(f.path))"
    mod_key = _path_to_mod_key_sql(path_expr)
    target_key = _import_target_mod_key_sql()
    ops: List[SqlPair] = [
        (f"DROP TABLE IF EXISTS {TBL_IMPORT_TREE}", ()),
        (f"DROP TABLE IF EXISTS {TBL_IMPORT_EDGES}", ()),
        (f"DROP TABLE IF EXISTS {TBL_FILE_MODULES}", ()),
        (
            f"""
CREATE TEMP TABLE {TBL_FILE_MODULES} (
  file_id TEXT NOT NULL,
  mod_key TEXT NOT NULL
)
""".strip(),
            (),
        ),
        (
            f"CREATE INDEX {IDX_FM_MOD} ON {TBL_FILE_MODULES} (mod_key)",
            (),
        ),
        (
            f"CREATE UNIQUE INDEX {IDX_FM_FILE} ON {TBL_FILE_MODULES} (file_id)",
            (),
        ),
        (
            f"""
INSERT INTO {TBL_FILE_MODULES} (file_id, mod_key)
SELECT CAST(f.id AS TEXT), {mod_key}
FROM files f
WHERE f.project_id = ?
  AND {WHERE_FILES_ACTIVE_F}
  AND ({path_expr}) LIKE ?
""".strip(),
            # Param order = appearance order: mod_key's LIKE (SELECT) first,
            # then project_id (WHERE), then the trailing ``.py`` LIKE.
            (LIKE_INIT_PY, project_id, LIKE_DOT_PY),
        ),
        (
            f"""
CREATE TEMP TABLE {TBL_IMPORT_EDGES} (
  file_from TEXT NOT NULL,
  file_to TEXT NOT NULL
)
""".strip(),
            (),
        ),
        (
            f"CREATE INDEX {IDX_IE_FROM} ON {TBL_IMPORT_EDGES} (file_from)",
            (),
        ),
        (
            f"CREATE INDEX {IDX_IE_TO} ON {TBL_IMPORT_EDGES} (file_to)",
            (),
        ),
        (
            f"""
INSERT INTO {TBL_IMPORT_EDGES} (file_from, file_to)
SELECT DISTINCT CAST(i.file_id AS TEXT), fm.file_id
FROM imports i
INNER JOIN files f ON f.id = i.file_id
INNER JOIN {TBL_FILE_MODULES} fm ON fm.mod_key = ({target_key})
WHERE f.project_id = ?
  AND {WHERE_FILES_ACTIVE_F}
  -- fm.file_id is TEXT (temp table); imports.file_id is UUID. CAST so the
  -- self-loop filter is text<>text — PostgreSQL has no uuid<>text operator
  -- (SQLite's dynamic typing tolerated the mismatch).
  AND CAST(i.file_id AS TEXT) <> fm.file_id
""".strip(),
            (project_id,),
        ),
    ]
    return ops


def _join_chain_aliases(max_depth: int) -> List[str]:
    """Return alias list e0..e(max_depth-1) for edge table self-joins."""
    return [f"e{i}" for i in range(max_depth)]


def build_step2_create_tree_sql(max_depth: int = DEFAULT_MAX_CHAIN_DEPTH) -> SqlPair:
    """
    Query 2: build path tree with LEFT JOIN chain (hop count up to max_depth).

    Columns: f0 .. f{max_depth} (f0=start file, f1..=successive import targets).
    """
    if max_depth < 2:
        raise ValueError("max_depth must be >= 2")
    aliases = _join_chain_aliases(max_depth)
    select_cols = ["e0.file_from AS f0", "e0.file_to AS f1"]
    for i in range(1, max_depth):
        select_cols.append(f"{aliases[i]}.file_to AS f{i + 1}")
    join_lines: List[str] = []
    for i in range(1, max_depth):
        prev, cur = aliases[i - 1], aliases[i]
        join_lines.append(
            f"LEFT JOIN {TBL_IMPORT_EDGES} {cur} "
            f"ON {prev}.file_to = {cur}.file_from "
            f"AND {cur}.file_from <> {cur}.file_to"
        )
    sql = f"""
CREATE TEMP TABLE {TBL_IMPORT_TREE} AS
SELECT
  {", ".join(select_cols)}
FROM {TBL_IMPORT_EDGES} e0
{" ".join(join_lines)}
WHERE e1.file_from IS NOT NULL
""".strip()
    return sql, ()


def _duplicate_or_cycle_predicate(max_depth: int) -> str:
    """
    Query 3 filter: reject trivial f0=f1; detect closure to f0 or internal duplicate.

    For hop k (f{k} column, k>=2): f{k} equals f0 or any of f1..f{k-1}.
    """
    parts: List[str] = ["f0 <> f1"]
    for k in range(2, max_depth + 1):
        fk = f"f{k}"
        prior = ["f0"] + [f"f{i}" for i in range(1, k)]
        cond = " OR ".join(f"{fk} = {p}" for p in prior)
        parts.append(f"({fk} IS NOT NULL AND ({cond}))")
    return " AND ".join([parts[0]] + [f"({' OR '.join(parts[1:])})"])


def build_step3_select_cycles_sql(max_depth: int = DEFAULT_MAX_CHAIN_DEPTH) -> SqlPair:
    """Query 3: select import paths that close or repeat a node (real cycles / duplicates)."""
    cols = ", ".join(f"f{i}" for i in range(max_depth + 1))
    where = _duplicate_or_cycle_predicate(max_depth)
    sql = f"""
SELECT {cols}
FROM {TBL_IMPORT_TREE}
WHERE {where}
""".strip()
    return sql, ()


def build_import_cycle_detection_batch(
    project_id: str,
    *,
    max_depth: int = DEFAULT_MAX_CHAIN_DEPTH,
) -> List[SqlPair]:
    """Full three-query batch: edges + tree + selection."""
    batch = build_step1_create_edges_sql(project_id)
    batch.append(build_step2_create_tree_sql(max_depth))
    batch.append(build_step3_select_cycles_sql(max_depth))
    return batch


def execute_sql_batch(database: Any, ops: Sequence[SqlPair]) -> None:
    """Run SQL statements sequentially on ``database``."""
    for sql, params in ops:
        database.execute(sql, params)


def fetch_import_cycles(
    database: Any,
    project_id: str,
    *,
    max_depth: int = DEFAULT_MAX_CHAIN_DEPTH,
) -> List[List[str]]:
    """
    Run the three-step batch and return each matching path as a list of file_id strings.

    Prefer :meth:`DatabaseClient.fetch_import_cycle_paths` when ``database`` is a
    client; this helper delegates to it or falls back to a transactional batch.
    """
    if hasattr(database, "fetch_import_cycle_paths"):
        return database.fetch_import_cycle_paths(project_id, max_depth=max_depth)

    batch = build_import_cycle_detection_batch(project_id, max_depth=max_depth)
    operations = [(sql, params) for sql, params in batch]
    if hasattr(database, "begin_transaction") and hasattr(database, "execute_batch"):
        tid = database.begin_transaction()
        try:
            results = database.execute_batch(operations, transaction_id=tid)
            database.commit_transaction(tid)
        except Exception:
            database.rollback_transaction(tid)
            raise
        if not results:
            return []
        last = results[-1]
        rows = last.get("data") if isinstance(last, dict) else None
        return parse_import_cycle_rows(rows or [], max_depth=max_depth)

    execute_sql_batch(database, operations[:-1])
    select_sql, select_params = operations[-1]
    result = database.execute(select_sql, select_params)
    rows = result.get("data") or []
    return parse_import_cycle_rows(rows, max_depth=max_depth)


def parse_import_cycle_rows(
    rows: Sequence[Any],
    *,
    max_depth: int = DEFAULT_MAX_CHAIN_DEPTH,
) -> List[List[str]]:
    """Convert SELECT rows from the cycle tree query into deduped file-id paths."""
    paths: List[List[str]] = []
    col_names = [f"f{i}" for i in range(max_depth + 1)]
    for row in rows:
        if isinstance(row, dict):
            nodes = [str(row[c]) for c in col_names if row.get(c) is not None]
        else:
            nodes = [str(v) for v in row if v is not None]
        trimmed = _trim_path_at_first_duplicate(nodes)
        if len(trimmed) >= 3 and trimmed[0] != trimmed[1]:
            paths.append(trimmed)
    return _dedupe_cycle_paths(paths)


def _trim_path_at_first_duplicate(nodes: List[str]) -> List[str]:
    """Cut path after first repeated node (inclusive)."""
    seen: set[str] = set()
    out: List[str] = []
    for n in nodes:
        if n in seen:
            out.append(n)
            break
        seen.add(n)
        out.append(n)
    return out


def _dedupe_cycle_paths(paths: List[List[str]]) -> List[List[str]]:
    """Drop paths that are rotations of an already kept cycle witness."""
    normalized: set[tuple[str, ...]] = set()
    unique: List[List[str]] = []
    for path in paths:
        if len(path) < 3:
            continue
        core = path[:-1] if path[-1] == path[0] else path
        if len(core) < 2:
            continue
        rots = {tuple(core[i:] + core[:i]) for i in range(len(core))}
        if rots & normalized:
            continue
        normalized |= rots
        unique.append(path)
    return unique
