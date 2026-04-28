"""
PostgreSQL Phases 3–5: shadow UUID tables, copy rows via ``uuid_migration_*`` maps, validate.

Phase 6 table swap is :func:`run_uuid_migration_phase6_swap_postgres` (destructive; opt-in).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import copy
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from code_analysis.core.database.schema_definition import get_schema_definition
from code_analysis.core.database.schema_sync_sql_postgres import (
    generate_create_table_sql_postgres,
)

from .uuid_identity_migration_common import (
    ENTITY_TYPE_TO_SOURCE_TABLE,
    MANDATORY_SOURCE_TO_MIGRATION,
    UuidMigrationError,
    _migration_commit,
    _migration_execute,
    _migration_fetchone,
    detect_backend_kind,
    mapping_table_for_source,
    validate_mapping_tables,
)

logger = logging.getLogger(__name__)

# Prefix for shadow tables (UUID schema, FKs to other shadow tables where applicable).
DEFAULT_SHADOW_PREFIX = "uuid_mig_new_"

# Business tables copied in dependency order (CREATE + INSERT). ``file_tree_snapshot_roots`` has
# no ``uuid_migration_*`` row map; ``snapshot_id`` is rewritten via ``uuid_migration_file_tree_snapshots``.
MIGRATED_TABLES_COPY_ORDER: Tuple[str, ...] = (
    "files",
    "classes",
    "functions",
    "methods",
    "entity_cross_ref",
    "imports",
    "issues",
    "usages",
    "code_content",
    "ast_trees",
    "cst_trees",
    "vector_index",
    "code_chunks",
    "code_duplicates",
    "duplicate_occurrences",
    "comprehensive_analysis_results",
    "file_tree_snapshots",
    "file_tree_snapshot_roots",
    "file_tree_snapshot_nodes",
    "indexing_errors",
)

# Tables referenced by shadow FKs that stay on canonical names (already UUID in Group 1).
_NON_SHADOW_REF_TABLES = frozenset({"projects", "watch_dirs"})


def shadow_table_name(base: str, shadow_prefix: str = DEFAULT_SHADOW_PREFIX) -> str:
    if not shadow_prefix.replace("_", "").isalnum() or not shadow_prefix.endswith("_"):
        raise ValueError(f"unsupported shadow_prefix: {shadow_prefix!r}")
    return f"{shadow_prefix}{base}"


def _rewrite_fk_ref_table(
    ref: str, migrated: frozenset[str], shadow_prefix: str
) -> str:
    if ref in _NON_SHADOW_REF_TABLES:
        return ref
    if ref in migrated:
        return shadow_table_name(ref, shadow_prefix)
    return ref


def build_shadow_table_ddl_postgres(
    *,
    shadow_prefix: str = DEFAULT_SHADOW_PREFIX,
) -> List[str]:
    """
    Phase 3 DDL: ``CREATE TABLE IF NOT EXISTS`` for each shadow table, PostgreSQL UUID types.

    FK targets point at sibling shadow tables where the referenced table is migrated; otherwise
    ``projects`` / ``watch_dirs`` keep canonical names.
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
        sql = generate_create_table_sql_postgres(partial_schema, shadow)
        out.append(sql)
    return out


