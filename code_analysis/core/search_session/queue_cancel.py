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
    proc = manifest.process
    process: dict = proc if isinstance(proc, dict) else {}  # type: ignore[assignment]
    job_id = process.get("queue_job_id")
    if job_id and str(job_id).strip():
        return str(job_id).strip()
    return None


async def cancel_queued_search_job(queue_job_id: str) -> bool:
    """Best-effort cancellation of a queued search job via queue_stop_job MCP command.

    Returns True when the stop signal was sent, False when unavailable (non-fatal).
    """
    try:
        from mcp_proxy_adapter.commands.command_registry import registry

        cmd_cls = registry.get_command("queue_stop_job")
        await cmd_cls.run(job_id=queue_job_id)
        logger.info("[search_cancel] queue job %s stop requested", queue_job_id)
        return True
    except Exception as exc:
        logger.warning(
            "[search_cancel] could not stop queue job %s: %s", queue_job_id, exc
        )
        return False
