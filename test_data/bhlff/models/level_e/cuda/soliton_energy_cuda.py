"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized energy calculations for soliton models in 7D phase field theory.

This module provides GPU-accelerated energy computation with block processing
and vectorized operations for maximum performance.

Physical Meaning:
    Computes various energy contributions for soliton configurations using
    CUDA acceleration, including kinetic, Skyrme, and WZW energy terms
    with optimized memory usage through block processing.

    Mathematical Foundation:
    Implements GPU-accelerated energy calculations:
    E = ∫[F₂²/2 Tr(L_M L^M) + S₄/4 J₄[U] + S₆/6 J₆[U] + Γ_WZW[U]] dV
    with block-based processing using 80% of GPU memory.

Example:
    >>> energy_calc = SolitonEnergyCalculatorCUDA(domain, physics_params)
    >>> total_energy = energy_calc.compute_total_energy(field)
"""

import numpy as np
from typing import Dict, Any, Optional, TYPE_CHECKING
import logging

try:
    import cupy as cp
    import cupyx.scipy.fft as cp_fft

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None
    cp_fft = None

if TYPE_CHECKING:
    if CUDA_AVAILABLE and cp is not None:
        CpArray = cp.ndarray
    else:
        CpArray = Any
else:
    CpArray = Any

from bhlff.utils.cuda_utils import get_optimal_backend, CUDABackend, CPUBackend
from bhlff.core.domain.cuda_block_processor import CUDABlockProcessor
from .energy.kinetic import KineticEnergyCUDA
from .energy.skyrme import SkyrmeEnergyCUDA
from .energy.wzw import WZWEnergyCUDA
from .energy.blocks import EnergyBlockComputerCUDA


class SolitonEnergyCalculatorCUDA:
    """
    CUDA-optimized energy calculator for soliton models.

    Physical Meaning:
        Computes various energy contributions for soliton configurations
        using GPU acceleration with block processing and vectorization
        for maximum computational efficiency.

    Mathematical Foundation:
        Implements GPU-accelerated energy calculations with block-based
        processing optimized for 80% of available GPU memory.
    """

    def __init__(
        self, domain: "Domain", physics_params: Dict[str, Any], use_cuda: bool = True
    ):
        """
        Initialize CUDA energy calculator.

        Physical Meaning:
            Sets up GPU-accelerated energy computation system with
            automatic memory management and optimized block processing.

        Args:
            domain: Computational domain
            physics_params: Physical parameters including β, μ, λ, S₄, S₆
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

        # Setup energy parameters
        self.S4 = physics_params.get("S4", 0.1)
        self.S6 = physics_params.get("S6", 0.01)
        self.F2 = physics_params.get("F2", 1.0)
        self.N_c = physics_params.get("N_c", 3)

        # Initialize energy term components
        self._kinetic = KineticEnergyCUDA()
        self._skyrme = SkyrmeEnergyCUDA(S4=self.S4)
        self._wzw = WZWEnergyCUDA()
        self._block_computer = EnergyBlockComputerCUDA(
            self._kinetic, self._skyrme, self._wzw
        )

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
            f"Soliton energy calculator initialized: "
            f"CUDA={self.cuda_available}, block_size={self.block_size}"
        )

    def _compute_optimal_block_size(self) -> int:
        """
        Compute optimal block size based on GPU memory (80% of available).

        Physical Meaning:
            Calculates block size to use 80% of available GPU memory,
            ensuring efficient memory usage while avoiding OOM errors.

        Returns:
            int: Optimal block size per dimension.
        """
        if not self.cuda_available:
            return 8  # Default CPU block size

        try:
            # Get GPU memory info
            if isinstance(self.backend, CUDABackend):
                mem_info = self.backend.get_memory_info()
                free_memory_bytes = mem_info["free_memory"]
                # Use 80% of free memory
                available_memory_bytes = int(free_memory_bytes * 0.8)
            else:
                return 8

            # Memory per element (complex128 = 16 bytes)
            bytes_per_element = 16

            # For energy computations, we need space for:
            # - Input field: 1x
            # - Gradients (3 spatial): 3x
            # - Energy densities: 2x (kinetic, potential)
            # - Intermediate results: 2x
            # Total overhead: ~8x
            overhead_factor = 8

            # Maximum elements per block
            max_elements = available_memory_bytes // (
                bytes_per_element * overhead_factor
            )

            # For 7D, calculate block size per dimension
            elements_per_dim = int(max_elements ** (1.0 / 7.0))

            # Ensure reasonable bounds (4 to 128)
            block_size = max(4, min(elements_per_dim, 128))

            self.logger.info(
                f"Optimal block size: {block_size} "
                f"(available GPU memory: {available_memory_bytes / 1e9:.2f} GB, "
                f"using 80%)"
            )

            return block_size

        except Exception as e:
            self.logger.warning(
                f"Failed to compute optimal block size: {e}, using default 8"
            )
            return 8

    def compute_total_energy(self, field: np.ndarray) -> float:
        """
        Compute total energy of soliton configuration using CUDA.

        Physical Meaning:
            Calculates the total energy of the soliton including kinetic,
            Skyrme, and WZW contributions using GPU-accelerated block processing.

        Mathematical Foundation:
            E = ∫[F₂²/2 Tr(L_M L^M) + S₄/4 J₄[U] + S₆/6 J₆[U] + Γ_WZW[U]] dV

        Args:
            field: Soliton field configuration

        Returns:
            Total energy of the configuration
        """
        if self.cuda_available:
            return self._compute_total_energy_cuda(field)
        else:
            return self._compute_total_energy_cpu(field)

    def _compute_total_energy_cuda(self, field: np.ndarray) -> float:
        """Compute total energy using CUDA with block processing."""
        # Transfer to GPU
        field_gpu = self.backend.array(field)

        # Initialize energy accumulator
        total_energy = 0.0

        try:
            # Process in blocks
            if self.block_processor:
                block_id = 0
                for _, block_info in self.block_processor.iterate_blocks_cuda():
                    # Slice the input field by block indices (use provided field, not internal generator)
                    slices = tuple(
                        slice(start, end)
                        for start, end in zip(
                            block_info.start_indices, block_info.end_indices
                        )
                    )
                    block_gpu = field_gpu[slices]
                    block_energy = self._compute_block_energy_cuda(block_gpu)
                    total_energy += float(cp.asnumpy(block_energy))
                    block_id += 1
            else:
                # Process entire field if no block processor
                total_energy = float(
                    cp.asnumpy(self._compute_block_energy_cuda(field_gpu))
                )

        finally:
            # Cleanup GPU memory
            if self.cuda_available:
                cp.get_default_memory_pool().free_all_blocks()

        return total_energy

    def _compute_block_energy_cuda(self, block: CpArray) -> CpArray:
        """Compute energy for a single block on GPU (delegated)."""
        return self._block_computer.compute_block(block)

    def _compute_kinetic_energy_cuda(self, field: CpArray) -> CpArray:
        """Delegate to kinetic energy component."""
        return self._kinetic.compute_cuda(field)

    def _compute_skyrme_energy_cuda(self, field: CpArray) -> CpArray:
        """Delegate to skyrme energy component."""
        return self._skyrme.compute_cuda(field)

    def _compute_wzw_energy_cuda(self, field: CpArray) -> CpArray:
        """Delegate to WZW energy component."""
        return self._wzw.compute_cuda(field)

    def _compute_total_energy_cpu(self, field: np.ndarray) -> float:
        """Fallback CPU computation."""
        # Compute different energy contributions
        kinetic_energy = self._kinetic.compute_cpu(field)
        skyrme_energy = self._skyrme.compute_cpu(field)
        wzw_energy = self._wzw.compute_cpu(field)

        total_energy = kinetic_energy + skyrme_energy + wzw_energy
        return total_energy

    def _compute_kinetic_energy_cpu(self, field: np.ndarray) -> float:
        """
        CPU fallback for kinetic energy.

        Physical Meaning:
            Calculates the kinetic energy contribution from the time
            derivative of the field configuration, representing the
            energy associated with field dynamics.

        Mathematical Foundation:
            T = (1/2)∫|∂U/∂t|² d³x where U is the SU(2) field matrix.
        """
        if field.ndim < 4:
            return 0.0

        # Compute time derivative using finite differences
        dt = 0.01  # Time step
        if field.shape[-1] > 1:
            dU_dt = np.gradient(field, dt, axis=-1)
            # Kinetic energy density: (1/2) * Tr(dU/dt * dU/dt†)
            kinetic_density = 0.5 * np.real(
                np.trace(np.einsum("...ij,...kj->...ik", dU_dt, np.conj(dU_dt)))
            )
            return float(np.sum(kinetic_density))
        return 0.0

    def _compute_skyrme_energy_cpu(self, field: np.ndarray) -> float:
        """
        CPU fallback for Skyrme energy.

        Physical Meaning:
            Calculates the Skyrme energy contribution from the
            quartic terms in the field derivatives, providing
            stability against collapse.

        Mathematical Foundation:
            E_Skyrme = (1/32π²)∫Tr([L_μ, L_ν]²) d³x
            where L_μ = U†∂_μU are the left currents.
        """
        if field.ndim < 4:
            return 0.0

        # Compute spatial derivatives
        dx = 0.1  # Spatial step
        gradients = []
        for i in range(3):  # x, y, z coordinates
            if field.shape[i] > 1:
                grad = np.gradient(field, dx, axis=i)
                gradients.append(grad)
            else:
                gradients.append(np.zeros_like(field))

        # Compute left currents L_μ = U†∂_μU
        L_currents = []
        for grad in gradients:
            # L_μ = U†∂_μU
            L_mu = np.einsum("...ji,...jk->...ik", np.conj(field), grad)
            L_currents.append(L_mu)

        # Compute Skyrme term: Tr([L_μ, L_ν]²)
        skyrme_energy = 0.0
        for i in range(3):
            for j in range(3):
                if i != j:
                    # Commutator [L_i, L_j]
                    commutator = np.einsum(
                        "...ik,...kj->...ij", L_currents[i], L_currents[j]
                    ) - np.einsum("...ik,...kj->...ij", L_currents[j], L_currents[i])
                    # Tr([L_i, L_j]²)
                    skyrme_density = np.real(
                        np.trace(
                            np.einsum("...ik,...kj->...ij", commutator, commutator)
                        )
                    )
                    skyrme_energy += np.sum(skyrme_density)

        return float(skyrme_energy / (32 * np.pi**2))

    def _compute_wzw_energy_cpu(self, field: np.ndarray) -> float:
        """
        CPU fallback for WZW energy.

        Physical Meaning:
            Calculates the Wess-Zumino-Witten energy contribution
            for 7D U(1)^3 phase patterns on VBP substrate that ensures
            baryon number conservation and provides correct quantum statistics.

        Mathematical Foundation:
            For 7D U(1)^3 phase field Θ(x,φ,t) ∈ T^3_φ:
            E_WZW = (1/8π²)∫_T³_φ dφ₁dφ₂dφ₃ ∇_φ·Θ(x,φ) for topological charge
            The classical SU(2) form is a 4D pedagogical limit.
        """
        if field.ndim < 7:
            return 0.0

        # For 7D U(1)^3 phase field, compute WZW energy via phase winding
        # E_WZW = (1/8π²)∫_T³_φ dφ₁dφ₂dφ₃ ∇_φ·Θ(x,φ)

        # Extract phase coordinates (last 3 dimensions are φ-coordinates)
        if field.shape[-3:] != (8, 8, 8):  # Assuming 8x8x8 φ-grid
            return 0.0

        # Compute phase gradients along φ-coordinates
        dphi = 2 * np.pi / 8  # Phase coordinate spacing
        phase_gradients = []

        for i in range(3):
            # Gradient along φ_i coordinate
            grad = np.gradient(field, dphi, axis=-(3 - i))
            phase_gradients.append(grad)

        # Compute WZW energy via U(1)^3 phase winding
        # E_WZW = (1/8π²)∫_T³_φ dφ₁dφ₂dφ₃ ∇_φ·Θ(x,φ)
        wzw_energy = 0.0

        # Integrate over φ-coordinates
        for i in range(8):
            for j in range(8):
                for k in range(8):
                    # Compute divergence of phase field at (i,j,k)
                    div_phase = 0.0
                    for alpha in range(3):
                        div_phase += phase_gradients[alpha][..., i, j, k]

                    # Add to WZW energy
                    wzw_energy += div_phase * (dphi**3)

        # Normalize by 8π²
        wzw_energy /= 8 * np.pi**2

        return float(np.real(wzw_energy))