def _polymorphic_entity_joins_and_expr(
    src_alias: str,
    *,
    entity_type_col: str = "entity_type",
    entity_id_col: str = "entity_id",
) -> Tuple[str, str]:
    """
    LEFT JOINs + CASE expression matching :data:`ENTITY_TYPE_TO_SOURCE_TABLE` /
    :func:`map_polymorphic_entity_id_to_new_uuid` rules.
    """
    et = f"LOWER(TRIM({src_alias}.{entity_type_col}))"
    eid = f"{src_alias}.{entity_id_col}"
    joins: List[str] = []

    # file + module -> uuid_migration_files
    joins.append(
        f"LEFT JOIN uuid_migration_files j_pol_fm ON ({et} IN ('file', 'module') "
        f"AND j_pol_fm.old_id = {eid})"
    )
    type_to_alias = {
        "class": "j_pol_class",
        "function": "j_pol_function",
        "method": "j_pol_method",
        "chunk": "j_pol_chunk",
    }
    for etype, alias in type_to_alias.items():
        mtab = mapping_table_for_source(ENTITY_TYPE_TO_SOURCE_TABLE[etype])
        joins.append(
            f"LEFT JOIN {mtab} {alias} ON ({et} = '{etype}' AND {alias}.old_id = {eid})"
        )

    expr = f"""CASE {et}
        WHEN 'file' THEN j_pol_fm.new_id
        WHEN 'module' THEN j_pol_fm.new_id
        WHEN 'class' THEN j_pol_class.new_id
        WHEN 'function' THEN j_pol_function.new_id
        WHEN 'method' THEN j_pol_method.new_id
        WHEN 'chunk' THEN j_pol_chunk.new_id
        ELSE NULL
    END"""
    return "\n".join(joins), expr


def build_truncate_shadow_sql(
    shadow_prefix: str = DEFAULT_SHADOW_PREFIX,
) -> List[str]:
    """DELETE all rows from shadow tables in reverse dependency order."""
    names = [
        shadow_table_name(t, shadow_prefix)
        for t in reversed(MIGRATED_TABLES_COPY_ORDER)
    ]
    return [f"DELETE FROM {n}" for n in names]


