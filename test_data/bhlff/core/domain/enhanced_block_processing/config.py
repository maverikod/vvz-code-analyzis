"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Configuration for enhanced block processing.
"""

from dataclasses import dataclass
from enum import Enum


class ProcessingMode(Enum):
    """Processing mode for block operations."""

    CPU_ONLY = "cpu_only"
    GPU_PREFERRED = "gpu_preferred"
    GPU_ONLY = "gpu_only"
    ADAPTIVE = "adaptive"


@dataclass
class ProcessingConfig:
    """Configuration for enhanced block processing."""

    mode: ProcessingMode = ProcessingMode.ADAPTIVE
    max_memory_usage: float = 0.8  # 80% of available memory
    min_block_size: int = 4
    max_block_size: int = 64
    overlap_ratio: float = 0.1  # 10% overlap between blocks
    batch_size: int = 4
    enable_memory_optimization: bool = True
    enable_adaptive_sizing: bool = True
    enable_parallel_processing: bool = True

