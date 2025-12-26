"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Memory kernel implementation for non-local operations.

This module implements memory kernels for non-local phase field operations
in the 7D phase field theory.

Physical Meaning:
    Memory kernels represent the non-local interactions in phase field
    configurations, capturing the influence of distant regions on local
    field evolution.

Mathematical Foundation:
    Implements memory kernels K(x,y) for non-local operations:
    (K * a)(x) = ∫ K(x,y) a(y) dy
    where K(x,y) is the memory kernel function.

Example:
    >>> kernel = MemoryKernel(domain, kernel_type="power_law")
    >>> result = kernel.apply(field)
"""

import numpy as np
from typing import Dict, Any, Optional

from ..domain import Domain
from ..bvp.boundary.step_resonator import (
    FrequencyDependentResonator,
    CascadeResonatorFilter,
)


class MemoryKernel:
    """
    Memory kernel for non-local phase field operations.

    Physical Meaning:
        Implements memory kernels that capture non-local interactions
        in phase field configurations, representing the influence of
        distant regions on local field evolution.

    Mathematical Foundation:
        Memory kernels K(x,y) implement non-local operations:
        (K * a)(x) = ∫ K(x,y) a(y) dy
        where the kernel function K(x,y) determines the nature of
        non-local interactions.

    Attributes:
        domain (Domain): Computational domain.
        kernel_type (str): Type of memory kernel.
        parameters (Dict[str, Any]): Kernel parameters.
        _kernel_data (np.ndarray): Pre-computed kernel data.
    """

    def __init__(
        self,
        domain: Domain,
        kernel_type: str = "power_law",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize memory kernel.

        Physical Meaning:
            Sets up the memory kernel with specified type and parameters
            for non-local phase field interactions.

        Args:
            domain (Domain): Computational domain for the kernel.
            kernel_type (str): Type of memory kernel ("power_law",
                "exponential" (uses resonator model), "gaussian").
            parameters (Dict[str, Any], optional): Kernel parameters.

        Raises:
            ValueError: If kernel_type is not supported.
        """
        self.domain = domain
        self.kernel_type = kernel_type
        self.parameters = parameters or {}

        valid_kernel_types = ["power_law", "exponential", "gaussian"]
        if kernel_type not in valid_kernel_types:
            raise ValueError(f"Unsupported kernel type: {kernel_type}")

        self._kernel_data: np.ndarray
        self._setup_kernel()

    def _setup_kernel(self) -> None:
        """
        Setup memory kernel data.

        Physical Meaning:
            Pre-computes the memory kernel data based on the specified
            kernel type and parameters.

        Mathematical Foundation:
            Computes the kernel function K(x,y) in spatial or spectral
            space depending on the kernel type.
        """
        if self.kernel_type == "power_law":
            self._setup_power_law_kernel()
        elif self.kernel_type == "exponential":
            self._setup_resonator_kernel()
        elif self.kernel_type == "gaussian":
            self._setup_gaussian_kernel()

    def _setup_power_law_kernel(self) -> None:
        """
        Setup power law memory kernel.

        Physical Meaning:
            Implements a power law kernel K(r) ∝ r^(-α) that represents
            long-range interactions with power law decay.

        Mathematical Foundation:
            Power law kernel: K(r) = A * r^(-α) for r > 0
            where A is the amplitude and α is the power law exponent.
        """
        alpha = self.parameters.get("alpha", 1.0)
        amplitude = self.parameters.get("amplitude", 1.0)

        # Create coordinate arrays
        if self.domain.dimensions == 1:
            x = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            r = np.abs(x)
        elif self.domain.dimensions == 2:
            x = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            y = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            X, Y = np.meshgrid(x, y, indexing="ij")
            r = np.sqrt(X**2 + Y**2)
        else:  # 3D
            x = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            y = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            z = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
            r = np.sqrt(X**2 + Y**2 + Z**2)

        # Avoid division by zero
        r_safe = np.where(r < 1e-12, 1e-12, r)

        # Power law kernel
        self._kernel_data = amplitude * (r_safe ** (-alpha))

        # Set center to zero to avoid singularity
        if self.domain.dimensions == 1:
            self._kernel_data[self.domain.N // 2] = 0.0
        elif self.domain.dimensions == 2:
            self._kernel_data[self.domain.N // 2, self.domain.N // 2] = 0.0
        else:  # 3D
            self._kernel_data[
                self.domain.N // 2, self.domain.N // 2, self.domain.N // 2
            ] = 0.0

    def _setup_resonator_kernel(self) -> None:
        """
        Setup step resonator memory kernel.

        Physical Meaning:
            Implements a step resonator kernel K(r) that represents
            energy exchange through semi-transparent resonator boundaries
            according to 7D BVP theory.

        Mathematical Foundation:
            Resonator kernel: K(r) = T(r) * R(r) where T is transmission
            and R is reflection coefficient through step resonator boundaries.
        """
        length_scale = self.parameters.get("length_scale", 1.0)
        amplitude = self.parameters.get("amplitude", 1.0)

        # Create coordinate arrays
        if self.domain.dimensions == 1:
            x = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            r = np.abs(x)
        elif self.domain.dimensions == 2:
            x = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            y = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            X, Y = np.meshgrid(x, y, indexing="ij")
            r = np.sqrt(X**2 + Y**2)
        else:  # 3D
            x = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            y = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            z = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
            r = np.sqrt(X**2 + Y**2 + Z**2)

        # Initialize frequency-dependent resonator
        if not hasattr(self, "_resonator"):
            self._resonator = FrequencyDependentResonator(
                R0=self.parameters.get("R0", 0.1),
                T0=self.parameters.get("T0", 0.9),
                omega0=self.parameters.get("omega0", 1.0),
            )

        # Compute frequency-dependent coefficients
        # Use radial distance as proxy for frequency content
        field_frequencies = r / length_scale  # Normalized frequency
        R, T = self._resonator.compute_coefficients(field_frequencies)

        # Step resonator kernel: frequency-dependent T/R coefficients
        self._kernel_data = amplitude * np.where(
            r < length_scale,
            T,  # Use frequency-dependent transmission
            R,  # Use frequency-dependent reflection
        )

    def _setup_gaussian_kernel(self) -> None:
        """
        Setup Gaussian memory kernel.

        Physical Meaning:
            Implements a Gaussian kernel K(r) ∝ exp(-r²/(2σ²)) that represents
            localized interactions with Gaussian decay.

        Mathematical Foundation:
            Gaussian kernel: K(r) = A * exp(-r²/(2σ²))
            where A is the amplitude and σ is the standard deviation.
        """
        sigma = self.parameters.get("sigma", 1.0)
        amplitude = self.parameters.get("amplitude", 1.0)

        # Create coordinate arrays
        if self.domain.dimensions == 1:
            x = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            r = np.abs(x)
        elif self.domain.dimensions == 2:
            x = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            y = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            X, Y = np.meshgrid(x, y, indexing="ij")
            r = np.sqrt(X**2 + Y**2)
        else:  # 3D
            x = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            y = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            z = np.linspace(-self.domain.L / 2, self.domain.L / 2, self.domain.N)
            X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
            r = np.sqrt(X**2 + Y**2 + Z**2)

        # Power law kernel instead of Gaussian (no exponential attenuation)
        # Power law: kernel = amplitude / (1 + r^2/sigma^2)
        self._kernel_data = amplitude / (1.0 + (r**2) / (sigma**2))

    def apply(self, field: np.ndarray) -> np.ndarray:
        """
        Apply memory kernel to field.

        Physical Meaning:
            Applies the memory kernel to the field, computing the non-local
            convolution operation.

        Mathematical Foundation:
            Computes (K * a)(x) = ∫ K(x,y) a(y) dy using convolution:
            (K * a) = FFT^{-1}(FFT(K) * FFT(a))

        Args:
            field (np.ndarray): Input field a(x).

        Returns:
            np.ndarray: Result of kernel application (K * a)(x).

        Raises:
            ValueError: If field shape is incompatible with domain.
        """
        if field.shape != self.domain.shape:
            raise ValueError(
                f"Field shape {field.shape} incompatible with "
                f"domain shape {self.domain.shape}"
            )

        # Transform to spectral space
        field_spectral = np.fft.fftn(field)
        kernel_spectral = np.fft.fftn(self._kernel_data)

        # Apply convolution in spectral space
        result_spectral = kernel_spectral * field_spectral

        # Transform back to real space
        result = np.fft.ifftn(result_spectral)

        return result.real

    def get_kernel_data(self) -> np.ndarray:
        """
        Get the memory kernel data.

        Physical Meaning:
            Returns the pre-computed memory kernel data K(x,y).

        Returns:
            np.ndarray: Memory kernel data.
        """
        return self._kernel_data.copy()

    def get_kernel_type(self) -> str:
        """
        Get the kernel type.

        Physical Meaning:
            Returns the type of memory kernel being used.

        Returns:
            str: Kernel type.
        """
        return self.kernel_type

    def get_parameters(self) -> Dict[str, Any]:
        """
        Get kernel parameters.

        Physical Meaning:
            Returns the parameters used to define the memory kernel.

        Returns:
            Dict[str, Any]: Kernel parameters.
        """
        return self.parameters.copy()

    def __repr__(self) -> str:
        """String representation of the memory kernel."""
        return (
            f"MemoryKernel(domain={self.domain}, "
            f"kernel_type={self.kernel_type}, "
            f"parameters={self.parameters})"
        )