def build_copy_insert_sql(
    shadow_prefix: str = DEFAULT_SHADOW_PREFIX,
) -> List[str]:
    """Phase 4 ``INSERT INTO`` … ``SELECT`` statements rewriting PK/FK via ``uuid_migration_*``."""
    sp = shadow_prefix
    sfiles = shadow_table_name("files", sp)
    sclasses = shadow_table_name("classes", sp)
    sfunctions = shadow_table_name("functions", sp)
    smethods = shadow_table_name("methods", sp)
    scent = shadow_table_name("entity_cross_ref", sp)
    simports = shadow_table_name("imports", sp)
    sissues = shadow_table_name("issues", sp)
    susages = shadow_table_name("usages", sp)
    scc = shadow_table_name("code_content", sp)
    sast = shadow_table_name("ast_trees", sp)
    scst = shadow_table_name("cst_trees", sp)
    svi = shadow_table_name("vector_index", sp)
    schk = shadow_table_name("code_chunks", sp)
    sdup = shadow_table_name("code_duplicates", sp)
    sdocc = shadow_table_name("duplicate_occurrences", sp)
    scar = shadow_table_name("comprehensive_analysis_results", sp)
    sfts = shadow_table_name("file_tree_snapshots", sp)
    sftsr = shadow_table_name("file_tree_snapshot_roots", sp)
    sftsn = shadow_table_name("file_tree_snapshot_nodes", sp)
    sie = shadow_table_name("indexing_errors", sp)

    stmts: List[str] = []

    stmts.append(
        f"""
INSERT INTO {sfiles} (
    id, project_id, watch_dir_id, path, relative_path, lines, last_modified,
    has_docstring, deleted, original_path, version_dir, needs_chunking, created_at, updated_at
)
SELECT
    mf.new_id,
    f.project_id::uuid,
    f.watch_dir_id::uuid,
    f.path,
    f.relative_path,
    f.lines,
    f.last_modified,
    f.has_docstring,
    f.deleted,
    f.original_path,
    f.version_dir,
    f.needs_chunking,
    f.created_at,
    f.updated_at
FROM files f
JOIN uuid_migration_files mf ON mf.old_id = f.id
""".strip()
    )

    stmts.append(
        f"""
INSERT INTO {sclasses} (
    id, file_id, name, line, end_line, cst_node_id, docstring, bases, created_at
)
SELECT
    mc.new_id,
    mf.new_id,
    c.name,
    c.line,
    c.end_line,
    c.cst_node_id,
    c.docstring,
    c.bases,
    c.created_at
FROM classes c
JOIN uuid_migration_classes mc ON mc.old_id = c.id
JOIN uuid_migration_files mf ON mf.old_id = c.file_id
""".strip()
    )

    stmts.append(
        f"""
INSERT INTO {sfunctions} (
    id, file_id, name, line, end_line, cst_node_id, args, docstring, complexity, created_at
)
SELECT
    mfn.new_id,
    mf.new_id,
    fn.name,
    fn.line,
    fn.end_line,
    fn.cst_node_id,
    fn.args,
    fn.docstring,
    fn.complexity,
    fn.created_at
FROM functions fn
JOIN uuid_migration_functions mfn ON mfn.old_id = fn.id
JOIN uuid_migration_files mf ON mf.old_id = fn.file_id
""".strip()
    )

    stmts.append(
        f"""
INSERT INTO {smethods} (
    id, class_id, name, line, end_line, cst_node_id, args, docstring,
    is_abstract, has_pass, has_not_implemented, complexity, created_at
)
SELECT
    mm.new_id,
    mc.new_id,
    m.name,
    m.line,
    m.end_line,
    m.cst_node_id,
    m.args,
    m.docstring,
    m.is_abstract,
    m.has_pass,
    m.has_not_implemented,
    m.complexity,
    m.created_at
FROM methods m
JOIN uuid_migration_methods mm ON mm.old_id = m.id
JOIN uuid_migration_classes mc ON mc.old_id = m.class_id
""".strip()
    )

    stmts.append(
        f"""
INSERT INTO {scent} (
    id, caller_class_id, caller_method_id, caller_function_id,
    callee_class_id, callee_method_id, callee_function_id,
    ref_type, file_id, line, created_at
)
SELECT
    mer.new_id,
    mcc.new_id,
    mcm.new_id,
    mcf.new_id,
    mccc.new_id,
    mccm.new_id,
    mccf.new_id,
    e.ref_type,
    mf.new_id,
    e.line,
    e.created_at
FROM entity_cross_ref e
JOIN uuid_migration_entity_cross_ref mer ON mer.old_id = e.id
LEFT JOIN uuid_migration_classes mcc ON mcc.old_id = e.caller_class_id
LEFT JOIN uuid_migration_methods mcm ON mcm.old_id = e.caller_method_id
LEFT JOIN uuid_migration_functions mcf ON mcf.old_id = e.caller_function_id
LEFT JOIN uuid_migration_classes mccc ON mccc.old_id = e.callee_class_id
LEFT JOIN uuid_migration_methods mccm ON mccm.old_id = e.callee_method_id
LEFT JOIN uuid_migration_functions mccf ON mccf.old_id = e.callee_function_id
LEFT JOIN uuid_migration_files mf ON mf.old_id = e.file_id
""".strip()
    )

    stmts.append(
        f"""
INSERT INTO {simports} (
    id, file_id, name, module, import_type, line, created_at
)
SELECT
    mi.new_id,
    mf.new_id,
    i.name,
    i.module,
    i.import_type,
    i.line,
    i.created_at
FROM imports i
JOIN uuid_migration_imports mi ON mi.old_id = i.id
JOIN uuid_migration_files mf ON mf.old_id = i.file_id
""".strip()
    )

    stmts.append(
        f"""
INSERT INTO {sissues} (
    id, file_id, project_id, class_id, function_id, method_id,
    issue_type, line, description, metadata, created_at
)
SELECT
    mis.new_id,
    mf.new_id,
    iss.project_id::uuid,
    mcls.new_id,
    mfn.new_id,
    mm.new_id,
    iss.issue_type,
    iss.line,
    iss.description,
    iss.metadata,
    iss.created_at
FROM issues iss
JOIN uuid_migration_issues mis ON mis.old_id = iss.id
LEFT JOIN uuid_migration_files mf ON mf.old_id = iss.file_id
LEFT JOIN uuid_migration_classes mcls ON mcls.old_id = iss.class_id
LEFT JOIN uuid_migration_functions mfn ON mfn.old_id = iss.function_id
LEFT JOIN uuid_migration_methods mm ON mm.old_id = iss.method_id
""".strip()
    )

    stmts.append(
        f"""
INSERT INTO {susages} (
    id, file_id, line, usage_type, target_type, target_class, target_name, context, created_at
)
SELECT
    mu.new_id,
    mf.new_id,
    u.line,
    u.usage_type,
    u.target_type,
    u.target_class,
    u.target_name,
    u.context,
    u.created_at
FROM usages u
JOIN uuid_migration_usages mu ON mu.old_id = u.id
JOIN uuid_migration_files mf ON mf.old_id = u.file_id
""".strip()
    )

    cc_joins, cc_ent = _polymorphic_entity_joins_and_expr("cc")
    stmts.append(
        f"""
INSERT INTO {scc} (
    id, file_id, entity_type, entity_id, entity_name, content, docstring, created_at
)
SELECT
    mid.new_id,
    mf.new_id,
    cc.entity_type,
    ({cc_ent})::uuid,
    cc.entity_name,
    cc.content,
    cc.docstring,
    cc.created_at
FROM code_content cc
JOIN uuid_migration_code_content mid ON mid.old_id = cc.id
JOIN uuid_migration_files mf ON mf.old_id = cc.file_id
{cc_joins}
""".strip()
    )

    stmts.append(
        f"""
INSERT INTO {sast} (
    id, file_id, project_id, ast_json, ast_hash, file_mtime, created_at, updated_at
)
SELECT
    ma.new_id,
    mf.new_id,
    a.project_id::uuid,
    a.ast_json,
    a.ast_hash,
    a.file_mtime,
    a.created_at,
    a.updated_at
FROM ast_trees a
JOIN uuid_migration_ast_trees ma ON ma.old_id = a.id
JOIN uuid_migration_files mf ON mf.old_id = a.file_id
""".strip()
    )

    stmts.append(
        f"""
INSERT INTO {scst} (
    id, file_id, project_id, cst_code, cst_hash, file_mtime, created_at, updated_at
)
SELECT
    mc.new_id,
    mf.new_id,
    c.project_id::uuid,
    c.cst_code,
    c.cst_hash,
    c.file_mtime,
    c.created_at,
    c.updated_at
FROM cst_trees c
JOIN uuid_migration_cst_trees mc ON mc.old_id = c.id
JOIN uuid_migration_files mf ON mf.old_id = c.file_id
""".strip()
    )

    vi_joins, vi_ent = _polymorphic_entity_joins_and_expr("v")
    stmts.append(
        f"""
INSERT INTO {svi} (
    id, project_id, entity_type, entity_id, vector_id, vector_dim, embedding_model, created_at
)
SELECT
    mv.new_id,
    v.project_id::uuid,
    v.entity_type,
    ({vi_ent})::uuid,
    v.vector_id,
    v.vector_dim,
    v.embedding_model,
    v.created_at
FROM vector_index v
JOIN uuid_migration_vector_index mv ON mv.old_id = v.id
{vi_joins}
""".strip()
    )

    stmts.append(
        f"""
INSERT INTO {schk} (
    id, file_id, project_id, chunk_uuid, chunk_type, chunk_text, chunk_ordinal,
    vector_id, embedding_model, bm25_score, embedding_vector, token_count,
    class_id, function_id, method_id, line, ast_node_type, source_type,
    binding_level, created_at, updated_at, vectorization_skipped
)
SELECT
    mchk.new_id,
    mf.new_id,
    ch.project_id::uuid,
    ch.chunk_uuid,
    ch.chunk_type,
    ch.chunk_text,
    ch.chunk_ordinal,
    ch.vector_id,
    ch.embedding_model,
    ch.bm25_score,
    ch.embedding_vector,
    ch.token_count,
    mcls.new_id,
    mfn.new_id,
    mm.new_id,
    ch.line,
    ch.ast_node_type,
    ch.source_type,
    ch.binding_level,
    ch.created_at,
    ch.updated_at,
    ch.vectorization_skipped
FROM code_chunks ch
JOIN uuid_migration_code_chunks mchk ON mchk.old_id = ch.id
JOIN uuid_migration_files mf ON mf.old_id = ch.file_id
LEFT JOIN uuid_migration_classes mcls ON mcls.old_id = ch.class_id
LEFT JOIN uuid_migration_functions mfn ON mfn.old_id = ch.function_id
LEFT JOIN uuid_migration_methods mm ON mm.old_id = ch.method_id
""".strip()
    )

    stmts.append(
        f"""
INSERT INTO {sdup} (
    id, project_id, duplicate_hash, similarity, created_at
)
SELECT
    md.new_id,
    d.project_id::uuid,
    d.duplicate_hash,
    d.similarity,
    d.created_at
FROM code_duplicates d
JOIN uuid_migration_code_duplicates md ON md.old_id = d.id
""".strip()
    )

    stmts.append(
        f"""
INSERT INTO {sdocc} (
    id, duplicate_id, file_id, start_line, end_line, code_snippet, ast_node_id, created_at
)
SELECT
    mo.new_id,
    md.new_id,
    mf.new_id,
    o.start_line,
    o.end_line,
    o.code_snippet,
    o.ast_node_id,
    o.created_at
FROM duplicate_occurrences o
JOIN uuid_migration_duplicate_occurrences mo ON mo.old_id = o.id
JOIN uuid_migration_code_duplicates md ON md.old_id = o.duplicate_id
JOIN uuid_migration_files mf ON mf.old_id = o.file_id
""".strip()
    )

    stmts.append(
        f"""
INSERT INTO {scar} (
    id, file_id, project_id, file_mtime, results_json, summary_json, created_at, updated_at
)
SELECT
    mr.new_id,
    mf.new_id,
    r.project_id::uuid,
    r.file_mtime,
    r.results_json,
    r.summary_json,
    r.created_at,
    r.updated_at
FROM comprehensive_analysis_results r
JOIN uuid_migration_comprehensive_analysis_results mr ON mr.old_id = r.id
JOIN uuid_migration_files mf ON mf.old_id = r.file_id
""".strip()
    )

    stmts.append(
        f"""
INSERT INTO {sfts} (
    id, file_id, project_id, source_payload, file_mtime, created_at, updated_at
)
SELECT
    ms.new_id,
    mf.new_id,
    s.project_id::uuid,
    s.source_payload,
    s.file_mtime,
    s.created_at,
    s.updated_at
FROM file_tree_snapshots s
JOIN uuid_migration_file_tree_snapshots ms ON ms.old_id = s.id
JOIN uuid_migration_files mf ON mf.old_id = s.file_id
""".strip()
    )

    stmts.append(
        f"""
INSERT INTO {sftsr} (snapshot_id, root_node_id)
SELECT ms.new_id, r.root_node_id
FROM file_tree_snapshot_roots r
JOIN uuid_migration_file_tree_snapshots ms ON ms.old_id = r.snapshot_id
""".strip()
    )

    stmts.append(
        f"""
INSERT INTO {sftsn} (
    id, snapshot_id, node_id, parent_node_id, child_index
)
SELECT
    mn.new_id,
    ms.new_id,
    n.node_id,
    n.parent_node_id,
    n.child_index
FROM file_tree_snapshot_nodes n
JOIN uuid_migration_file_tree_snapshot_nodes mn ON mn.old_id = n.id
JOIN uuid_migration_file_tree_snapshots ms ON ms.old_id = n.snapshot_id
""".strip()
    )

    stmts.append(
        f"""
INSERT INTO {sie} (
    id, project_id, file_path, error_type, error_message, created_at
)
SELECT
    me.new_id,
    e.project_id::uuid,
    e.file_path,
    e.error_type,
    e.error_message,
    e.created_at
FROM indexing_errors e
JOIN uuid_migration_indexing_errors me ON me.old_id = e.id
""".strip()
    )

    return stmts


