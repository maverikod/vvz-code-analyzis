"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for BVP block processing system.

This module provides the base implementation that initialises the block
processing infrastructure, domain specific components, and shared state for
BVP envelope computations.
"""

from typing import Any, Dict
import logging

try:
    import cupy as cp  # type: ignore
    CUDA_AVAILABLE = True
except ImportError:  # pragma: no cover - CUDA optional
    cp = None  # type: ignore
    CUDA_AVAILABLE = False

from ...domain import Domain
from ...domain.enhanced_block_processor import (
    EnhancedBlockProcessor,
    ProcessingConfig,
    ProcessingMode,
)
from ...domain.domain_7d import Domain7D
from ..quench_detector import QuenchDetector
from ..bvp_impedance_calculator import BVPImpedanceCalculator
from ..phase_vector.phase_vector import PhaseVector
from ....utils.memory_monitor import MemoryMonitor
from ..bvp_block_processing import BVPBlockSolver
from .bvp_block_processing_config import BVPBlockConfig


class BVPBlockProcessingBase:
    """
    Base class for BVP block processing system.
    
    Physical Meaning:
        Sets up the intelligent block processing infrastructure that enables
        memory-aware 7D BVP computations with optional GPU acceleration and
        auxiliary analysis components.
    """

    def __init__(self, domain: Domain, config: BVPBlockConfig | None = None):
        """
        Initialise BVP block processing system.
        
        Args:
            domain: 7D computational domain instance.
            config: Optional configuration for block processing.
        """
        self.domain = domain
        self.config = config or BVPBlockConfig()
        self.logger = logging.getLogger(__name__)
        self.cuda_available = CUDA_AVAILABLE and self.config.enable_gpu_acceleration

        processing_config = ProcessingConfig(
            mode=ProcessingMode.ADAPTIVE,
            max_memory_usage=self.config.max_memory_usage,
            min_block_size=4,
            max_block_size=self.config.block_size,
            overlap_ratio=self.config.overlap_ratio,
            enable_memory_optimization=self.config.enable_memory_optimization,
            enable_adaptive_sizing=self.config.enable_adaptive_sizing,
            enable_parallel_processing=self.config.enable_parallel_processing,
        )

        self.block_processor = EnhancedBlockProcessor(domain, processing_config)

        if self.config.quench_detection_enabled and isinstance(domain, Domain7D):
            self.quench_detector = QuenchDetector(domain, {})
        else:
            self.quench_detector = None

        self.impedance_calculator = (
            BVPImpedanceCalculator(domain, {})
            if self.config.impedance_calculation_enabled
            else None
        )

        self.phase_vector = PhaseVector(domain, {})
        self.memory_monitor = MemoryMonitor()
        self.block_solver = BVPBlockSolver()

        self.stats: Dict[str, Any] = {
            "envelope_solves": 0,
            "quench_detections": 0,
            "impedance_calculations": 0,
            "blocks_processed": 0,
            "memory_peak_usage": 0.0,
            "processing_time": 0.0,
        }

        self.logger.info(
            "BVP block processing system initialised: block_size=%s, overlap_ratio=%s",
            self.config.block_size,
            self.config.overlap_ratio,
        )
