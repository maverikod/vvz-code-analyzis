"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Impedance calculation mixin for BVP block processing system.

This module provides block-based impedance computation utilities.
"""

from typing import Any, Dict, List
import numpy as np


class BVPBlockProcessingImpedanceMixin:
    """Mixin implementing impedance calculations over blocks."""

    def compute_impedance_blocked(self, envelope: np.ndarray) -> Dict[str, List[Any]]:
        """Compute impedance characteristics in a block-wise fashion."""
        if not self.impedance_calculator:
            return {
                "admittance": [],
                "reflection": [],
                "transmission": [],
                "peaks": [],
            }

        self.logger.info("Computing impedance using block processing")
        all_admittance: List[Any] = []
        all_reflection: List[Any] = []
        all_transmission: List[Any] = []
        all_peaks: List[Any] = []

        for _, block_info in self.block_processor.base_processor.iterate_blocks():
            envelope_block = self._extract_envelope_block(envelope, block_info)
            block_impedance = self.impedance_calculator.compute_admittance(envelope_block)
            all_admittance.append(block_impedance.get("admittance", []))
            all_reflection.append(block_impedance.get("reflection", []))
            all_transmission.append(block_impedance.get("transmission", []))
            all_peaks.append(block_impedance.get("peaks", []))

        self.stats["impedance_calculations"] += 1
        return {
            "admittance": all_admittance,
            "reflection": all_reflection,
            "transmission": all_transmission,
            "peaks": all_peaks,
        }
