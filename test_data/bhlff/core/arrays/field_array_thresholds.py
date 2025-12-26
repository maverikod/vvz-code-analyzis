"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Swap threshold utilities for FieldArray memory management.

Provides helper functions that compute swap thresholds based on
available GPU memory (80% usage) or environment overrides, keeping
FieldArray files concise and ensuring consistent policies across
array-related modules.

Physical Meaning:
    Determines how large 7D phase field arrays can grow before they
    must be transparently swapped to disk, ensuring GPU memory usage
    never exceeds 80% of the available pool during Level A workloads.

Example:
    >>> from bhlff.core.arrays.field_array_thresholds import get_default_swap_threshold_gb
    >>> threshold = get_default_swap_threshold_gb()
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def get_default_swap_threshold_gb() -> float:
    """
    Compute default swap threshold using 80% of available GPU memory.

    Physical Meaning:
        Uses 80% of the currently free GPU memory as the swap threshold
        so FieldArray transparently moves large tensors to disk before
        any allocation threatens GPU stability. Allows tests to override
        the limit via environment variable for deterministic behavior.

    Returns:
        float: Swap threshold measured in gigabytes.
    """

    env_threshold = os.getenv("BHLFF_SWAP_THRESHOLD_GB")
    if env_threshold is not None:
        return float(env_threshold)

    try:
        from ...utils.cuda_utils import get_global_backend, CUDABackend

        backend = get_global_backend()
        if isinstance(backend, CUDABackend):
            mem_info = backend.get_memory_info()
            free_memory = mem_info.get("free_memory", mem_info.get("total_memory", 0))
            threshold_gb = (free_memory * 0.8) / 1e9
            logger.info(
                "Swap threshold based on GPU memory: %.3f GB (free %.3f GB)",
                threshold_gb,
                free_memory / 1e9,
            )
            return threshold_gb
    except Exception as exc:
        logger.warning("Unable to determine GPU memory, using default threshold: %s", exc)

    return 0.01

