"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Solver mixin for BVP block processing system.

This module provides the iterative envelope solver logic together with helper
methods for block extraction, merging, and convergence checking.
"""

from __future__ import annotations

from typing import Optional
import numpy as np
import time

from bhlff.core.sources.blocked_field_generator import BlockedFieldGenerator


class BVPBlockProcessingSolverMixin:
    """Mixin implementing block-based BVP envelope solving."""

    def solve_envelope_blocked(
        self,
        source: np.ndarray,
        max_iterations: Optional[int] = None,
        tolerance: Optional[float] = None,
    ) -> np.ndarray:
        """
        Solve the BVP envelope equation using block processing.
        
        Physical Meaning:
            Computes the envelope a(x, φ, t) satisfying the block-decomposed BVP
            equation with intelligent memory management.
        """
        max_iterations = max_iterations or self.config.max_envelope_iterations
        tolerance = tolerance or self.config.envelope_tolerance

        self.logger.info(
            "Solving BVP envelope: shape=%s, max_iterations=%s, tolerance=%s",
            source.shape,
            max_iterations,
            tolerance,
        )

        start_time = time.time()
        total_elements = int(np.prod(self.domain.shape))
        memory_needed_gb = (total_elements * 16) / (1024**3)

        if memory_needed_gb > 1.0:
            def zero_block_generator(domain, slice_config, config):
                block_shape = slice_config["shape"]
                if len(block_shape) != 7:
                    raise ValueError(
                        "Expected 7D block shape for envelope initialisation, "
                        f"received {len(block_shape)}D"
                    )
                return np.zeros(block_shape, dtype=np.complex128)

            generator = BlockedFieldGenerator(
                self.domain,
                zero_block_generator,
                block_size=None,
                max_memory_mb=self.config.max_memory_usage * 1024,
                config=self.config.__dict__ if hasattr(self.config, "__dict__") else {},
                use_cuda=self.cuda_available,
            )
            envelope = generator.get_field()
            self.logger.info(
                "Using BlockedFieldGenerator for envelope initialisation "
                "(domain size %.2f GB, block_size=%s, CUDA=%s)",
                memory_needed_gb,
                generator.block_size,
                generator.use_cuda,
            )
        else:
            if len(self.domain.shape) != 7:
                raise ValueError(
                    f"Expected 7D domain shape for BVP envelope, got {len(self.domain.shape)}D"
                )
            envelope = np.zeros(self.domain.shape, dtype=np.complex128)

        for iteration in range(max_iterations):
            self.logger.info(
                "BVP envelope iteration %s/%s", iteration + 1, max_iterations
            )
            new_envelope = self._solve_envelope_blocks(envelope, source)

            if self._check_envelope_convergence(envelope, new_envelope, tolerance):
                self.logger.info(
                    "BVP envelope converged after %s iterations", iteration + 1
                )
                envelope = new_envelope
                break

            envelope = new_envelope

            if self.config.enable_memory_optimization:
                self._cleanup_memory()

        self.stats["envelope_solves"] += 1
        self.stats["processing_time"] += time.time() - start_time
        self.logger.info("BVP envelope solution completed")
        return envelope

    def _solve_envelope_blocks(
        self, current_envelope: np.ndarray, source: np.ndarray
    ) -> np.ndarray:
        """Solve the envelope equation block-by-block."""
        result = np.zeros_like(current_envelope, dtype=np.complex128)

        for _, block_info in self.block_processor.base_processor.iterate_blocks():
            source_block = self._extract_source_block(source, block_info)
            envelope_block = self._extract_envelope_block(current_envelope, block_info)

            if source_block.shape != envelope_block.shape:
                source_block = self._match_block_shape(source_block, envelope_block.shape)

            block_solution = self.block_solver.solve(
                envelope_block,
                source_block,
                block_info,
                use_cuda=self.cuda_available,
            )

            self._merge_block_result(result, block_solution, block_info)
            self.stats["blocks_processed"] += 1

        return result

    def _match_block_shape(self, block: np.ndarray, target_shape: tuple[int, ...]) -> np.ndarray:
        """Pad or crop a block to match the target shape."""
        src = block
        pad_width = []
        slices = []
        for source_dim, target_dim in zip(src.shape, target_shape):
            if source_dim < target_dim:
                pad_width.append((0, target_dim - source_dim))
                slices.append(slice(0, source_dim))
            elif source_dim > target_dim:
                pad_width.append((0, 0))
                slices.append(slice(0, target_dim))
            else:
                pad_width.append((0, 0))
                slices.append(slice(0, source_dim))

        src_cropped = src[tuple(slices)]
        if any(pad[1] > 0 for pad in pad_width):
            return np.pad(src_cropped, pad_width, mode="constant", constant_values=0)
        return src_cropped

    def _extract_source_block(self, source: np.ndarray, block_info) -> np.ndarray:
        """Extract the portion of the source that corresponds to a block."""
        slices = tuple(
            slice(start, end)
            for start, end in zip(block_info.start_indices, block_info.end_indices)
        )
        return source[slices]

    def _extract_envelope_block(self, envelope: np.ndarray, block_info) -> np.ndarray:
        """Extract the portion of the envelope that corresponds to a block."""
        slices = tuple(
            slice(start, end)
            for start, end in zip(block_info.start_indices, block_info.end_indices)
        )
        return envelope[slices]

    def _merge_block_result(
        self, result: np.ndarray, block_result: np.ndarray, block_info
    ) -> None:
        """Merge a processed block back into the full result array."""
        start_indices = block_info.start_indices
        end_indices = block_info.end_indices
        slices = tuple(slice(start, end) for start, end in zip(start_indices, end_indices))

        if not isinstance(block_result, np.ndarray):
            block_result = np.array(block_result)

        if block_result.ndim == 0:
            expected_shape = tuple(end - start for start, end in zip(start_indices, end_indices))
            block_result = np.full(expected_shape, block_result.item(), dtype=block_result.dtype)

        expected_shape = tuple(end - start for start, end in zip(start_indices, end_indices))
        if block_result.shape != expected_shape:
            if block_result.size == int(np.prod(expected_shape)):
                block_result = block_result.reshape(expected_shape)
            else:
                raise ValueError(
                    f"Block result shape {block_result.shape} does not match expected shape {expected_shape}"
                )

        result[slices] = block_result

    def _check_envelope_convergence(
        self, old_envelope: np.ndarray, new_envelope: np.ndarray, tolerance: float
    ) -> bool:
        """Check convergence between successive envelope iterations."""
        if np.allclose(old_envelope, 0):
            return np.allclose(new_envelope, 0)

        relative_change = np.linalg.norm(new_envelope - old_envelope) / np.linalg.norm(
            old_envelope
        )
        return relative_change < tolerance
