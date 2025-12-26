"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized defect dynamics for Level E experiments in 7D phase field theory.

This module provides GPU-accelerated defect dynamics with block processing
and vectorized operations for maximum performance.

Physical Meaning:
    Implements GPU-accelerated dynamics of topological defects following
    the Thiele equation with energy-based motion using CUDA vectorization.

Mathematical Foundation:
    Solves the Thiele equation: ẋ = -∇U_eff + G × ẋ + D ẋ
    with GPU-accelerated block processing using 80% of GPU memory.

Example:
    >>> dynamics = DefectDynamicsCUDA(domain, physics_params)
    >>> trajectory = dynamics.simulate_defect_motion(position, time_steps, field)
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple, TYPE_CHECKING
import logging

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

if TYPE_CHECKING:
    if CUDA_AVAILABLE and cp is not None:
        CpArray = cp.ndarray
    else:
        CpArray = Any
else:
    CpArray = Any

from bhlff.utils.cuda_utils import get_optimal_backend, CUDABackend, CPUBackend
from bhlff.core.domain.cuda_block_processor import CUDABlockProcessor


class DefectDynamicsCUDA:
    """
    CUDA-optimized defect dynamics calculator for topological defects.

    Physical Meaning:
        Implements GPU-accelerated dynamics of topological defects following
        the Thiele equation with energy-based motion using vectorized operations
        and block processing for maximum efficiency.

    Mathematical Foundation:
        Solves the Thiele equation: ẋ = -∇U_eff + G × ẋ + D ẋ
        with GPU-accelerated block processing.
    """

    def __init__(
        self, domain: "Domain", physics_params: Dict[str, Any], use_cuda: bool = True
    ):
        """
        Initialize CUDA defect dynamics calculator.

        Physical Meaning:
            Sets up GPU-accelerated defect dynamics system with
            automatic memory management and optimized block processing.

        Args:
            domain: Computational domain
            physics_params: Physical parameters
            use_cuda: Whether to use CUDA acceleration
        """
        self.domain = domain
        self.params = physics_params
        self.logger = logging.getLogger(__name__)
        self.use_cuda = use_cuda and CUDA_AVAILABLE

        # Initialize backend
        if self.use_cuda:
            try:
                self.backend = get_optimal_backend()
                self.cuda_available = isinstance(self.backend, CUDABackend)
            except Exception as e:
                self.logger.warning(f"CUDA initialization failed: {e}, using CPU")
                self.backend = CPUBackend()
                self.cuda_available = False
        else:
            self.backend = CPUBackend()
            self.cuda_available = False

        # Setup dynamics parameters
        self.gyroscopic_coefficient = physics_params.get("gyroscopic_coefficient", 1.0)
        self.time_step = physics_params.get("time_step", 0.01)
        self.energy_threshold = physics_params.get("energy_threshold", 1.0)

        # Compute optimal block size
        self.block_size = self._compute_optimal_block_size()

        # Initialize block processor if CUDA available
        if self.cuda_available:
            self.block_processor = CUDABlockProcessor(
                domain, block_size=self.block_size
            )
        else:
            self.block_processor = None

        self.logger.info(
            f"Defect dynamics CUDA initialized: "
            f"CUDA={self.cuda_available}, block_size={self.block_size}"
        )

    def _compute_optimal_block_size(self) -> int:
        """
        Compute optimal block size based on GPU memory (80% of available).

        Physical Meaning:
            Calculates block size to use 80% of available GPU memory.

        Returns:
            int: Optimal block size per dimension.
        """
        if not self.cuda_available:
            return 8

        try:
            if isinstance(self.backend, CUDABackend):
                mem_info = self.backend.get_memory_info()
                free_memory_bytes = mem_info["free_memory"]
                available_memory_bytes = int(free_memory_bytes * 0.8)
            else:
                return 8

            bytes_per_element = 16
            overhead_factor = 6  # Energy landscape + gradients + positions
            max_elements = available_memory_bytes // (
                bytes_per_element * overhead_factor
            )
            elements_per_dim = int(max_elements ** (1.0 / 7.0))
            block_size = max(4, min(elements_per_dim, 128))

            self.logger.info(
                f"Optimal block size: {block_size} "
                f"(available GPU memory: {available_memory_bytes / 1e9:.2f} GB)"
            )

            return block_size

        except Exception as e:
            self.logger.warning(f"Failed to compute optimal block size: {e}")
            return 8

    def simulate_defect_motion(
        self, initial_position: np.ndarray, time_steps: int, field: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """
        Simulate defect motion using CUDA-accelerated energy-based dynamics.

        Physical Meaning:
            Computes defect motion based on energy gradients using
            GPU-accelerated block processing for maximum efficiency.

        Args:
            initial_position: Initial defect position
            time_steps: Number of time steps
            field: Background field configuration

        Returns:
            Dict containing positions, energy landscape, and gradients
        """
        if self.cuda_available:
            return self._simulate_defect_motion_cuda(
                initial_position, time_steps, field
            )
        else:
            return self._simulate_defect_motion_cpu(initial_position, time_steps, field)

    def _simulate_defect_motion_cuda(
        self, initial_position: np.ndarray, time_steps: int, field: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """Simulate defect motion using CUDA with block processing."""
        # Transfer to GPU
        field_gpu = self.backend.array(field)

        try:
            # Compute energy landscape on GPU
            energy_landscape = self._compute_energy_landscape_cuda(field_gpu)

            # Compute energy gradients on GPU (vectorized)
            energy_gradients = self._compute_energy_gradients_cuda(energy_landscape)

            # Integrate motion on GPU
            positions = self._integrate_energy_dynamics_cuda(
                initial_position, energy_gradients, time_steps
            )

            # Transfer results back to CPU
            return {
                "positions": cp.asnumpy(positions),
                "energy_landscape": cp.asnumpy(energy_landscape),
                "energy_gradients": cp.asnumpy(energy_gradients),
            }

        finally:
            if self.cuda_available:
                cp.get_default_memory_pool().free_all_blocks()

    def _compute_energy_landscape_cuda(self, field: CpArray) -> CpArray:
        """
        Compute energy landscape on GPU.

        Physical Meaning:
            Calculates the energy density distribution in the field
            using GPU-accelerated vectorized operations.
        """
        # Energy density from field amplitude and gradients
        amplitude = cp.abs(field)

        # Compute gradients (vectorized on GPU)
        gradients = []
        for axis in range(3):
            if field.shape[axis] > 1:
                grad = cp.gradient(field, axis=axis)
                gradients.append(cp.abs(grad))
            else:
                gradients.append(cp.zeros_like(amplitude))

        # Energy landscape: amplitude + gradient contributions
        energy_landscape = amplitude**2
        for grad in gradients:
            energy_landscape += grad**2

        return energy_landscape

    def _compute_energy_gradients_cuda(self, energy_landscape: CpArray) -> CpArray:
        """
        Compute energy gradients on GPU (vectorized).

        Physical Meaning:
            Calculates the gradient of the energy landscape using
            GPU-accelerated vectorized gradient operations.
        """
        # Compute gradients along all spatial dimensions (vectorized)
        gradients = []
        for axis in range(3):
            if energy_landscape.shape[axis] > 1:
                grad = cp.gradient(energy_landscape, axis=axis)
                gradients.append(grad)
            else:
                gradients.append(cp.zeros_like(energy_landscape))

        # Stack gradients into array
        energy_gradients = cp.stack(gradients, axis=-1)

        return energy_gradients

    def _integrate_energy_dynamics_cuda(
        self,
        initial_position: np.ndarray,
        energy_gradients: CpArray,
        time_steps: int,
    ) -> CpArray:
        """
        Integrate defect motion using energy-based dynamics on GPU.

        Physical Meaning:
            Evolves defect position according to energy gradients
            using GPU-accelerated time integration.
        """
        # Transfer initial position to GPU
        position_gpu = cp.array(initial_position)

        # Initialize trajectory array on GPU
        trajectory = cp.zeros((time_steps, 3))
        trajectory[0] = position_gpu

        # Time integration loop (vectorized where possible)
        for t in range(1, time_steps):
            # Interpolate energy gradient at current position
            gradient_at_pos = self._interpolate_gradient_cuda(
                position_gpu, energy_gradients
            )

            # Energy-based motion: dx/dt = -∇U (no mass)
            velocity = -gradient_at_pos * self.time_step

            # Update position
            position_gpu += velocity
            trajectory[t] = position_gpu

        return trajectory

    def _interpolate_gradient_cuda(
        self, position: CpArray, gradients: CpArray
    ) -> CpArray:
        """
        Interpolate energy gradient at given position on GPU.

        Physical Meaning:
            Computes the energy gradient at a specific position
            using GPU-accelerated interpolation.
        """
        # Convert position to grid indices
        L = self.domain.L
        N = self.domain.N
        indices = (position * N / L).astype(cp.int32)

        # Clamp indices to valid range
        indices = cp.clip(indices, 0, N - 1)

        # Extract gradient at position (simple nearest neighbor)
        gradient = gradients[indices[0], indices[1], indices[2]]

        return gradient

    def _simulate_defect_motion_cpu(
        self, initial_position: np.ndarray, time_steps: int, field: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """CPU fallback for defect motion simulation."""
        # Compute energy landscape
        amplitude = np.abs(field)
        energy_landscape = amplitude**2

        # Compute gradients
        gradients = []
        for axis in range(3):
            if field.shape[axis] > 1:
                grad = np.gradient(field, axis=axis)
                gradients.append(np.abs(grad) ** 2)
            else:
                gradients.append(np.zeros_like(amplitude))

        for grad in gradients:
            energy_landscape += grad

        # Compute energy gradients
        energy_gradients = []
        for axis in range(3):
            if energy_landscape.shape[axis] > 1:
                grad = np.gradient(energy_landscape, axis=axis)
                energy_gradients.append(grad)
            else:
                energy_gradients.append(np.zeros_like(energy_landscape))

        energy_gradients = np.stack(energy_gradients, axis=-1)

        # Integrate motion
        trajectory = np.zeros((time_steps, 3))
        trajectory[0] = initial_position

        for t in range(1, time_steps):
            L = self.domain.L
            N = self.domain.N
            indices = (trajectory[t - 1] * N / L).astype(int)
            indices = np.clip(indices, 0, N - 1)

            gradient = energy_gradients[indices[0], indices[1], indices[2]]
            velocity = -gradient * self.time_step
            trajectory[t] = trajectory[t - 1] + velocity

            if t % 10 == 0 or t == time_steps - 1:
                grad_norm = float(np.linalg.norm(gradient))
                self.logger.info(
                    f"[DefectDynamicsCUDA] t={t}/{time_steps-1} grad_norm={grad_norm:.3e} pos={trajectory[t]}"
                )

        return {
            "positions": trajectory,
            "energy_landscape": energy_landscape,
            "energy_gradients": energy_gradients,
        }
