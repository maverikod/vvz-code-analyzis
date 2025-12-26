"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Radial analysis core module.

This module implements core radial analysis functionality for boundary effects
in Level C test C1 of 7D phase field theory.

Physical Meaning:
    Analyzes radial profiles for boundary effects,
    including field distribution and concentration patterns.

Example:
    >>> analyzer = RadialAnalysisCore(bvp_core)
    >>> results = analyzer.analyze_radial_profile(domain, boundary, field)
"""

import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import logging

from bhlff.core.bvp import BVPCore
from .data_structures import BoundaryGeometry, RadialProfile
from ..cuda import LevelCCUDAProcessor


class RadialAnalysisCore:
    """
    Radial analysis core for boundary effects.

    Physical Meaning:
        Analyzes radial profiles for boundary effects,
        including field distribution and concentration patterns.

    Mathematical Foundation:
        Implements radial analysis:
        - Radial profile: A(r) = (1/4π) ∫_S(r) |a(x)|² dS
        - Local maxima detection in radial profiles
        - Field concentration analysis
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize radial analyzer.

        Physical Meaning:
            Sets up the radial analysis system with
            appropriate parameters and methods.

        Args:
            bvp_core (BVPCore): BVP core framework instance.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Initialize CUDA processor for vectorized operations
        # CUDA is required for Level C - no fallback to CPU
        try:
            self.cuda_processor = LevelCCUDAProcessor(bvp_core, use_cuda=True)
            self.use_cuda = self.cuda_processor.cuda_available
            if not self.use_cuda:
                raise RuntimeError(
                    "CUDA not available - Level C requires GPU acceleration"
                )
        except Exception as e:
            self.logger.error(f"CUDA processor initialization failed: {e}")
            raise RuntimeError(f"Level C requires CUDA: {e}")

    def analyze_radial_profile(
        self, domain: Dict[str, Any], boundary: BoundaryGeometry, field: np.ndarray
    ) -> RadialProfile:
        """
        Analyze radial profile using 7D GPU-accelerated computation.

        Physical Meaning:
            Analyzes radial profile for boundary effects in 7D space-time,
            including field distribution and concentration patterns.
            Uses full 7D radial distance: |x|² = x² + y² + z² + φ₁² + φ₂² + φ₃² + t²

        Mathematical Foundation:
            Radial profile in 7D: A(r) = (1/Ω₆) ∫_S(r) |a(x)|² dS
            where S(r) is the 6-sphere surface in 7D space-time at radius r,
            and Ω₆ = 16π³/15 is the surface area of unit 6-sphere.

        Args:
            domain (Dict[str, Any]): Domain parameters with 7D shape information.
            boundary (BoundaryGeometry): Boundary geometry with 7D center.
            field (np.ndarray): 7D field data (shape: N×N×N×N_phi×N_phi×N_phi×N_t).

        Returns:
            RadialProfile: Radial profile analysis results with amplitudes at each radius.

        Raises:
            RuntimeError: If CUDA is not available or processor not initialized.
            ValueError: If field has incompatible dtype or shape.
        """
        self.logger.info("Starting 7D radial profile analysis on GPU")

        # CUDA is required for Level C - no fallback to CPU
        if not self.use_cuda or self.cuda_processor is None:
            raise RuntimeError(
                "CUDA processor not initialized - Level C requires GPU acceleration"
            )

        # Extract center from boundary - extend to 7D if needed
        if hasattr(boundary, "center"):
            center_3d = np.asarray(boundary.center, dtype=np.float64)
        else:
            L = domain.get("L", 1.0)
            center_3d = np.array([L / 2] * 3, dtype=np.float64)

        # For 7D, center should have 7 coordinates (x, y, z, φ₁, φ₂, φ₃, t)
        # Default phase and time centers to 0
        if len(center_3d) == 3:
            center = np.concatenate(
                [center_3d, np.zeros(4, dtype=np.float64)]  # φ₁, φ₂, φ₃, t centers
            )
        else:
            center = np.asarray(center_3d, dtype=np.float64)
            if len(center) != 7:
                raise ValueError(
                    f"Center must have 3 or 7 dimensions, got {len(center)}"
                )

        # CRITICAL: Enforce precise dtype (float64) before GPU transfer
        center = np.asarray(center, dtype=np.float64).flatten()
        if center.shape[0] != 7:
            raise ValueError(f"Center must have 7 dimensions, got {center.shape[0]}")

        # CRITICAL: Verify no object dtype
        if center.dtype == object:
            raise ValueError(
                f"center has object dtype: {center.dtype}. "
                f"Must be float64 for GPU transfer"
            )
        if center.dtype != np.float64:
            center = center.astype(np.float64)

        # Define radial range with precise dtype
        r_max = domain.get("L", 1.0) / 2
        num_radii = 50
        radii = np.linspace(0, r_max, num_radii, dtype=np.float64)

        # CRITICAL: Enforce precise dtype (float64) before GPU transfer
        radii = np.asarray(radii, dtype=np.float64)
        if radii.dtype == object:
            raise ValueError(
                f"radii has object dtype: {radii.dtype}. "
                f"Must be float64 for GPU transfer"
            )
        if radii.dtype != np.float64:
            radii = radii.astype(np.float64)

        # Handle 7D field - ensure proper dtype before GPU transfer
        from bhlff.core.sources.blocked_field_generator import BlockedField

        if isinstance(field, BlockedField):
            # For BlockedField, extract spatial block
            sample_block = field.generator.get_block_by_indices((0, 0, 0, 0, 0, 0, 0))
            if sample_block is not None:
                field_7d = sample_block
            else:
                raise ValueError("Cannot extract block from BlockedField")
        else:
            field_7d = field

        # CRITICAL: Enforce precise dtype (float64/complex128) before GPU transfer
        # No CPU path - Level C requires GPU-only execution
        if np.iscomplexobj(field_7d):
            field_7d = np.asarray(field_7d, dtype=np.complex128)
        else:
            field_7d = np.asarray(field_7d, dtype=np.float64)

        # Verify field is 7D
        if len(field_7d.shape) != 7:
            raise ValueError(
                f"Field must be 7D, got shape {field_7d.shape} "
                f"with {len(field_7d.shape)} dimensions"
            )

        # CRITICAL: Verify no object dtype - prevents dtype/object pitfalls
        if field_7d.dtype == object:
            raise ValueError(
                f"field_7d has object dtype: {field_7d.dtype}. "
                f"Must be float64 or complex128 for GPU transfer"
            )

        # CRITICAL: Ensure dtype is exactly float64 or complex128
        if field_7d.dtype not in (np.float64, np.complex128):
            # Convert to appropriate dtype
            if np.iscomplexobj(field_7d):
                field_7d = field_7d.astype(np.complex128)
            else:
                field_7d = field_7d.astype(np.float64)
            self.logger.info(f"Converted field dtype to {field_7d.dtype}")

        self.logger.info(
            f"7D field shape: {field_7d.shape}, dtype: {field_7d.dtype}, "
            f"center dtype: {center.dtype}, radii dtype: {radii.dtype}"
        )

        # Compute radial profile using CUDA vectorized operations (7D)
        # GPU-only execution - no CPU fallback
        amplitudes = self.cuda_processor.compute_radial_profile_vectorized(
            field_7d, center, radii, domain
        )

        # CRITICAL: Ensure amplitudes are float64 after GPU computation
        amplitudes = np.asarray(amplitudes, dtype=np.float64)
        if amplitudes.dtype == object:
            raise ValueError(
                f"amplitudes has object dtype: {amplitudes.dtype}. "
                f"Must be float64 after GPU computation"
            )
        if amplitudes.dtype != np.float64:
            amplitudes = amplitudes.astype(np.float64)

        # Create radial profile data structure
        radial_profile_data = {
            "radii": radii,
            "amplitudes": amplitudes,
        }

        # Find local maxima
        local_maxima = self._find_local_maxima(radial_profile_data)

        # Create radial profile object
        profile = RadialProfile(
            radii=radial_profile_data["radii"],
            amplitudes=radial_profile_data["amplitudes"],
            local_maxima=local_maxima,
        )

        self.logger.info("7D radial profile analysis completed on GPU")
        return profile

    def _compute_radial_profile(
        self, domain: Dict[str, Any], boundary: BoundaryGeometry, field: np.ndarray
    ) -> Dict[str, Any]:
        """
        Compute radial profile.

        Physical Meaning:
            Computes radial profile for boundary effects
            analysis.

        Mathematical Foundation:
            Radial profile: A(r) = (1/4π) ∫_S(r) |a(x)|² dS

        Args:
            domain (Dict[str, Any]): Domain parameters.
            boundary (BoundaryGeometry): Boundary geometry.
            field (np.ndarray): Field data.

        Returns:
            Dict[str, Any]: Radial profile data.
        """
        # Extract domain parameters
        N = domain["N"]
        L = domain["L"]

        # Define radial range
        r_max = L / 2
        num_radii = 50
        radii = np.linspace(0, r_max, num_radii)

        # Initialize amplitude array
        amplitudes = np.zeros(num_radii)

        # Compute amplitude at each radius
        for i, r in enumerate(radii):
            amplitudes[i] = self._compute_amplitude_at_radius(domain, field, r)

        return {
            "radii": radii,
            "amplitudes": amplitudes,
        }

    def _compute_amplitude_at_radius(
        self, domain: Dict[str, Any], field: np.ndarray, radius: float
    ) -> float:
        """
        Compute amplitude at specific radius.

        Physical Meaning:
            Computes field amplitude at specific radius
            for radial profile analysis.

        Mathematical Foundation:
            Amplitude at radius: A(r) = (1/4π) ∫_S(r) |a(x)|² dS

        Args:
            domain (Dict[str, Any]): Domain parameters.
            field (np.ndarray): Field data.
            radius (float): Radius for computation.

        Returns:
            float: Amplitude at radius.
        """
        # Create spherical shell mask (3D spatial mask)
        shell_mask = self._create_spherical_shell_mask(domain, radius)

        # Handle 7D field - extract spatial part for mask application
        # Теория работает на 7D, но mask применяется к пространственным измерениям
        from bhlff.core.sources.blocked_field_generator import BlockedField

        if isinstance(field, BlockedField):
            # For BlockedField, extract spatial block that matches mask
            # Get full spatial slice, average over phase and temporal dimensions
            N = domain["N"]
            # Get spatial slice, keeping all phase/temporal dimensions
            # Then average over phase and time for radial analysis
            field_spatial = field[:, :, :, :, :, :, :]  # Get full 7D block
            # Average over phase and temporal dimensions (indices 3,4,5,6)
            if hasattr(field_spatial, "shape") and len(field_spatial.shape) == 7:
                field_3d = np.mean(np.abs(field_spatial), axis=(3, 4, 5, 6))
            else:
                # If already extracted, use as is
                field_3d = field_spatial
        else:
            # Regular numpy array - extract 3D spatial part
            if len(field.shape) == 7:
                # Average over phase and temporal dimensions
                field_3d = np.mean(np.abs(field), axis=(3, 4, 5, 6))
            else:
                field_3d = field

        # Ensure field_3d matches shell_mask shape
        if field_3d.shape != shell_mask.shape:
            # Crop to match mask shape
            min_shape = tuple(
                min(s, m) for s, m in zip(field_3d.shape, shell_mask.shape)
            )
            field_3d = field_3d[tuple(slice(0, s) for s in min_shape)]
            shell_mask = shell_mask[tuple(slice(0, s) for s in min_shape)]

        # Compute amplitude
        amplitude = np.sqrt(np.mean(np.abs(field_3d[shell_mask]) ** 2))

        return amplitude

    def _create_spherical_shell_mask(
        self, domain: Dict[str, Any], radius: float
    ) -> np.ndarray:
        """
        Create spherical shell mask.

        Physical Meaning:
            Creates spherical shell mask for radial
            profile computation.

        Args:
            domain (Dict[str, Any]): Domain parameters.
            radius (float): Shell radius.

        Returns:
            np.ndarray: Spherical shell mask.
        """
        # Extract domain parameters
        N = domain["N"]
        L = domain["L"]

        # Create coordinate arrays
        x = np.linspace(0, L, N)
        y = np.linspace(0, L, N)
        z = np.linspace(0, L, N)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

        # Calculate distance from center
        center = L / 2
        distance = np.sqrt((X - center) ** 2 + (Y - center) ** 2 + (Z - center) ** 2)

        # Create shell mask
        shell_thickness = L / (2 * N)  # Shell thickness
        shell_mask = (distance >= radius - shell_thickness) & (
            distance <= radius + shell_thickness
        )

        return shell_mask

    def _find_local_maxima(
        self, radial_profile: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Find local maxima in radial profile.

        Physical Meaning:
            Finds local maxima in radial profile
            for boundary effects analysis.

        Args:
            radial_profile (Dict[str, Any]): Radial profile data.

        Returns:
            List[Dict[str, Any]]: Local maxima information.
        """
        amplitudes = radial_profile["amplitudes"]
        radii = radial_profile["radii"]

        # Find local maxima
        local_maxima = []
        for i in range(1, len(amplitudes) - 1):
            if (
                amplitudes[i] > amplitudes[i - 1]
                and amplitudes[i] > amplitudes[i + 1]
                and amplitudes[i] > np.mean(amplitudes)
            ):
                maximum = {
                    "radius": radii[i],
                    "amplitude": amplitudes[i],
                    "index": i,
                }
                local_maxima.append(maximum)

        return local_maxima
