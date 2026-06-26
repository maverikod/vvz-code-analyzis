"""
SQLite Phases 3–5: shadow UUID-as-TEXT tables, copy via ``uuid_migration_*`` maps, validate.

Canonical UUIDs are stored as **TEXT** (no PostgreSQL casts). Uses ``?``-friendly statements
only in helpers delegated to the common layer; batch DDL/DML here is literal SQL with SQLite
identifiers.

**FTS5:** Phases 3–5 do **not** modify ``code_content_fts``. The external-content FTS index
still tracks the live ``code_content`` rowids until Phase 6. :func:`run_uuid_migration_phase6_swap_sqlite`
drops ``code_content_fts`` before table renames (if present) and recreates it afterward so the
virtual table rebinds to the promoted UUID ``code_content`` table.

Phase 6 swap is destructive; requires ``i_confirm_maintenance_swap=True``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import copy
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from code_analysis.core.database.schema_definition import get_schema_definition
from code_analysis.core.database.schema_sync_sql import generate_create_table_sql
from code_analysis.core.database.schema_sync_virtual import (
    generate_recreate_virtual_table_sql,
)

from .uuid_identity_migration_common import (
    UuidMigrationError,
    _migration_commit,
    _migration_execute,
    _migration_fetchone,
    detect_backend_kind,
    validate_mapping_tables,
)
from .uuid_identity_postgres_data_migrate import (
    DEFAULT_SHADOW_PREFIX,
    MANDATORY_SOURCE_TO_MIGRATION,
    MIGRATED_TABLES_COPY_ORDER,
    Phase345Report,
    build_copy_insert_sql,
    build_phase5_validation_sql,
    build_truncate_shadow_sql,
    shadow_table_name,
)

logger = logging.getLogger(__name__)

_NON_SHADOW_REF_TABLES = frozenset({"projects", "watch_dirs"})


def _rewrite_fk_ref_table(
    ref: str, migrated: frozenset[str], shadow_prefix: str
) -> str:
    """Return rewrite fk ref table."""
    if ref in _NON_SHADOW_REF_TABLES:
        return ref
    if ref in migrated:
        return shadow_table_name(ref, shadow_prefix)
    return ref


def build_shadow_table_ddl_sqlite(
    *,
    shadow_prefix: str = DEFAULT_SHADOW_PREFIX,
) -> List[str]:
    """
    Phase 3 DDL: ``CREATE TABLE IF NOT EXISTS`` for each shadow table; UUID columns as TEXT.

    FK targets reference shadow peers where the referenced table is migrated; ``projects`` /
    ``watch_dirs`` stay canonical.
    """
    schema = get_schema_definition()
    tables = schema["tables"]
    migrated = frozenset(MIGRATED_TABLES_COPY_ORDER)
    out: List[str] = []
    for tname in MIGRATED_TABLES_COPY_ORDER:
        tdef = copy.deepcopy(tables[tname])
        shadow = shadow_table_name(tname, shadow_prefix)
        for fk in tdef.get("foreign_keys", []):
            fk["references_table"] = _rewrite_fk_ref_table(
                fk["references_table"], migrated, shadow_prefix
            )
        partial_schema = {"tables": {shadow: tdef}}
        sql = generate_create_table_sql(partial_schema, shadow)
        out.append(sql)
    return out


def build_copy_insert_sql_sqlite(
    shadow_prefix: str = DEFAULT_SHADOW_PREFIX,
) -> List[str]:
    """
    Phase 4 INSERT…SELECT for SQLite: same dependency order and polymorphic rules as PostgreSQL,
    with ``::uuid`` casts stripped (legacy ``project_id`` / ``watch_dir_id`` are already TEXT).
    """
    return [stmt.replace("::uuid", "") for stmt in build_copy_insert_sql(shadow_prefix)]


def _scalar_count(db: Any, sql: str) -> int:
    """Return scalar count."""
    r = _migration_fetchone(db, sql)
    if not r:
        return 0
    if isinstance(r, dict):
        return int(next(iter(r.values())))
    return int(r[0])


def _sqlite_has_code_content_fts(db: Any) -> bool:
    """Return sqlite has code content fts."""
    row = _migration_fetchone(
        db,
        """
        SELECT 1 FROM sqlite_master
        WHERE type IN ('table', 'virtual')
          AND name = 'code_content_fts'
        LIMIT 1
        """,
    )
    return row is not None


def run_uuid_migration_phases_3_to_5_sqlite(
    db: Any,
    *,
    shadow_prefix: str = DEFAULT_SHADOW_PREFIX,
    dry_run: bool = False,
    skip_mapping_validation: bool = False,
) -> Phase345Report:
    """
    Phases 3–5 for SQLite: create shadow TEXT-UUID tables, copy rows, validate.

    Prerequisites: Phase 2 mapping tables populated.

    Does **not** modify ``code_content_fts`` (see module docstring). Phase 6 rebuilds FTS when
    needed.

    With ``dry_run=True``, no DDL/DML runs; ``sql_log`` lists Phase 3–5 statements only.
    """
    if detect_backend_kind(db) != "sqlite":
        raise UuidMigrationError(
            "Phases 3–5 data migration in this module are SQLite-only"
        )

    if not skip_mapping_validation:
        validate_mapping_tables(db, MANDATORY_SOURCE_TO_MIGRATION)

    sql_log: List[str] = []
    executed = 0

    phase3 = build_shadow_table_ddl_sqlite(shadow_prefix=shadow_prefix)
    trunc = build_truncate_shadow_sql(shadow_prefix=shadow_prefix)
    copies = build_copy_insert_sql_sqlite(shadow_prefix=shadow_prefix)

    for stmt in phase3 + trunc + copies:
        sql_log.append(stmt)
        if not dry_run:
            _migration_execute(db, stmt)
            executed += 1

    row_pairs: Dict[str, Tuple[int, int]] = {}
    validation: Dict[str, int] = {}

    if not dry_run:
        _migration_commit(db)
        for base in MIGRATED_TABLES_COPY_ORDER:
            src_n = _scalar_count(db, f"SELECT COUNT(*) FROM {base}")
            sh = shadow_table_name(base, shadow_prefix)
            dst_n = _scalar_count(db, f"SELECT COUNT(*) FROM {sh}")
            if src_n != dst_n:
                raise UuidMigrationError(
                    f"Row count mismatch after copy {base!r}: source={src_n}, shadow={dst_n}"
                )
            row_pairs[base] = (src_n, dst_n)

        for name, vsql in build_phase5_validation_sql(shadow_prefix=shadow_prefix):
            bad = _scalar_count(db, vsql)
            validation[name] = bad
            if bad != 0:
                raise UuidMigrationError(
                    f"Phase 5 validation failed: {name} count={bad}"
                )

        uq_files = _scalar_count(
            db,
            f"""SELECT COUNT(*) FROM (
                SELECT project_id, path, COUNT(*) c FROM {shadow_table_name("files", shadow_prefix)}
                GROUP BY project_id, path HAVING COUNT(*) > 1
            ) t""",
        )
        if uq_files != 0:
            raise UuidMigrationError(
                f"Shadow files UNIQUE(project_id, path) violated: {uq_files}"
            )
        uq_vi = _scalar_count(
            db,
            f"""SELECT COUNT(*) FROM (
                SELECT project_id, entity_type, entity_id, COUNT(*) c
                FROM {shadow_table_name("vector_index", shadow_prefix)}
                GROUP BY project_id, entity_type, entity_id HAVING COUNT(*) > 1
            ) t""",
        )
        if uq_vi != 0:
            raise UuidMigrationError(
                f"Shadow vector_index UNIQUE(project_id, entity_type, entity_id) violated: {uq_vi}"
            )
        uq_ie = _scalar_count(
            db,
            f"""SELECT COUNT(*) FROM (
                SELECT project_id, file_path, COUNT(*) c
                FROM {shadow_table_name("indexing_errors", shadow_prefix)}
                GROUP BY project_id, file_path HAVING COUNT(*) > 1
            ) t""",
        )
        if uq_ie != 0:
            raise UuidMigrationError(
                f"Shadow indexing_errors UNIQUE(project_id, file_path) violated: {uq_ie}"
            )
        uq_chk = _scalar_count(
            db,
            f"""SELECT COUNT(*) FROM (
                SELECT chunk_uuid, COUNT(*) c
                FROM {shadow_table_name("code_chunks", shadow_prefix)}
                GROUP BY chunk_uuid HAVING COUNT(*) > 1
            ) t""",
        )
        if uq_chk != 0:
            raise UuidMigrationError(
                f"Shadow code_chunks UNIQUE(chunk_uuid) violated: {uq_chk}"
            )

    return Phase345Report(
        backend="sqlite",
        shadow_prefix=shadow_prefix,
        dry_run=dry_run,
        statements_executed=executed,
        row_counts_source_vs_shadow=row_pairs,
        validation=validation,
        sql_log=sql_log,
    )


def run_uuid_migration_phase6_swap_sqlite(
    db: Any,
    *,
    shadow_prefix: str = DEFAULT_SHADOW_PREFIX,
    migration_tag: Optional[str] = None,
    i_confirm_maintenance_swap: bool = False,
) -> List[str]:
    """
    Phase 6 — **destructive**: rename live INTEGER-key tables to ``*_int_backup_<tag>`` and
    promote shadow UUID-TEXT tables to canonical names.

    If ``code_content_fts`` exists, it is **dropped** before renames (required: external content
    targets ``code_content`` by name) and **recreated** after promotion via
    :func:`generate_recreate_virtual_table_sql`, re-indexing from the new ``code_content`` rows.

    Refuses unless ``i_confirm_maintenance_swap=True``.
    """
    if not i_confirm_maintenance_swap:
        raise UuidMigrationError(
            "Phase 6 swap refused: set i_confirm_maintenance_swap=True only after maintenance "
            "window + backup; see docstring."
        )
    if detect_backend_kind(db) != "sqlite":
        raise UuidMigrationError("Phase 6 swap in this module is SQLite-only")

    tag = migration_tag or str(uuid.uuid4())[:8]
    backup_suffix = f"_int_backup_{tag}"

    fts_existed = _sqlite_has_code_content_fts(db)
    stmts: List[str] = []

    if fts_existed:
        drop_fts = "DROP TABLE IF EXISTS code_content_fts"
        stmts.append(drop_fts)
        _migration_execute(db, drop_fts)

    old_first = list(reversed(MIGRATED_TABLES_COPY_ORDER))
    new_second = list(MIGRATED_TABLES_COPY_ORDER)

    for t in old_first:
        s = f"ALTER TABLE {t} RENAME TO {t}{backup_suffix}"
        stmts.append(s)
        _migration_execute(db, s)
    for t in new_second:
        sh = shadow_table_name(t, shadow_prefix)
        s = f"ALTER TABLE {sh} RENAME TO {t}"
        stmts.append(s)
        _migration_execute(db, s)

    if fts_existed:
        vdefs = get_schema_definition().get("virtual_tables", [])
        fts_def = next((v for v in vdefs if v.get("name") == "code_content_fts"), None)
        if fts_def is None:
            raise UuidMigrationError(
                "code_content_fts was present but schema has no virtual_tables definition "
                "for code_content_fts — cannot rebuild FTS"
            )
        for s in generate_recreate_virtual_table_sql("code_content_fts", fts_def):
            stmts.append(s)
            _migration_execute(db, s)

    _migration_commit(db)
    logger.warning(
        "[uuid-migration] SQLite Phase 6 swap completed tag=%s fts_rebuilt=%s",
        tag,
        fts_existed,
    )
    return stmts


__all__ = [
    "build_copy_insert_sql_sqlite",
    "build_shadow_table_ddl_sqlite",
    "run_uuid_migration_phase6_swap_sqlite",
    "run_uuid_migration_phases_3_to_5_sqlite",
]
