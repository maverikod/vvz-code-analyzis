"""
Per-project purge-gate signature: skip ``run_pre_scan_ignore_purge_for_project``
when nothing that could change its outcome has changed since the last run.

Bug 5b663fbb (cost half): the pre-scan ignore purge ran unconditionally every
cycle for every project (~190s live on project 44a8ce88), even though its
result depends only on two things -- the set of active ``files`` rows for the
project (DB-side) and the merged ignore-pattern policy (per-watch-dir +
global). Neither is expected to change most cycles. This mirrors the existing
``manifest_signature_cache`` / :func:`code_analysis.core.file_watcher_pkg.
watcher_disk_manifest.manifest_rebuild_needed` idiom (disk-side short-circuit,
bug 673ba07a) but keyed on the DB-side signature instead: unlike the disk
manifest signature, ``(COUNT(*), MAX(updated_at))`` over active files DOES
change whenever the watcher's own bulk sync inserts/updates/deletes rows for a
project, so this gate stays correct without ever needing to run the purge on
a cycle that could not have produced a different purge outcome.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, Optional, Sequence, Tuple

from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE

logger = logging.getLogger(__name__)

# (file_count, max_updated_at) over active files rows for one project.
DbPurgeSignature = Tuple[int, Optional[float]]
# (db_signature, policy_stamp) -- the full cache value per project_id.
PurgeGateSignature = Tuple[DbPurgeSignature, str]


def compute_project_db_purge_signature(database: Any, project_id: str) -> DbPurgeSignature:
    """
    Cheap DB-side ``(COUNT(*), MAX(updated_at))`` over active ``files`` rows.

    Single aggregate query (no full row fetch), scoped to one project -- reuses
    the shared :data:`WHERE_FILES_ACTIVE` predicate idiom so it always agrees
    with :func:`code_analysis.core.file_watcher_pkg.ignore_pre_scan_purge.
    collect_file_ids_to_purge_for_ignore_policy`'s own active-row selection.
    """
    sql = (
        "SELECT COUNT(*) AS cnt, MAX(updated_at) AS max_updated "
        f"FROM files WHERE project_id = ? AND {WHERE_FILES_ACTIVE}"
    )
    try:
        result = database.execute(sql, (project_id,))
    except Exception as exc:
        logger.warning(
            "[PURGE_GATE] db signature query failed for project_id=%s: %s "
            "(treating as changed -- purge will run)",
            project_id,
            exc,
        )
        return (-1, None)
    rows = list(result.get("data", [])) if isinstance(result, dict) else []
    if not rows:
        return (0, None)
    row = rows[0]
    count = int(row.get("cnt") or 0)
    max_updated_raw = row.get("max_updated")
    max_updated = float(max_updated_raw) if max_updated_raw is not None else None
    return (count, max_updated)


def compute_ignore_policy_stamp(ignore_patterns: Sequence[str]) -> str:
    """
    Stable hash of the merged ignore-pattern tuple (order preserved -- a caller
    that legitimately reorders precedence has changed the policy, so the stamp
    should change too).
    """
    joined = "\x1f".join(str(p) for p in ignore_patterns)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def purge_gate_needed(
    project_id: str,
    db_signature: DbPurgeSignature,
    policy_stamp: str,
    signature_cache: Optional[Dict[str, PurgeGateSignature]],
) -> bool:
    """
    True when the pre-scan ignore purge must run for ``project_id`` this cycle.

    True when there is no cache (gate disabled), no prior cached signature for
    the project (first sight after worker start), or either the DB signature or
    the policy stamp differs from the cached value.
    """
    if signature_cache is None:
        return True
    cached = signature_cache.get(project_id)
    return cached != (db_signature, policy_stamp)
