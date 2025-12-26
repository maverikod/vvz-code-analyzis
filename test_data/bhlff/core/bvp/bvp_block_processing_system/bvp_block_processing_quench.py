"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Quench detection mixin for BVP block processing system.

This module provides block-based quench detection utilities.
"""

from typing import Any, Dict, List
import numpy as np


class BVPBlockProcessingQuenchMixin:
    """Mixin implementing block-based quench detection workflow."""

    def detect_quenches_blocked(self, envelope: np.ndarray) -> Dict[str, Any]:
        """Detect quench events using block processing."""
        if not self.quench_detector:
            return {"quenches": [], "total_quenches": 0}

        self.logger.info("Detecting quenches using block processing")
        all_quenches: List[Dict[str, Any]] = []

        for _, block_info in self.block_processor.base_processor.iterate_blocks():
            envelope_block = self._extract_envelope_block(envelope, block_info)
            block_quenches = self.quench_detector.detect(envelope_block)
            adjusted_quenches = self._adjust_quench_positions(block_quenches, block_info)
            all_quenches.extend(adjusted_quenches)

        self.stats["quench_detections"] += 1
        return {"quenches": all_quenches, "total_quenches": len(all_quenches)}

    def _adjust_quench_positions(self, block_quenches: List, block_info) -> List:
        """Convert block-local quench coordinates to global coordinates."""
        if not block_quenches:
            return []

        start_indices = block_info.start_indices
        adjusted: List[Any] = []

        for quench in block_quenches:
            adjusted_quench = quench.copy() if hasattr(quench, "copy") else dict(quench)

            if "position" in adjusted_quench:
                local_pos = adjusted_quench["position"]
                if isinstance(local_pos, (list, tuple, np.ndarray)) and len(local_pos) == 7:
                    global_pos = [local_pos[i] + start_indices[i] for i in range(7)]
                    adjusted_quench["position"] = tuple(global_pos)

            if "indices" in adjusted_quench:
                local_idx = adjusted_quench["indices"]
                if isinstance(local_idx, (list, tuple, np.ndarray)) and len(local_idx) == 7:
                    global_idx = [local_idx[i] + start_indices[i] for i in range(7)]
                    adjusted_quench["indices"] = tuple(global_idx)

            adjusted.append(adjusted_quench)

        return adjusted
