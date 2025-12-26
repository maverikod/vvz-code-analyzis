"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Phase components setup methods.
"""

import numpy as np
from typing import Dict, Any, List
import logging

from bhlff.core.domain import Domain


class PhaseComponentsSetup:
    """
    Phase components setup methods.

    Physical Meaning:
        Provides methods to setup the three U(1) phase components
        using direct or blocked initialization.
    """

    def __init__(self, domain: Domain, config: Dict[str, Any]):
        """
        Initialize setup manager.

        Args:
            domain (Domain): Computational domain.
            config (Dict[str, Any]): Phase components configuration.
        """
        self.domain = domain
        self.config = config
        self.theta_components: List[np.ndarray] = []
        self.logger = logging.getLogger(__name__)

    def setup_phase_components(self) -> None:
        """
        Setup the three U(1) phase components Θ_a (a=1..3).

        Physical Meaning:
            Initializes the three independent U(1) phase components
            that form the U(1)³ structure of the BVP field.
            Uses block processing for large domains to avoid memory issues.
        """
        # Get phase configuration
        phase_config = self.config.get("phase_components", {})

        # Check if we need block processing
        total_elements = np.prod(self.domain.shape)
        memory_needed_gb = (total_elements * 16) / (1024**3)  # complex128 = 16 bytes
        
        use_block_processing = memory_needed_gb > 1.0
        
        if use_block_processing:
            self.logger.info(
                f"Using block processing for phase components "
                f"(domain size: {memory_needed_gb:.2f} GB)"
            )
            # Use block-based initialization
            self._setup_phase_components_blocked(phase_config)
        else:
            # Use direct initialization for small domains
            self._setup_phase_components_direct(phase_config)

    def _setup_phase_components_direct(self, phase_config: Dict[str, Any]) -> None:
        """Setup phase components directly for small domains."""
        for a in range(3):  # Three U(1) components
            # Initialize phase component Θ_a
            theta_a = np.zeros(self.domain.shape, dtype=complex)

            # Set amplitude and frequency for this component
            amplitude = phase_config.get(f"amplitude_{a+1}", 1.0)
            frequency = phase_config.get(f"frequency_{a+1}", 1.0)

            # Create spatial phase distribution for 7D structure
            if self.domain.dimensions == 7:
                # 7D structure: ℝ³ₓ × 𝕋³_φ × ℝₜ
                # Use domain shape for proper 7D structure
                theta_a = np.zeros(self.domain.shape, dtype=complex)

                # Create simple 7D phase distribution
                # For testing purposes, create a simple phase pattern
                indices = np.indices(self.domain.shape)
                phase_sum = np.sum(indices, axis=0)
                theta_a = amplitude * np.exp(
                    1j * frequency * phase_sum / np.max(phase_sum)
                )
            elif self.domain.dimensions == 1:
                x = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
                theta_a = amplitude * np.exp(1j * frequency * x)
            elif self.domain.dimensions == 2:
                x = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
                y = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
                X, Y = np.meshgrid(x, y, indexing="ij")
                theta_a = amplitude * np.exp(1j * frequency * (X + Y))
            else:  # 3D
                x = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
                y = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
                z = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
                X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
                theta_a = amplitude * np.exp(1j * frequency * (X + Y + Z))

            self.theta_components.append(theta_a)

    def _setup_phase_components_blocked(self, phase_config: Dict[str, Any]) -> None:
        """
        Setup phase components using block processing for large domains.
        
        Physical Meaning:
            Creates phase components using block-based processing to
            handle memory-efficient initialization for large 7D domains.
        """
        try:
            from bhlff.core.sources.blocked_field_generator import BlockedFieldGenerator
            
            for a in range(3):  # Three U(1) components
                amplitude = phase_config.get(f"amplitude_{a+1}", 1.0)
                frequency = phase_config.get(f"frequency_{a+1}", 1.0)
                
                # Create block generator function for this component
                def create_phase_block_generator(amp, freq, comp_idx):
                    def phase_block_generator(domain, slice_config, config):
                        """Generate phase component block."""
                        block_shape = slice_config["shape"]
                        block_indices = slice_config.get("block_indices", {})
                        
                        # Create block coordinates
                        # For simplicity, use simple phase pattern per block
                        # In production, this would use proper coordinate mapping
                        block_data = np.zeros(block_shape, dtype=complex)
                        
                        # Create simple phase pattern for this block
                        # This is a simplified version - full implementation would
                        # properly map coordinates from domain to block
                        indices = np.indices(block_shape)
                        phase_sum = np.sum(indices, axis=0)
                        if phase_sum.size > 0:
                            max_val = np.max(phase_sum) if np.max(phase_sum) > 0 else 1.0
                            block_data = amp * np.exp(1j * freq * phase_sum / max_val)
                        
                        return block_data
                    
                    return phase_block_generator
                
                # Create generator for this component
                generator_func = create_phase_block_generator(amplitude, frequency, a)
                
                # Use BlockedFieldGenerator
                generator = BlockedFieldGenerator(self.domain, generator_func)
                theta_a = generator.get_field()
                
                self.theta_components.append(theta_a)
                
        except Exception as e:
            self.logger.warning(
                f"Block processing failed for phase components: {e}, "
                f"falling back to direct initialization (may fail for large domains)"
            )
            # Fallback to direct initialization (will likely fail for large domains)
            self._setup_phase_components_direct(phase_config)

