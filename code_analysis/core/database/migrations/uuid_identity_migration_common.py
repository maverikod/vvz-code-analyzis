"""
Shared UUID migration logic: mandatory mapping-table list, polymorphic helpers, Phase 1–2.

``file_tree_snapshot_roots``: Option A — no dedicated mapping table; roots are rewritten via
``uuid_migration_file_tree_snapshots`` snapshot_id remap in Phase 4 (not implemented here).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

BackendKind = Literal["postgresql"]

# (source_pk_table, uuid_migration_* table name) — exhaustive per step 09.
MANDATORY_SOURCE_TO_MIGRATION: Tuple[Tuple[str, str], ...] = (
    ("files", "uuid_migration_files"),
    ("classes", "uuid_migration_classes"),
    ("methods", "uuid_migration_methods"),
    ("functions", "uuid_migration_functions"),
    ("entity_cross_ref", "uuid_migration_entity_cross_ref"),
    ("imports", "uuid_migration_imports"),
    ("issues", "uuid_migration_issues"),
    ("usages", "uuid_migration_usages"),
    ("code_content", "uuid_migration_code_content"),
    ("ast_trees", "uuid_migration_ast_trees"),
    ("cst_trees", "uuid_migration_cst_trees"),
    ("vector_index", "uuid_migration_vector_index"),
    ("code_chunks", "uuid_migration_code_chunks"),
    ("code_duplicates", "uuid_migration_code_duplicates"),
    ("duplicate_occurrences", "uuid_migration_duplicate_occurrences"),
    ("comprehensive_analysis_results", "uuid_migration_comprehensive_analysis_results"),
    ("file_tree_snapshots", "uuid_migration_file_tree_snapshots"),
    ("file_tree_snapshot_nodes", "uuid_migration_file_tree_snapshot_nodes"),
    ("indexing_errors", "uuid_migration_indexing_errors"),
)

# Polymorphic entity_type (code_content / vector_index) -> source table for old INTEGER id.
# ``vector_id`` on vector_index / code_chunks is NOT an entity id; never mapped here.
ENTITY_TYPE_TO_SOURCE_TABLE: Dict[str, str] = {
    "file": "files",
    "class": "classes",
    "function": "functions",
    "method": "methods",
    "chunk": "code_chunks",
    "module": "files",  # treated as file-level where used
}


class UuidMigrationError(RuntimeError):
    """Base error for UUID identity migration."""


class UuidMigrationPreflightError(UuidMigrationError):
    """Preflight phase refused to proceed."""


def _valid_ident(name: str) -> str:
    """Return valid ident."""
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        raise ValueError(f"invalid SQL identifier: {name!r}")
    return name


def mapping_table_for_source(source_table: str) -> str:
    """Return mapping table for source."""
    for src, mig in MANDATORY_SOURCE_TO_MIGRATION:
        if src == source_table:
            return mig
    raise KeyError(f"no migration mapping table for {source_table!r}")


def map_polymorphic_entity_id_to_new_uuid(
    entity_type: str,
    old_entity_id: int,
    lookup_new_uuid: Callable[[str, int], Union[str, uuid.UUID, None]],
) -> Union[str, uuid.UUID, None]:
    """
    Documented Phase-4 rule preview: resolve ``entity_id`` for ``code_content`` / ``vector_index``.

    ``lookup_new_uuid(source_table, old_int_id)`` must return the canonical new UUID/TEXT/shape for
    that row from the migration mapping tables (typically by joining source id to uuid_migration_*).

    Returns:
        New UUID representation, or ``None`` if ``entity_type`` unknown or resolver returned None.

    ``vector_index.vector_id`` and ``code_chunks.vector_id`` are never passed here — they remain
    integers through mapping (Phase 2 does not remap FAISS ids).
    """
    et = (entity_type or "").strip().lower()
    src = ENTITY_TYPE_TO_SOURCE_TABLE.get(et)
    if src is None:
        return None
    return lookup_new_uuid(src, old_entity_id)


def _migration_fetchone(db: Any, sql: str, params: Optional[tuple] = None) -> Any:
    """
    One row for migration SQL — works with :class:`CodeDatabase` (``_fetchone``) and
    :class:`DatabaseClient` (RPC ``execute`` → ``{"data": [row_dict, ...]}``).
    """
    fetch = getattr(db, "_fetchone", None)
    if callable(fetch):
        return fetch(sql, params)
    execute_fn = getattr(db, "execute", None)
    if callable(execute_fn):
        raw = execute_fn(sql, params)
        if not isinstance(raw, dict):
            return None
        rows = raw.get("data")
        if isinstance(rows, list) and rows:
            return rows[0]
        return None
    return None


def _migration_fetchall(db: Any, sql: str, params: Optional[tuple] = None) -> List[Any]:
    """All rows — ``_fetchall`` on CodeDatabase, else ``execute`` ``data`` list."""
    fetch = getattr(db, "_fetchall", None)
    if callable(fetch):
        return list(fetch(sql, params))
    execute_fn = getattr(db, "execute", None)
    if callable(execute_fn):
        raw = execute_fn(sql, params)
        if isinstance(raw, dict):
            data = raw.get("data")
            if isinstance(data, list):
                return list(data)
    return []


def _migration_execute(db: Any, sql: str, params: Optional[tuple] = None) -> None:
    """Run DDL/DML — ``_execute`` on :class:`CodeDatabase`, else ``execute`` (RPC client)."""
    fn = getattr(db, "_execute", None)
    if callable(fn):
        fn(sql, params)
        return
    execute_fn = getattr(db, "execute", None)
    if callable(execute_fn):
        execute_fn(sql, params)
        return
    raise UuidMigrationError(
        "database handle has no _execute/execute; cannot run migration SQL"
    )


def _migration_commit(db: Any) -> None:
    """Persist batch — ``_commit`` on CodeDatabase; no-op if absent (e.g. auto-commit RPC)."""
    fn = getattr(db, "_commit", None)
    if callable(fn):
        fn()


def detect_backend_kind(db: Any) -> BackendKind:
    """
    Detect PostgreSQL backend from CodeDatabase ``_driver_type`` or probe query.

    SQLite support was removed; any non-PostgreSQL result is a fatal
    configuration error, not a valid migration target.

    Enforced: ``_driver_type`` from :class:`CodeDatabase` when present; else
    ``version()`` probe.
    """
    dt = str(getattr(db, "_driver_type", "") or "").lower()
    if dt in ("postgres", "postgresql"):
        return "postgresql"

    driver = getattr(db, "driver", None)
    cls = type(driver).__name__.lower() if driver is not None else ""
    mod = type(driver).__module__.lower() if driver is not None else ""
    if "postgres" in cls or "postgres" in mod:
        return "postgresql"

    try:
        row2 = _migration_fetchone(db, "SELECT version() AS v")
        if row2:
            v = next(iter(row2.values())) if isinstance(row2, dict) else row2[0]
            if "postgresql" in str(v).lower():
                return "postgresql"
    except Exception:
        pass

    raise UuidMigrationError(
        "Could not detect PostgreSQL database backend; SQLite support was removed. "
        "Set CodeDatabase driver 'type' to 'postgres' or extend detect_backend_kind."
    )


def _scalar_int(db: Any, sql: str, params: Optional[tuple] = None) -> int:
    """Return scalar int."""
    r = _migration_fetchone(db, sql, params)
    if r is None:
        return 0
    if isinstance(r, dict):
        return int(next(iter(r.values())))
    if isinstance(r, (list, tuple)) and r:
        return int(r[0])
    return int(r)


def _rows_first_col(db: Any, sql: str, params: Optional[tuple] = None) -> List[int]:
    """Return rows first col."""
    rows = _migration_fetchall(db, sql, params)
    out: List[int] = []
    for r in rows:
        if isinstance(r, dict):
            out.append(int(next(iter(r.values()))))
        else:
            out.append(int(r[0]))
    return out


def _rows_pk_values(db: Any, sql: str, params: Optional[tuple] = None) -> List[Any]:
    """Return rows pk values."""
    rows = _migration_fetchall(db, sql, params)
    out: List[Any] = []
    for r in rows:
        if isinstance(r, dict):
            out.append(next(iter(r.values())))
        else:
            out.append(r[0])
    return out


def _validate_uuid_text(s: str) -> uuid.UUID:
    """Return validate uuid text."""
    try:
        return uuid.UUID(str(s).strip())
    except (ValueError, AttributeError) as e:
        raise UuidMigrationPreflightError(
            f"Expected canonical UUID string, got {s!r}"
        ) from e


@dataclass
class PreflightReport:
    """Represent PreflightReport."""

    backend: BackendKind
    projects_uuid_ok: bool = True
    watch_dirs_uuid_ok: bool = True
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def run_uuid_migration_preflight_phase1(
    db: Any,
    *,
    check_orphan_fks: bool = True,
    enforce_workers_stopped: bool = False,
) -> PreflightReport:
    """
    Phase 1 preflight — non-destructive.

    Enforced:
    - Backend detection (see :func:`detect_backend_kind`).
    - ``projects.id`` and ``watch_dirs.id`` parse as RFC-4122 UUID when present.

    Documented TODO (not enforced unless ``enforce_workers_stopped=True`` raises):
    - Maintenance mode / no active mutation jobs / workers idle — requires app wiring.
    - Full orphan-FK scans on large databases — cheap checks only when requested.

    ``insert`` DbIdentity UUID-safety for the driver is assumed from Block A; we do not
    re-verify driver implementation here beyond notes.
    """
    backend = detect_backend_kind(db)
    notes = [
        "Workers/maintenance gates (Phase 1 items 4–5, 159) require orchestration; TODO unless "
        "enforce_workers_stopped=True.",
        "Swap/destructive phases must not run with active writers — guard is documentation + "
        "optional enforce_workers_stopped.",
    ]

    rp = PreflightReport(backend=backend, notes=list(notes))

    if enforce_workers_stopped:
        raise UuidMigrationPreflightError(
            "enforce_workers_stopped was requested but worker idle detection is TODO"
        )

    for tbl in ("projects", "watch_dirs"):
        try:
            n = _scalar_int(db, f"SELECT COUNT(*) FROM {tbl}")
        except Exception:
            rp.warnings.append(
                f"Skipping UUID check: table missing or inaccessible: {tbl}"
            )
            continue
        if n == 0:
            continue
        ids = _rows_pk_values(db, f"SELECT id FROM {tbl}")
        bad: List[Any] = []
        for x in ids:
            try:
                _validate_uuid_text(str(x))
            except UuidMigrationPreflightError:
                bad.append(x)
        if bad:
            if tbl == "projects":
                rp.projects_uuid_ok = False
            else:
                rp.watch_dirs_uuid_ok = False
            raise UuidMigrationPreflightError(
                f"{tbl}.id contains non-UUID values (sample): {bad[:5]}"
            )

    if check_orphan_fks:
        try:
            orph = _scalar_int(
                db,
                """
                SELECT COUNT(*) FROM files f
                LEFT JOIN projects p ON p.id = f.project_id
                WHERE p.id IS NULL AND f.project_id IS NOT NULL
                """,
            )
            if orph > 0:
                raise UuidMigrationPreflightError(
                    f"Orphan FK: files rows with unknown project_id (count={orph})"
                )
        except UuidMigrationPreflightError:
            raise
        except Exception as exc:
            rp.warnings.append(
                f"Cheap orphan check skipped/failed ({exc}); enlarge when schema exposes FK ids."
            )

    return rp


@dataclass
class Phase2Report:
    """Represent Phase2Report."""

    backend: BackendKind
    migration_tables: Tuple[str, ...]
    counts: Dict[str, Tuple[int, int]]  # migration_table -> (source_count, map_count)


def _insert_mapping_pairs(
    db: Any,
    mig_table: str,
    pairs: Sequence[Tuple[int, str]],
) -> None:
    # Unified ``?`` placeholders — PostgreSQL driver translates to ``%s`` (see postgres_run).
    """Return insert mapping pairs."""
    sql = (
        f"INSERT INTO {_valid_ident(mig_table)} "
        "(old_id, new_id) VALUES (?, ?) ON CONFLICT (old_id) DO NOTHING"
    )
    for old_i, nid in pairs:
        _migration_execute(db, sql, (old_i, nid))
    _migration_commit(db)


def _fill_mapping_for_table(
    db: Any,
    source_table: str,
    mig_table: str,
) -> None:
    """Return fill mapping for table."""
    _valid_ident(source_table)
    _valid_ident(mig_table)
    missing_ids = _rows_first_col(
        db,
        f"""
        SELECT s.id FROM {_valid_ident(source_table)} s
        LEFT JOIN {_valid_ident(mig_table)} m ON m.old_id = s.id
        WHERE m.old_id IS NULL
        """,
    )
    if not missing_ids:
        return
    pairs = [(mid, str(uuid.uuid4())) for mid in missing_ids]
    _insert_mapping_pairs(db, mig_table, pairs)


def validate_mapping_tables(
    db: Any,
    specs: Sequence[Tuple[str, str]],
) -> Dict[str, Tuple[int, int]]:
    """Ensure row-count parity (source vs mapping), uniqueness enforced by DDL + verify."""
    counts: Dict[str, Tuple[int, int]] = {}
    for src, mig in specs:
        sct = _scalar_int(db, f"SELECT COUNT(*) FROM {_valid_ident(src)}")
        mct = _scalar_int(db, f"SELECT COUNT(*) FROM {_valid_ident(mig)}")
        if sct != mct:
            raise UuidMigrationError(
                f"Coverage mismatch {src!r}: source rows={sct}, {mig!r} rows={mct}"
            )
        u_old = _scalar_int(
            db, f"SELECT COUNT(DISTINCT old_id) FROM {_valid_ident(mig)}"
        )
        u_new = _scalar_int(
            db, f"SELECT COUNT(DISTINCT new_id) FROM {_valid_ident(mig)}"
        )
        if u_old != mct or u_new != mct:
            raise UuidMigrationError(
                f"Uniqueness failed for {mig!r}: rows={mct}, distinct old={u_old}, "
                f"distinct new={u_new}"
            )
        counts[mig] = (sct, mct)
    return counts


def run_uuid_migration_phase2_build_mappings(
    db: Any,
    *,
    specs: Optional[Sequence[Tuple[str, str]]] = None,
    skip_preflight: bool = False,
) -> Phase2Report:
    """
    Phase 2: create mapping DDL if missing and populate mappings idempotently.

    Generates **new_id** via :func:`uuid.uuid4`; never casts INTEGER to STRING as UUID without
    proper random/str UUID generation.

    Does **not** drop tables, swap, or touch ``vector_id`` (remains int in source rows).
    """
    if not skip_preflight:
        run_uuid_migration_preflight_phase1(db, check_orphan_fks=False)

    backend = detect_backend_kind(db)
    from .uuid_identity_migration_postgres import create_mapping_tables_postgres

    for stmt in create_mapping_tables_postgres():
        _migration_execute(db, stmt)
    _migration_commit(db)

    use = specs if specs is not None else MANDATORY_SOURCE_TO_MIGRATION

    tables_present: List[str] = []
    for src, mig in use:
        try:
            _scalar_int(db, f"SELECT COUNT(*) FROM {_valid_ident(src)} LIMIT 1")
        except Exception as exc:
            raise UuidMigrationError(
                f"Source table {src!r} missing; cannot build mapping: {exc}"
            ) from exc
        tables_present.append(mig)

    for src, mig in use:
        _fill_mapping_for_table(db, src, mig)

    cnt = validate_mapping_tables(db, use)
    return Phase2Report(
        backend=backend,
        migration_tables=tuple(m[1] for m in use),
        counts=cnt,
    )


def make_mapping_lookup_closure(
    db: Any,
    _backend: Optional[BackendKind] = None,
) -> Callable[[str, int], Optional[str]]:
    """
    Closure for tests / Phase 4: ``(source_table, old_id) -> new_id`` string.

    Uses uuid_migration_* tables selected by mapping_table_for_source.

    Legacy ``backend`` parameter is ignored — unified ``?`` placeholders.
    """

    del _backend  # reserved for adapters that bypass driver placeholder rewrite

    def lookup(source_table: str, old_entity_id_int: int) -> Optional[str]:
        """Return lookup."""
        mt = mapping_table_for_source(source_table)
        r = _migration_fetchone(
            db,
            f"SELECT new_id FROM {_valid_ident(mt)} WHERE old_id = ?",
            (old_entity_id_int,),
        )
        if not r:
            return None
        if isinstance(r, dict):
            return str(next(iter(r.values())))
        return str(r[0])

    return lookup
