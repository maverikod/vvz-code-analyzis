"""
Optional full operation timing log for bottleneck analysis.

When log_all_operations_timing is True, every significant operation is logged
at INFO with duration and key=value context.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any


def log_operation_timing(
    enabled: bool,
    log: logging.Logger,
    op_name: str,
    duration_sec: float,
    **kwargs: Any,
) -> None:
    """
    Log a single operation with timing when full timing is enabled.

    Args:
        enabled: When True, log at INFO; when False, no-op.
        log: Logger instance.
        op_name: Operation identifier (e.g. "Step0_SELECT", "get_chunks_batch").
        duration_sec: Elapsed time in seconds.
        **kwargs: Optional key=value context (e.g. rows=10, file_id=123).
    """
    if not enabled:
        return
    parts = [f"[TIMING] {op_name} duration={duration_sec:.3f}s"]
    for k, v in sorted(kwargs.items()):
        parts.append(f"{k}={v}")
    log.info(" ".join(parts))
