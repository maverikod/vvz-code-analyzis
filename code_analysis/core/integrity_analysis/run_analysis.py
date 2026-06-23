"""
Orchestrate integrity analysis for one project.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from code_analysis.core.integrity_analysis.eligibility import (
    is_project_available_for_integrity_scan,
)
from code_analysis.core.integrity_analysis.import_cycles_sql import (
    DEFAULT_MAX_CHAIN_DEPTH,
)
from code_analysis.core.integrity_analysis.import_cycles_resolver import (
    fetch_import_cycles_resolver,
)
from code_analysis.core.integrity_analysis.entity_index_check import (
    check_entity_index,
)
from code_analysis.core.integrity_analysis.issues_registry import (
    clear_integrity_issues,
    register_circular_import_issues,
    register_missing_file_issues,
)
from code_analysis.core.integrity_analysis.missing_files import (
    find_missing_indexed_files,
)
from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE

logger = logging.getLogger(__name__)


def _load_file_path_map(database: Any, project_id: str) -> Dict[str, str]:
    result = database.execute(
        f"""
        SELECT id, COALESCE(NULLIF(TRIM(relative_path), ''), path) AS label
        FROM files
        WHERE project_id = ? AND {WHERE_FILES_ACTIVE}
        """,
        (project_id,),
    )
    out: Dict[str, str] = {}
    for row in result.get("data") or []:
        if isinstance(row, dict):
            out[str(row["id"])] = str(row.get("label") or row["id"])
        else:
            out[str(row.id)] = str(getattr(row, "label", row.id))
    return out


def run_integrity_analysis_for_project(
    database: Any,
    project_id: str,
    project_root: Path,
    *,
    check_missing_files: bool = True,
    check_circular_imports: bool = True,
    max_import_chain_depth: int = DEFAULT_MAX_CHAIN_DEPTH,
) -> Dict[str, Any]:
    """
    Run integrity checks and register findings in ``issues``.

    Raises ``ValueError`` when the project is blocked by an active file watcher lease.
    """
    ok, reason = is_project_available_for_integrity_scan(database, project_id)
    if not ok:
        raise ValueError(
            f"Project {project_id} is not available for integrity scan: {reason}"
        )

    cleared = clear_integrity_issues(database, project_id)
    missing: List[Dict[str, Any]] = []
    cycles: List[List[str]] = []

    # Entity-index self-check (C-1): loud signal if files exist but entity rows == 0.
    entity_index = check_entity_index(database, project_id)
    if not entity_index["ok"]:
        logger.error(
            "[ENTITY_INDEX] desync for project %s: files=%s but entities=0 "
            "(functions/classes/methods all empty) — entity-path commands "
            "(list_code_entities/get_code_entity_info) will be unreliable; reindex needed",
            project_id,
            entity_index["files"],
        )

    if check_missing_files:
        missing = find_missing_indexed_files(database, project_id, project_root)

    if check_circular_imports:
        try:
            cycles = fetch_import_cycles_resolver(
                database,
                project_id,
                project_root,
                max_depth=max_import_chain_depth,
            )
        except Exception as exc:
            logger.exception(
                "Resolver circular-import detection failed for project %s: %s",
                project_id,
                exc,
            )
            raise

    path_map = _load_file_path_map(database, project_id)
    missing_count = 0
    cycle_count = 0
    if missing:
        missing_count = register_missing_file_issues(database, project_id, missing)
    if cycles:
        cycle_count = register_circular_import_issues(
            database,
            project_id,
            cycles,
            file_id_to_path=path_map,
        )

    return {
        "project_id": project_id,
        "skipped": False,
        "eligibility_reason": reason,
        "cleared_issues": cleared,
        "missing_files": missing,
        "missing_files_count": missing_count,
        "circular_imports": [[path_map.get(fid, fid) for fid in c] for c in cycles],
        "circular_imports_count": cycle_count,
        "max_import_chain_depth": max_import_chain_depth,
        "entity_index": entity_index,
        "entity_index_ok": entity_index["ok"],
    }
