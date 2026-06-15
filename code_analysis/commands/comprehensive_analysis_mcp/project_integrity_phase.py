"""
Project-level integrity checks for comprehensive_analysis (issues table).

Missing indexed files on disk and circular import chains (SQL 3-step batch).
Skipped while file watcher holds an active project lease.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from code_analysis.core.integrity_analysis.eligibility import (
    is_project_available_for_integrity_scan,
)
from code_analysis.core.integrity_analysis.import_cycles_sql import (
    DEFAULT_MAX_CHAIN_DEPTH,
)
from code_analysis.core.integrity_analysis.run_analysis import (
    run_integrity_analysis_for_project,
)

logger = logging.getLogger(__name__)


def maybe_run_project_integrity_checks(
    database: Any,
    project_id: str,
    project_root: Path,
    *,
    check_missing_files: bool,
    check_circular_imports: bool,
    max_import_chain_depth: int = DEFAULT_MAX_CHAIN_DEPTH,
    analysis_logger: logging.Logger | None = None,
) -> Dict[str, Any]:
    """
    Run integrity phase when enabled; register findings in ``issues``.

    Does not raise when file watcher is active — returns ``skipped: true`` instead.
    """
    log = analysis_logger or logger
    if not check_missing_files and not check_circular_imports:
        return {
            "skipped": True,
            "reason": "checks_disabled",
            "missing_files_count": 0,
            "circular_imports_count": 0,
        }

    ok, reason = is_project_available_for_integrity_scan(database, project_id)
    if not ok:
        log.info(
            "Project integrity checks skipped project_id=%s reason=%s",
            project_id,
            reason,
        )
        return {
            "skipped": True,
            "reason": reason,
            "missing_files_count": 0,
            "circular_imports_count": 0,
        }

    log.info(
        "Running project integrity checks project_id=%s missing=%s circular=%s",
        project_id,
        check_missing_files,
        check_circular_imports,
    )
    summary = run_integrity_analysis_for_project(
        database,
        project_id,
        project_root,
        check_missing_files=check_missing_files,
        check_circular_imports=check_circular_imports,
        max_import_chain_depth=max_import_chain_depth,
    )
    summary["skipped"] = False
    return summary