def build_phase5_validation_sql(
    shadow_prefix: str = DEFAULT_SHADOW_PREFIX,
) -> List[Tuple[str, str]]:
    """
    (name, sql) checks: expect scalar zero for orphan FK / mismatch counts.

    Polymorphic rows: orphan ``entity_id`` when type is mapped but new id is NULL.
    """
    sp = shadow_prefix
    sfiles = shadow_table_name("files", sp)
    schk = shadow_table_name("code_chunks", sp)
    sast = shadow_table_name("ast_trees", sp)

    checks: List[Tuple[str, str]] = []

    checks.append(
        (
            "orphan_code_chunks_file",
            f"""SELECT COUNT(*) FROM {schk} cc
            LEFT JOIN {sfiles} f ON f.id = cc.file_id
            WHERE f.id IS NULL""",
        )
    )
    checks.append(
        (
            "code_chunks_project_mismatch",
            f"""SELECT COUNT(*) FROM {schk} cc
            JOIN {sfiles} f ON f.id = cc.file_id
            WHERE cc.project_id IS DISTINCT FROM f.project_id""",
        )
    )
    checks.append(
        (
            "orphan_ast_trees_file",
            f"""SELECT COUNT(*) FROM {sast} a
            LEFT JOIN {sfiles} f ON f.id = a.file_id
            WHERE f.id IS NULL""",
        )
    )

    # Polymorphic resolution uses legacy INTEGER entity_id on **source** tables (not shadow UUIDs).
    cc_joins, cc_ent = _polymorphic_entity_joins_and_expr(
        "cc", entity_id_col="entity_id"
    )
    checks.append(
        (
            "code_content_polymorphic_entity_unresolved",
            f"""SELECT COUNT(*) FROM code_content cc
            {cc_joins}
            WHERE cc.entity_id IS NOT NULL
              AND LOWER(TRIM(cc.entity_type)) IN (
                  'file','module','class','function','method','chunk'
              )
              AND ({cc_ent}) IS NULL""",
        )
    )

    vi_joins, vi_ent = _polymorphic_entity_joins_and_expr(
        "vi", entity_id_col="entity_id"
    )
    checks.append(
        (
            "vector_index_polymorphic_entity_unresolved",
            f"""SELECT COUNT(*) FROM vector_index vi
            {vi_joins}
            WHERE LOWER(TRIM(vi.entity_type)) IN (
                'file','module','class','function','method','chunk'
            )
              AND ({vi_ent}) IS NULL""",
        )
    )

    return checks


