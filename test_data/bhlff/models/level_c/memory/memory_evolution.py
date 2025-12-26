"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Memory evolution analysis module.

This module implements memory evolution analysis functionality
for Level C test C3 in 7D phase field theory.

Physical Meaning:
    Analyzes the evolution of fields with memory effects,
    including memory kernel application and quench detection.

Example:
    >>> analyzer = MemoryEvolutionAnalyzer(bvp_core)
    >>> results = analyzer.evolve_with_memory(domain, memory, time_params)
"""

import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import logging

from bhlff.core.bvp import BVPCore
from .data_structures import MemoryParameters, QuenchEvent, MemoryKernel, MemoryState
from .spatial_field_extractor import SpatialFieldExtractor
from .memory_kernel_processor import MemoryKernelProcessor
from .memory_effects_analyzer import MemoryEffectsAnalyzer
from .initial_field_generator_cuda import InitialFieldGeneratorCUDA


class MemoryEvolutionAnalyzer:
    """
    Memory evolution analysis for Level C test C3.

    Physical Meaning:
        Analyzes the evolution of fields with memory effects,
        including memory kernel application and quench detection.

    Mathematical Foundation:
        Implements memory evolution analysis:
        - Memory kernel analysis: K(t) = (1/τ) * Θ(t_cutoff - t)  # Step resonator
        - Memory term: Γ_memory[a] = -γ ∫_0^t K(t-τ) a(τ) dτ
        - Field evolution: ∂a/∂t = L[a] + Γ_memory[a] + s(x,t)
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize memory evolution analyzer.

        Args:
            bvp_core (BVPCore): BVP core framework instance.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)
        self.spatial_extractor = SpatialFieldExtractor()
        self.kernel_processor = MemoryKernelProcessor()
        self.effects_analyzer = MemoryEffectsAnalyzer()
        self.initial_field_generator = InitialFieldGeneratorCUDA(self.spatial_extractor)

    def evolve_with_memory(
        self,
        domain: Dict[str, Any],
        memory: MemoryParameters,
        time_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evolve field with memory effects.

        Physical Meaning:
            Performs time evolution of the field with memory effects,
            including memory kernel application and quench detection.

        Mathematical Foundation:
            ∂a/∂t = L[a] + Γ_memory[a] + s(x,t)
            where Γ_memory[a] = -γ ∫_0^t K(t-τ) a(τ) dτ

        Args:
            domain (Dict[str, Any]): Domain parameters.
            memory (MemoryParameters): Memory parameters.
            time_params (Dict[str, Any]): Time evolution parameters.

        Returns:
            Dict[str, Any]: Memory evolution results.
        """
        # Extract time parameters
        dt = time_params.get("dt", 0.005)
        T = time_params.get("T", 400.0)
        time_points = np.arange(0, T, dt)

        # Create initial field
        field = self._create_initial_field(domain)
        field_history = [field.copy()]

        # Create memory kernel
        memory_kernel = self.kernel_processor.create_memory_kernel(memory)

        # Time evolution
        for t in time_points[1:]:
            # Apply memory term
            memory_term = self.kernel_processor.apply_memory_term(
                field_history, memory_kernel, memory
            )

            # Apply evolution operator
            field = self._apply_evolution_operator(field, memory_term, dt)

            # Detect quench events
            quench_events = self._detect_quench_events(field, t)

            # Update field history
            field_history.append(field.copy())

        # Analyze memory effects
        memory_analysis = self.effects_analyzer.analyze_memory_effects(
            field_history, memory
        )

        return {
            "field_evolution": field_history,
            "memory_analysis": memory_analysis,
            "quench_events": self._collect_quench_events(field_history),
            "evolution_complete": True,
        }

    def _create_initial_field(self, domain: Dict[str, Any]) -> np.ndarray:
        """
        Create initial field configuration with block-based processing.

        Physical Meaning:
            Creates an initial field configuration for memory evolution analysis
            using block-based processing with CUDA acceleration when field size
            exceeds memory limits. Extracts 3D spatial field from 7D BlockedField
            by averaging over phase and temporal dimensions (indices 3,4,5,6) per block
            using vectorized operations. Iterates via generator with capped max_blocks
            for memory safety. Preserves 7D-to-3D semantics with proper broadcasting.

        Mathematical Foundation:
            For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
            - Field: a(x, y, z, φ₁, φ₂, φ₃, t)
            - 3D extraction per block: a_3d(x, y, z) = ⟨|a(x, y, z, φ₁, φ₂, φ₃, t)|⟩_{φ₁,φ₂,φ₃,t}
            - Block processing: processes blocks preserving 7D structure using generator
            - CUDA acceleration: uses 80% GPU memory limit with vectorized operations
            - Generator iteration: uses max_blocks limit for memory safety

        Args:
            domain (Dict[str, Any]): Domain parameters.

        Returns:
            np.ndarray: Initial 3D field configuration (N, N, N).
        """
        # Extract domain parameters
        N = domain.get("N", 64)
        L = domain.get("L", 1.0)

        # Use block-based processing for large fields
        if N**3 > 64**3:  # Threshold for block processing
            return self._create_blocked_initial_field(domain, N, L)

        # Create small field directly (fallback for small domains)
        return self.initial_field_generator._create_small_field(N, L)

    def _create_blocked_initial_field(
        self, domain: Dict[str, Any], N: int, L: float
    ) -> np.ndarray:
        """
        Create initial field from 7D BlockedField using block-based processing.

        Physical Meaning:
            Creates 7D blocked field and extracts 3D spatial field by averaging
            over phase and temporal dimensions per block. Iterates via generator
            with capped max_blocks for memory safety. Uses CUDA acceleration with
            80% GPU memory limit and vectorized operations.

        Mathematical Foundation:
            For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
            - Creates 7D BlockedField using BlockedFieldGenerator
            - Iterates blocks via generator.iterate_blocks(max_blocks)
            - Extracts 3D per block: a_3d(x, y, z) = ⟨|a(x, y, z, φ₁, φ₂, φ₃, t)|⟩_{φ₁,φ₂,φ₃,t}
            - Combines blocks into full 3D field using vectorized operations
            - CUDA optimization: respects 80% GPU memory limit

        Args:
            domain (Dict[str, Any]): Domain parameters.
            N (int): Domain size (N×N×N).
            L (float): Domain length.

        Returns:
            np.ndarray: Initial 3D field configuration (N, N, N).
        """
        from bhlff.core.sources.blocked_field_generator import (
            BlockedFieldGenerator,
            BlockedField,
        )
        from bhlff.core.domain import Domain as DomainClass

        # Create 7D domain object (required for 7D BlockedField)
        # Level C works with 3D spatial fields, but BlockedField requires 7D
        domain_obj = DomainClass(L=L, N=N, N_phi=4, N_t=8, T=1.0, dimensions=7)

        # Create field generator function with CUDA support
        field_generator = self.initial_field_generator._create_field_generator_function()

        # Use BlockedFieldGenerator with CUDA support
        generator = BlockedFieldGenerator(
            domain_obj, field_generator, use_cuda=self.initial_field_generator.cuda_available
        )
        blocked_field = generator.get_field()

        # Process blocked field using generator with max_blocks limit
        if isinstance(blocked_field, BlockedField):
            from .blocked_field_processor_cuda import BlockedFieldProcessorCUDA

            processor = BlockedFieldProcessorCUDA(self.spatial_extractor)
            return processor.process_blocked_field_blocks(
                blocked_field, generator, N, self.initial_field_generator.cuda_available
            )
        else:
            # Fallback: if not BlockedField, try direct extraction
            if hasattr(blocked_field, "shape") and len(blocked_field.shape) == 7:
                return self.spatial_extractor.extract_spatial_from_7d_block(
                    blocked_field, self.initial_field_generator.cuda_available
                )
            else:
                # If already 3D or different shape, use absolute value
                return (
                    np.abs(blocked_field)
                    if isinstance(blocked_field, np.ndarray)
                    else np.array(blocked_field)
                )

    def _apply_evolution_operator(
        self, field: np.ndarray, memory_term: np.ndarray, dt: float
    ) -> np.ndarray:
        """
        Apply evolution operator to field.

        Physical Meaning:
            Applies the evolution operator to the field,
            including memory effects.

        Mathematical Foundation:
            Applies the evolution operator:
            ∂a/∂t = L[a] + Γ_memory[a] + s(x,t)
            where L is the linear operator and Γ_memory is the memory term.

        Args:
            field (np.ndarray): Current field configuration.
            memory_term (np.ndarray): Memory term contribution.
            dt (float): Time step.

        Returns:
            np.ndarray: Evolved field configuration.
        """
        # Apply BVP evolution
        evolved_field = self.bvp_core.evolve_field(field, dt)

        # Add memory term
        evolved_field += memory_term * dt

        return evolved_field

    def _detect_quench_events(self, field: np.ndarray, t: float) -> List[QuenchEvent]:
        """
        Detect quench events in field.

        Physical Meaning:
            Detects quench events in the field evolution,
            including thermal and non-thermal quenches.

        Args:
            field (np.ndarray): Current field configuration.
            t (float): Current time.

        Returns:
            List[QuenchEvent]: Detected quench events.
        """
        quench_events = []

        # Simplified quench detection
        # In practice, this would involve proper quench analysis
        field_intensity = np.mean(np.abs(field))
        if field_intensity > 0.5:  # Threshold for quench detection
            quench_event = QuenchEvent(
                timestamp=t,
                intensity=field_intensity,
                spatial_position=np.array([0.0, 0.0, 0.0]),
                event_type="thermal",
            )
            quench_events.append(quench_event)

        return quench_events


    def _collect_quench_events(
        self, field_history: List[np.ndarray]
    ) -> List[QuenchEvent]:
        """
        Collect all quench events from field history.

        Physical Meaning:
            Collects all quench events detected during
            the field evolution.

        Args:
            field_history (List[np.ndarray]): History of field evolution.

        Returns:
            List[QuenchEvent]: All detected quench events.
        """
        quench_events = []

        for i, field in enumerate(field_history):
            field_intensity = np.mean(np.abs(field))
            if field_intensity > 0.5:  # Threshold for quench detection
                quench_event = QuenchEvent(
                    timestamp=float(i),
                    intensity=field_intensity,
                    spatial_position=np.array([0.0, 0.0, 0.0]),
                    event_type="thermal",
                )
                quench_events.append(quench_event)

        return quench_events

