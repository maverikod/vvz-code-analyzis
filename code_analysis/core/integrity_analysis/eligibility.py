"""
Eligibility: integrity scans run only when file watcher is not holding the project lease.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from code_analysis.core.worker_project_activity import get_project_activity


def is_project_available_for_integrity_scan(
    database: Any, project_id: str
) -> Tuple[bool, str]:
    """
    Return (True, reason) when integrity analysis may run on ``project_id``.

    Blocked only when an **active** ``project_activity_locks`` row has
    ``owner_type='watcher'`` (lease_until >= now).
    """
    row: Optional[Dict[str, Any]] = get_project_activity(database, project_id)
    if row is None:
        return True, "no_activity_lock"
    now = time.time()
    lease_until = row.get("lease_until")
    try:
        lease_f = float(lease_until) if lease_until is not None else 0.0
    except (TypeError, ValueError):
        lease_f = 0.0
    if lease_f < now:
        return True, "watcher_lease_expired"
    owner_type = str(row.get("owner_type") or "")
    if owner_type == "watcher":
        return False, "watcher_active"
    return True, "other_owner_active"
