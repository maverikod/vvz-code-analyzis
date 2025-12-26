"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base initialization for phase components.
"""

import numpy as np
from typing import Dict, Any, List
import logging

from bhlff.core.domain import Domain

# CUDA optimization
try:
    import cupy as cp

    CUDA_AVAILABLE = True
    logging.info("CUDA support enabled with CuPy")
except ImportError:
    CUDA_AVAILABLE = False
    logging.warning("CUDA not available, falling back to CPU")


class PhaseComponentsBase:
    """
    Base class for phase components initialization.

    Physical Meaning:
        Provides base initialization for three U(1) phase components
        with CUDA optimization support.
    """

    def __init__(self, domain: Domain, config: Dict[str, Any]) -> None:
        """
        Initialize phase components manager.

        Physical Meaning:
            Sets up the three U(1) phase components Θ_a (a=1..3)
            with proper spatial distribution and frequencies.

        Args:
            domain (Domain): Computational domain.
            config (Dict[str, Any]): Phase components configuration including:
                - phase_amplitudes: Amplitudes for each phase component
                - phase_frequencies: Frequencies for each phase component
        """
        self.domain = domain
        self.config = config
        self.theta_components: List[np.ndarray] = []
        self._components_initialized = False  # Lazy initialization flag

        # CUDA optimization setup
        self.cuda_available = CUDA_AVAILABLE
        self.use_cuda = config.get("use_cuda", True) and self.cuda_available
        self.logger = logging.getLogger(__name__)

        if self.use_cuda:
            self.logger.info("PhaseComponents: CUDA optimization enabled")
        else:
            self.logger.info("PhaseComponents: Using CPU computation")

        # Check if domain is too large for immediate initialization
        total_elements = np.prod(domain.shape)
        memory_needed_gb = (total_elements * 16) / (1024**3)  # complex128 = 16 bytes
        
        # Use lazy initialization for large domains (>1GB)
        if memory_needed_gb > 1.0:
            self.logger.info(
                f"PhaseComponents: Large domain detected ({memory_needed_gb:.2f} GB), "
                f"using lazy initialization with block processing"
            )
            # Don't initialize immediately - will be done on-demand
        else:
            # Small domain - initialize immediately
            from .phase_components_setup import PhaseComponentsSetup
            setup = PhaseComponentsSetup(self.domain, self.config)
            setup.setup_phase_components()
            self.theta_components = setup.theta_components
            self._components_initialized = True

