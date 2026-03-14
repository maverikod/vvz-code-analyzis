"""
Database worker: cleanup expired jobs.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Any, Dict


logger = logging.getLogger(__name__)


def cleanup_expired_jobs(
    jobs: Dict[str, Dict[str, Any]],
    jobs_lock: threading.Lock,
    job_timeout: float = 300.0,
) -> None:
    """Clean up expired jobs from queue."""
    now = datetime.now()
    expired_job_ids = []
    with jobs_lock:
        for job_id, job in jobs.items():
            created_at = job.get("created_at")
            if created_at and (now - created_at) > timedelta(seconds=job_timeout):
                expired_job_ids.append(job_id)
        for job_id in expired_job_ids:
            logger.debug(f"Cleaning up expired job: {job_id}")
            del jobs[job_id]
    if expired_job_ids:
        logger.info(f"Cleaned up {len(expired_job_ids)} expired jobs")