@dataclass
class Phase345Report:
    backend: str
    shadow_prefix: str
    dry_run: bool
    statements_executed: int
    row_counts_source_vs_shadow: Dict[str, Tuple[int, int]] = field(
        default_factory=dict
    )
    validation: Dict[str, int] = field(default_factory=dict)
    sql_log: List[str] = field(default_factory=list)


def _scalar_count(db: Any, sql: str) -> int:
    r = _migration_fetchone(db, sql)
    if not r:
        return 0
    if isinstance(r, dict):
        return int(next(iter(r.values())))
    return int(r[0])


def run_uuid_migration_phases_3_to_5_postgres(
    db: Any,
    *,
    shadow_prefix: str = DEFAULT_SHADOW_PREFIX,
    dry_run: bool = False,
    skip_mapping_validation: bool = False,
) -> Phase345Report:
    """
    Phases 3–5 for PostgreSQL only: create shadow tables, copy rows, validate.

    Prerequisites: Phase 2 mapping tables populated (:func:`run_uuid_migration_phase2_build_mappings`).

    Group 1 tables (``watch_dirs``, ``projects``, …) are not copied; casts assume legacy TEXT UUID.

    Phase 6 rename/swap is **not** run here. With ``dry_run=True``, no DDL/DML is executed; returned
    ``sql_log`` contains Phase 3–5 SQL only (no swap statements).
    """
    if detect_backend_kind(db) != "postgresql":
        raise UuidMigrationError(
            "Phases 3–5 data migration in this module are PostgreSQL-only"
        )

    if not skip_mapping_validation:
        validate_mapping_tables(db, MANDATORY_SOURCE_TO_MIGRATION)

    sql_log: List[str] = []
    executed = 0

    phase3 = build_shadow_table_ddl_postgres(shadow_prefix=shadow_prefix)
    trunc = build_truncate_shadow_sql(shadow_prefix=shadow_prefix)
    copies = build_copy_insert_sql(shadow_prefix=shadow_prefix)

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

        # Uniqueness parity (shadow): same distinct keys as enforced in schema where applicable.
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
        backend="postgresql",
        shadow_prefix=shadow_prefix,
        dry_run=dry_run,
        statements_executed=executed,
        row_counts_source_vs_shadow=row_pairs,
        validation=validation,
        sql_log=sql_log,
    )


