"""
Queue cancellation helpers for search sessions (T-005/A-003 prerequisite).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Optional

from code_analysis.core.search_session.manifest import SearchSessionManifest

logger = logging.getLogger(__name__)


def queue_job_id_from_manifest(manifest: SearchSessionManifest) -> Optional[str]:
    """Extract queue_job_id from manifest process block if present."""
    process = manifest.process or {}
    job_id = process.get("queue_job_id")
    if job_id and str(job_id).strip():
        return str(job_id).strip()
    return None


async def cancel_queued_search_job(queue_job_id: str) -> bool:
    """Best-effort cancellation of a queued search job.

    Returns True when the cancel signal was sent, False when the job was not
    found or the queue subsystem is unavailable (non-fatal for search_cancel).
    """
    try:
        from mcp_proxy_adapter.commands.queue.manager import get_queue_manager

        mgr = get_queue_manager()
        mgr.cancel_job(queue_job_id)
        logger.info("[search_cancel] queue job %s cancel requested", queue_job_id)
        return True
    except Exception as exc:
        logger.warning(
            "[search_cancel] could not cancel queue job %s: %s", queue_job_id, exc
        )
        return False
