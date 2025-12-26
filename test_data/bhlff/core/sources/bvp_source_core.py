"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP-modulated source core implementation.

This module implements the core BVP-modulated source for the 7D phase field theory,
representing sources that are modulated by the Base High-Frequency Field.

Physical Meaning:
    BVP-modulated sources represent external excitations that are modulated
    by the high-frequency carrier field, creating envelope modulations
    in the source term.

Mathematical Foundation:
    BVP-modulated sources have the form:
    s(x) = s₀(x) * A(x) * exp(iω₀t)
    where s₀(x) is the base source, A(x) is the envelope, and ω₀ is the
    carrier frequency.

Example:
    >>> source = BVPSource(domain, config)
    >>> source_field = source.generate()
"""

import numpy as np
from typing import Dict, Any, Union

from ..domain import Domain
from .source import Source
from .bvp_source_generators import BVPSourceGenerators
from .bvp_source_envelope import BVPSourceEnvelope
from .block_7d_expansion import (
    expand_spatial_to_7d,
    expand_block_to_7d_explicit,
    generate_7d_block_on_device,
)


class BVPSource(Source):
    """
    BVP-modulated source for 7D phase field theory.

    Physical Meaning:
        Implements sources that are modulated by the Base High-Frequency
        Field, creating envelope modulations in the source term that
        drive phase field evolution.

    Mathematical Foundation:
        BVP-modulated sources have the form:
        s(x) = s₀(x) * A(x) * exp(iω₀t)
        where s₀(x) is the base source, A(x) is the envelope, and ω₀ is
        the carrier frequency.

    Attributes:
        domain (Domain): Computational domain.
        config (Dict[str, Any]): BVP source configuration.
        carrier_frequency (float): High-frequency carrier frequency.
        envelope_amplitude (float): Envelope amplitude.
        base_source_type (str): Type of base source.
        source_generators (BVPSourceGenerators): Source generators.
        envelope_generator (BVPSourceEnvelope): Envelope generator.
    """

    def __init__(self, domain: Domain, config: Dict[str, Any]) -> None:
        """
        Initialize BVP-modulated source.

        Physical Meaning:
            Sets up the BVP-modulated source with carrier frequency and
            envelope parameters for generating modulated source terms.

        Args:
            domain (Domain): Computational domain for the source.
            config (Dict[str, Any]): BVP source configuration including:
                - carrier_frequency: High-frequency carrier frequency
                - envelope_amplitude: Envelope amplitude
                - base_source_type: Type of base source
        """
        super().__init__(domain, config)
        self._setup_bvp_parameters()

        # Initialize component generators
        self.source_generators = BVPSourceGenerators(domain, config)
        self.envelope_generator = BVPSourceEnvelope(domain, config)

    def _setup_bvp_parameters(self) -> None:
        """
        Setup BVP source parameters.

        Physical Meaning:
            Initializes the BVP source parameters from configuration
            including carrier frequency and envelope properties.
        """
        self.carrier_frequency = self.config.get("carrier_frequency", 1.85e43)
        self.envelope_amplitude = self.config.get("envelope_amplitude", 1.0)
        self.base_source_type = self.config.get("base_source_type", "gaussian")

    def _expand_block_to_7d(
        self,
        block: np.ndarray,
        N_phi: int,
        N_t: int,
        domain: Domain,
        use_cuda: bool,
    ) -> np.ndarray:
        """
        Expand 3D block to 7D with explicit construction.

        Physical Meaning:
            Expands a 3D spatial block to 7D using explicit construction
            that respects the 7D space-time structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.
            Uses block processing automatically if needed (80% GPU memory limit).

        Args:
            block (np.ndarray): 3D spatial block to expand.
            N_phi (int): Number of grid points per phase dimension.
            N_t (int): Number of grid points for temporal dimension.
            domain (Domain): Domain object with 7D structure information.
            use_cuda (bool): Whether to use CUDA for expansion.

        Returns:
            np.ndarray: Expanded 7D block.
        """
        if block.ndim == 3:
            if use_cuda:
                return generate_7d_block_on_device(
                    block, N_phi=N_phi, N_t=N_t, domain=domain, use_cuda=True
                )
            else:
                return expand_spatial_to_7d(
                    block,
                    N_phi=N_phi,
                    N_t=N_t,
                    use_cuda=False,
                    optimize_block_size=True,
                )
        else:
            return block

    def _combine_blocks(
        self,
        base_block: np.ndarray,
        envelope_block: np.ndarray,
        carrier_block: np.ndarray,
        use_cuda: bool,
    ) -> np.ndarray:
        """
        Combine 7D blocks using vectorized operations.

        Physical Meaning:
            Combines base source, envelope, and carrier components using
            vectorized multiplication that preserves 7D structure.

        Args:
            base_block (np.ndarray): Base source block (3D or 7D).
            envelope_block (np.ndarray): Envelope block (3D or 7D).
            carrier_block (np.ndarray): Carrier block (3D or 7D).
            use_cuda (bool): Whether to use CUDA for combination.

        Returns:
            np.ndarray: Combined modulated block.
        """
        if use_cuda:
            import cupy as cp
            # Move to GPU if needed
            if isinstance(base_block, np.ndarray):
                base_block = cp.asarray(base_block)
            if isinstance(envelope_block, np.ndarray):
                envelope_block = cp.asarray(envelope_block)
            if isinstance(carrier_block, np.ndarray):
                carrier_block = cp.asarray(carrier_block)

            # Vectorized multiplication on GPU (fully parallelized)
            result = base_block * envelope_block * carrier_block
            cp.cuda.Stream.null.synchronize()
            return cp.asnumpy(result)
        else:
            # CPU: vectorized multiplication (NumPy optimized)
            return base_block * envelope_block * carrier_block

    def generate(self, use_blocked: bool = True) -> np.ndarray:
        """
        Generate BVP-modulated source field.

        Physical Meaning:
            Generates the BVP-modulated source field s(x) that represents
            external excitations modulated by the high-frequency carrier.

        Mathematical Foundation:
            Creates the BVP-modulated source:
            s(x) = s₀(x) * A(x) * exp(iω₀t)
            where s₀(x) is the base source, A(x) is the envelope, and
            ω₀ is the carrier frequency.

        Args:
            use_blocked (bool): Whether to use blocked generation for large fields.
                If True and field is large, returns BlockedField for lazy access.

        Returns:
            np.ndarray or BlockedField: BVP-modulated source field.
                For large fields with use_blocked=True, returns BlockedField.
        """
        # Check if field is large enough to require blocking
        total_elements = np.prod(self.domain.shape)
        memory_threshold_elements = (
            1e6  # ~1M elements = ~16MB (lower threshold for safety)
        )

        # Additional safety: always use blocked generation for 7D domains with N >= 32
        # to prevent memory exhaustion even for "small" 7D arrays
        force_blocked = (
            self.domain.dimensions == 7
            and hasattr(self.domain, "N")
            and self.domain.N >= 32
        )

        if use_blocked and (
            total_elements > memory_threshold_elements or force_blocked
        ):
            # Use blocked generation
            from .blocked_field_generator import BlockedFieldGenerator

            def field_block_generator(
                domain: Domain, slice_config: Dict[str, Any], config: Dict[str, Any]
            ) -> np.ndarray:
                """
                Generate field block with explicit 7D construction on device.

                Physical Meaning:
                    Generates only the requested 7D block using explicit construction
                    that respects the 7D space-time structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.
                    Uses block processing and CUDA acceleration with 80% GPU memory
                    limit for optimal performance.

                Mathematical Foundation:
                    Generates BVP-modulated source block:
                    s(x,φ,t) = s₀(x) * A(x) * exp(iω₀t)
                    where components are explicitly expanded to 7D with concrete
                    phase and time extents, generated directly on target device.
                """
                block_shape = tuple(slice_config["shape"])
                block_start = tuple(slice_config["start"])
                use_cuda = config.get("use_cuda", False)

                # Generate only the spatial block needed (3D), not full domain
                # This is the spatial part that will be expanded to 7D explicitly
                spatial_shape = block_shape[:3]
                spatial_start = block_start[:3]

                # Generate only the block we need, not full 3D array
                # Create a minimal domain slice for just this block
                from ..domain import Domain as DomainClass

                block_domain = DomainClass(
                    L=domain.L,
                    N=spatial_shape[0],  # Only block size
                    dimensions=3,
                )

                # Generate base source for this block only
                # Temporarily modify domain to generate only needed block
                original_domain = self.source_generators.domain
                self.source_generators.domain = block_domain
                try:
                    base_source_block = self.source_generators.generate_base_source(
                        self.base_source_type
                    )
                finally:
                    self.source_generators.domain = original_domain

                # Generate envelope for this block only
                original_domain_env = self.envelope_generator.domain
                self.envelope_generator.domain = block_domain
                try:
                    envelope_block = self.envelope_generator.generate_envelope()
                    # Generate carrier for this block only with explicit 7D construction
                    # For 7D domains, carrier will already be 7D from generate_carrier
                    carrier_block = self.envelope_generator.generate_carrier(
                        config.get("time", 0.0), use_cuda=use_cuda
                    )
                finally:
                    self.envelope_generator.domain = original_domain_env

                # Extract phase and time extents from block_shape for explicit 7D expansion
                # (N_x, N_y, N_z) -> (N_x, N_y, N_z, N_φ₁, N_φ₂, N_φ₃, N_t)
                N_phi_block = block_shape[3] if len(block_shape) > 3 else domain.N_phi
                N_t_block = block_shape[6] if len(block_shape) > 6 else domain.N_t

                # Check if we need to expand components to 7D
                is_7d_domain = domain.dimensions == 7

                if is_7d_domain:
                    # Expand 3D components to 7D with explicit construction
                    # Uses block processing automatically if needed (80% GPU memory limit)
                    envelope_block_7d = self._expand_block_to_7d(
                        envelope_block, N_phi_block, N_t_block, domain, use_cuda
                    )
                    carrier_block_7d = self._expand_block_to_7d(
                        carrier_block, N_phi_block, N_t_block, domain, use_cuda
                    )
                    base_source_block_7d = self._expand_block_to_7d(
                        base_source_block, N_phi_block, N_t_block, domain, use_cuda
                    )

                    # Combine 7D components (vectorized operation, fully parallelized)
                    modulated_block_7d = self._combine_blocks(
                        base_source_block_7d,
                        envelope_block_7d,
                        carrier_block_7d,
                        use_cuda,
                    )
                else:
                    # Non-7D domain: combine 3D components directly
                    modulated_block_7d = self._combine_blocks(
                        base_source_block, envelope_block, carrier_block, use_cuda
                    )

                # Verify shape matches expected block_shape and adjust if needed
                if modulated_block_7d.shape != block_shape:
                    # If shape mismatch, adjust to match block_shape using explicit expansion
                    # This handles partial 7D slices correctly
                    modulated_block_7d = expand_block_to_7d_explicit(
                        modulated_block_7d,
                        target_shape=block_shape,
                        block_start=block_start,
                        use_cuda=use_cuda,
                    )

                return modulated_block_7d

            # Create blocked generator
            blocked_generator = BlockedFieldGenerator(
                self.domain,
                field_block_generator,
                config=self.config,
            )

            return blocked_generator.get_field()

        # Generate normally for small fields
        base_source = self.source_generators.generate_base_source(self.base_source_type)

        # Generate BVP-modulated source with explicit 7D construction
        time = self.config.get("time", 0.0)
        use_cuda = self.config.get("use_cuda", False)
        modulated_source = self.envelope_generator.generate_modulated_source(
            base_source, time, use_cuda=use_cuda
        )

        return modulated_source

    def generate_base_source(self) -> np.ndarray:
        """
        Generate base source without modulation.

        Physical Meaning:
            Generates the base source s₀(x) without BVP modulation,
            representing the unmodulated external excitation.

        Returns:
            np.ndarray: Base source field.
        """
        return self.source_generators.generate_base_source(self.base_source_type)

    def generate_envelope(self) -> np.ndarray:
        """
        Generate envelope modulation.

        Physical Meaning:
            Generates the envelope modulation A(x) that modulates the
            base source in the BVP framework.

        Returns:
            np.ndarray: Envelope modulation field.
        """
        return self.envelope_generator.generate_envelope()

    def generate_carrier(self, time: float = 0.0) -> np.ndarray:
        """
        Generate high-frequency carrier.

        Physical Meaning:
            Generates the high-frequency carrier component exp(iω₀t) that
            modulates the source in the BVP framework.

        Args:
            time (float): Time for carrier generation.

        Returns:
            np.ndarray: Carrier component.
        """
        return self.envelope_generator.generate_carrier(time)

    def get_source_type(self) -> str:
        """
        Get the source type.

        Physical Meaning:
            Returns the type of BVP-modulated source being generated.

        Returns:
            str: Source type.
        """
        return f"BVP-modulated {self.base_source_type}"

    def get_carrier_frequency(self) -> float:
        """
        Get the carrier frequency.

        Physical Meaning:
            Returns the high-frequency carrier frequency used in
            BVP modulation.

        Returns:
            float: Carrier frequency.
        """
        return self.carrier_frequency

    def get_envelope_amplitude(self) -> float:
        """
        Get the envelope amplitude.

        Physical Meaning:
            Returns the envelope amplitude used in BVP modulation.

        Returns:
            float: Envelope amplitude.
        """
        return self.envelope_amplitude

    def get_base_source_type(self) -> str:
        """
        Get the base source type.

        Physical Meaning:
            Returns the type of base source being used.

        Returns:
            str: Base source type.
        """
        return self.base_source_type

    def get_supported_source_types(self) -> list:
        """
        Get supported source types.

        Physical Meaning:
            Returns the list of supported base source types for
            BVP modulation.

        Returns:
            list: Supported source types.
        """
        return self.source_generators.get_supported_source_types()

    def get_source_info(self) -> Dict[str, Any]:
        """
        Get source information.

        Physical Meaning:
            Returns comprehensive information about the BVP-modulated
            source including parameters and configuration.

        Returns:
            Dict[str, Any]: Source information.
        """
        return {
            "source_type": self.get_source_type(),
            "base_source_type": self.base_source_type,
            "carrier_frequency": self.carrier_frequency,
            "envelope_amplitude": self.envelope_amplitude,
            "envelope_info": self.envelope_generator.get_envelope_info(),
            "carrier_info": self.envelope_generator.get_carrier_info(),
            "supported_source_types": self.get_supported_source_types(),
        }

    def __repr__(self) -> str:
        """String representation of the BVP-modulated source."""
        return (
            f"BVPSource(domain={self.domain}, "
            f"base_type={self.base_source_type}, "
            f"carrier_frequency={self.carrier_frequency}, "
            f"envelope_amplitude={self.envelope_amplitude})"
        )
