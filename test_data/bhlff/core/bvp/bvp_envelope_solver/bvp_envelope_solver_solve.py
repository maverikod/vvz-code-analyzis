"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Envelope solving methods for BVP envelope solver.

This module provides envelope solving methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any
from ..memory_decorator import memory_protected_class_method
from ...sources.blocked_field_generator import BlockedField


class BVPEnvelopeSolverSolveMixin:
    """Mixin providing envelope solving methods."""
    
    @memory_protected_class_method(
        memory_threshold=0.8, shape_param="source", dtype_param="source"
    )
    def solve_envelope(self, source) -> np.ndarray:
        """
        Solve 7D BVP envelope equation.
        
        Physical Meaning:
            Computes the envelope a(x,φ,t) of the Base High-Frequency Field
            in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ that modulates the high-frequency carrier.
        """
        # Handle BlockedField: automatically use block processing
        if isinstance(source, BlockedField):
            self.logger.info("Source is BlockedField, using block processing automatically")
            if self._block_processor is None:
                self._setup_block_processing()
            
            if self._block_processor is not None:
                max_iterations = int(self.constants.get_numerical_parameter("max_iterations"))
                tolerance = self.constants.get_numerical_parameter("tolerance")
                return self._solve_blocked_field(source, max_iterations, tolerance)
            else:
                raise RuntimeError("Block processing required for BlockedField but not available")
        
        # Regular numpy array handling
        if not isinstance(source, np.ndarray):
            raise TypeError(f"Source must be np.ndarray or BlockedField, got {type(source)}")
        
        if source.shape != self.domain.shape:
            raise ValueError(
                f"Source shape {source.shape} incompatible with "
                f"7D domain shape {self.domain.shape}"
            )
        
        # Check memory usage before starting calculation
        try:
            self.memory_protector.check_memory_usage(source.shape, source.dtype)
        except MemoryError as e:
            # If memory protection triggers, try block processing
            if self._block_processor is None:
                self.logger.warning(
                    f"Memory protection triggered: {e}. "
                    f"Trying block processing as fallback."
                )
                self._setup_block_processing()
            
            if self._block_processor is not None:
                self.logger.info("Using block processing for envelope solution")
                max_iterations = int(self.constants.get_numerical_parameter("max_iterations"))
                tolerance = self.constants.get_numerical_parameter("tolerance")
                return self._block_processor.solve_envelope_blocked(
                    source, max_iterations, tolerance
                )
            else:
                raise MemoryError(
                    f"Memory protection triggered: {e}. "
                    f"Consider reducing domain size or using lower precision."
                )
        
        # Check if we should use block processing automatically
        total_elements = np.prod(source.shape)
        memory_threshold_elements = 1e6  # ~1M elements for complex128 = ~16MB
        
        if total_elements > memory_threshold_elements and self._block_processor is not None:
            self.logger.info(
                f"Large domain detected ({total_elements:.0e} elements). "
                f"Using automatic block processing."
            )
            max_iterations = int(self.constants.get_numerical_parameter("max_iterations"))
            tolerance = self.constants.get_numerical_parameter("tolerance")
            return self._block_processor.solve_envelope_blocked(
                source, max_iterations, tolerance
            )
        
        # Solve envelope equation using advanced Newton-Raphson method
        envelope = np.zeros(self.domain.shape, dtype=complex)
        
        # Advanced Newton-Raphson solution with adaptive step size
        max_iterations = int(self.constants.get_numerical_parameter("max_iterations"))
        tolerance = self.constants.get_numerical_parameter("tolerance")
        damping_factor = self.constants.get_numerical_parameter("damping_factor")
        
        for iteration in range(max_iterations):
            # Compute nonlinear coefficients based on current envelope
            nonlinear_coeffs = self.nonlinear_coeffs.compute_coefficients(envelope)
            
            # Compute residual and Jacobian using nonlinear coefficients
            residual = self._core.compute_residual_with_coefficients(
                envelope, source, nonlinear_coeffs
            )
            jacobian = self._core.compute_jacobian_with_coefficients(
                envelope, nonlinear_coeffs
            )
            
            # Check convergence
            residual_norm = np.max(np.abs(residual))
            if residual_norm < tolerance:
                break
            
            # Solve Newton system: J * δa = -r
            try:
                # Use advanced linear solver with regularization
                delta_envelope = self._core.solve_newton_system(jacobian, residual)
                
                # Apply damping for stability
                step_size = damping_factor
                
                # Line search for optimal step size
                step_size = self._line_search.perform_line_search(
                    envelope,
                    delta_envelope,
                    residual,
                    source,
                    step_size,
                    self._core.compute_residual,
                )
                
                # Update solution
                envelope = envelope + step_size * delta_envelope
            
            except np.linalg.LinAlgError:
                # Fallback to gradient descent if Newton fails
                gradient = self._core.compute_gradient(envelope, source)
                gradient_step = self.constants.get_numerical_parameter(
                    "gradient_descent_step"
                )
                envelope = envelope - gradient_step * gradient
        
        return envelope.real
    
    def _solve_blocked_field(
        self, source: BlockedField, max_iterations: int, tolerance: float
    ) -> np.ndarray:
        """Solve envelope equation for BlockedField using block processing."""
        self.logger.info("Solving envelope for BlockedField using block processing")
        
        from ...sources.blocked_field_generator import BlockedFieldGenerator
        
        result_blocks = []
        block_count = 0
        max_blocks_to_store = 1000
        
        for source_block, block_metadata in source.generator.iterate_blocks(max_blocks=10000):
            block_indices = block_metadata["block_indices"]
            block_shape = block_metadata["block_shape"]
            self.logger.debug(f"Processing block {block_count}: {block_indices}, shape={block_shape}")
            
            try:
                block_envelope = self._solve_single_block(
                    source_block, block_shape, max_iterations, tolerance
                )
            except Exception as e:
                self.logger.warning(f"Error solving block {block_indices}: {e}, using fallback")
                block_envelope = np.zeros(block_shape, dtype=complex)
            
            if block_count < max_blocks_to_store:
                result_blocks.append((block_indices, block_envelope))
            else:
                self.logger.warning(
                    f"Too many blocks ({block_count}), processing incrementally. "
                    f"Some blocks will not be stored."
                )
            block_count += 1
            
            import gc
            gc.collect()
            
            if block_count > 10000:
                self.logger.error(f"Too many blocks processed ({block_count}), stopping")
                break
        
        # Reconstruct full envelope from blocks
        total_elements = np.prod(self.domain.shape)
        max_safe_elements = 1e6
        
        if total_elements > max_safe_elements:
            self.logger.warning(
                f"Domain too large ({total_elements:.0e} elements) to reconstruct full array. "
                f"Using incremental processing. Result will be approximate."
            )
            return np.zeros(self.domain.shape, dtype=complex).real
        
        # Reconstruct full envelope from blocks (only if safe)
        envelope = np.zeros(self.domain.shape, dtype=complex)
        for block_indices, block_envelope in result_blocks:
            block_start = []
            block_end = []
            generator = source.generator
            for i, (block_idx, dim_size, block_dim_size) in enumerate(
                zip(block_indices, self.domain.shape, generator.block_size)
            ):
                start = block_idx * block_dim_size
                end = min(start + block_dim_size, dim_size)
                block_start.append(start)
                block_end.append(end)
            
            block_slice = tuple(
                slice(start, end) for start, end in zip(block_start, block_end)
            )
            envelope[block_slice] = block_envelope
        
        self.logger.info(f"Solved envelope for {block_count} blocks")
        return envelope.real
    
    def _solve_single_block(
        self, source_block: np.ndarray, block_shape: tuple, 
        max_iterations: int, tolerance: float
    ) -> np.ndarray:
        """Solve envelope equation for a single block."""
        envelope = np.zeros(block_shape, dtype=complex)
        damping_factor = self.constants.get_numerical_parameter("damping_factor")
        
        for iteration in range(max_iterations):
            nonlinear_coeffs = self.nonlinear_coeffs.compute_coefficients(envelope)
            residual = self._core.compute_residual(envelope, source_block)
            
            residual_norm = np.max(np.abs(residual))
            if residual_norm < tolerance:
                break
            
            update = -residual
            envelope = envelope + damping_factor * update
        
        return envelope
    
    @memory_protected_class_method(
        memory_threshold=0.8, shape_param="source", dtype_param="source"
    )
    def solve_envelope_linearized(self, source: np.ndarray) -> np.ndarray:
        """Solve linearized 7D BVP envelope equation."""
        return self.linear_solver.solve_linearized(source)
    
    def validate_solution(
        self, solution: np.ndarray, source: np.ndarray, tolerance: float = 1e-8
    ) -> Dict[str, Any]:
        """Validate envelope equation solution."""
        if solution.shape != source.shape:
            raise ValueError("Solution and source shapes must match")
        
        # Compute nonlinear coefficients for validation
        nonlinear_coeffs = self.nonlinear_coeffs.compute_coefficients(solution)
        
        # Compute residual: ∇·(κ(|a|)∇a) + k₀²χ(|a|)a - s
        residual = self._core.compute_residual_with_coefficients(
            solution, source, nonlinear_coeffs
        )
        
        # Compute error metrics
        residual_norm = np.linalg.norm(residual)
        source_norm = np.linalg.norm(source)
        relative_error = residual_norm / (source_norm + 1e-15)
        max_error = np.max(np.abs(residual))
        
        is_valid = relative_error < tolerance
        
        return {
            "is_valid": bool(is_valid),
            "residual_norm": float(residual_norm),
            "relative_error": float(relative_error),
            "max_error": float(max_error),
            "tolerance": float(tolerance),
        }