def run_uuid_migration_phase6_swap_postgres(
    db: Any,
    *,
    shadow_prefix: str = DEFAULT_SHADOW_PREFIX,
    migration_tag: Optional[str] = None,
    i_confirm_maintenance_swap: bool = False,
) -> List[str]:
    """
    Phase 6 — **destructive**: rename live INTEGER-key tables to ``*_int_backup_<tag>`` and promote
    shadow UUID tables to canonical names.

    **Requires maintenance mode:** stop all writers, drain mutation workers, and take a backup before
    calling. Incorrect use can corrupt the database or leave FKs inconsistent.

    This function **refuses** to run unless ``i_confirm_maintenance_swap=True`` (explicit opt-in).

    Returns the list of ``ALTER TABLE … RENAME TO`` statements executed (for audit logs).

    Phase 7+ (runtime verification, optional FAISS rebuild per Step 15) is out of scope here.
    """
    if not i_confirm_maintenance_swap:
        raise UuidMigrationError(
            "Phase 6 swap refused: set i_confirm_maintenance_swap=True only after maintenance "
            "window + backup; see docstring."
        )
    if detect_backend_kind(db) != "postgresql":
        raise UuidMigrationError("Phase 6 swap in this module is PostgreSQL-only")

    tag = migration_tag or str(uuid.uuid4())[:8]
    backup_suffix = f"_int_backup_{tag}"

    # Rename old tables first (frees canonical names), then promote shadow tables.
    # Order: old tables reverse dependency, then new tables forward dependency.
    old_first = list(reversed(MIGRATED_TABLES_COPY_ORDER))
    new_second = list(MIGRATED_TABLES_COPY_ORDER)

    stmts: List[str] = []
    for t in old_first:
        stmts.append(f'ALTER TABLE "{t}" RENAME TO "{t}{backup_suffix}"')
    for t in new_second:
        sh = shadow_table_name(t, shadow_prefix)
        stmts.append(f'ALTER TABLE "{sh}" RENAME TO "{t}"')

    for s in stmts:
        _migration_execute(db, s)
    _migration_commit(db)
    logger.warning(
        "[uuid-migration] Phase 6 swap completed tag=%s — verify application and FK health",
        tag,
    )
    return stmts


__all__ = [
    "DEFAULT_SHADOW_PREFIX",
    "MIGRATED_TABLES_COPY_ORDER",
    "Phase345Report",
    "build_copy_insert_sql",
    "build_phase5_validation_sql",
    "build_shadow_table_ddl_postgres",
    "build_truncate_shadow_sql",
    "run_uuid_migration_phase6_swap_postgres",
    "run_uuid_migration_phases_3_to_5_postgres",
    "shadow_table_name",
]
