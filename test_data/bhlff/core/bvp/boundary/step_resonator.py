"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Semi-transparent step resonator boundary operator for 7D phase field fields.

Physical Meaning:
    Implements partial reflection and transmission at domain boundaries to
    model semi-transparent resonator walls. No exponential attenuation is
    used; energy exchange occurs via boundary mixing with reflection (R) and
    transmission (T) coefficients.

Mathematical Foundation:
    For a given spatial axis a and boundary indices 0 and -1, apply:
        f[0]  <- R * f[0]  + T * f[1]
        f[-1] <- R * f[-1] + T * f[-2]
    where 0 <= R <= 1, 0 <= T <= 1 and typically R + T <= 1 (leaky walls).

Usage:
    apply_step_resonator(field, axes=(0,1,2), R=0.1, T=0.9)
"""

from typing import Iterable, Tuple, Dict, Any, Optional
import numpy as np


def apply_step_resonator(
    field: np.ndarray,
    axes: Iterable[int] = (0, 1, 2),
    R: float | np.ndarray = 0.1,
    T: float | np.ndarray = 0.9,
) -> np.ndarray:
    """
    Apply semi-transparent step resonator boundary conditions in-place.

    Args:
        field: N-dimensional complex or real field (supports 7D arrays)
        axes: axes along which to apply boundary mixing (e.g., spatial axes)
        R: reflection coefficient at the wall (0..1)
        T: transmission coefficient from the interior cell (0..1)

    Returns:
        np.ndarray: The same field array with updated boundary values.
    """
    # Allow scalar or frequency-dependent arrays for R/T
    if np.isscalar(R):
        if not 0.0 <= float(R) <= 1.0:
            raise ValueError("R must be in [0,1]")
    if np.isscalar(T):
        if not 0.0 <= float(T) <= 1.0:
            raise ValueError("T must be in [0,1]")

    # Work on a view to avoid copies
    updated = field

    for axis in axes:
        if updated.shape[axis] < 2:
            continue  # cannot apply mixing on degenerate axis

        # Build index tuples for boundary and neighbor positions
        slicer_low = [slice(None)] * updated.ndim
        slicer_low_neighbor = [slice(None)] * updated.ndim
        slicer_high = [slice(None)] * updated.ndim
        slicer_high_neighbor = [slice(None)] * updated.ndim

        slicer_low[axis] = 0
        slicer_low_neighbor[axis] = 1
        slicer_high[axis] = -1
        slicer_high_neighbor[axis] = -2

        low = tuple(slicer_low)
        low_n = tuple(slicer_low_neighbor)
        high = tuple(slicer_high)
        high_n = tuple(slicer_high_neighbor)

        # Apply mixing at both boundaries
        # If R/T are arrays (e.g., frequency/axis-dependent), rely on numpy broadcasting
        updated[low] = (R * updated[low]) + (T * updated[low_n])
        updated[high] = (R * updated[high]) + (T * updated[high_n])

    return updated


class FrequencyDependentResonator:
    """
    Frequency-dependent step resonator with transmission/reflection coefficients.

    Physical Meaning:
        Implements frequency-dependent energy exchange through semi-transparent
        resonator walls, where transmission and reflection coefficients depend
        on the frequency content of the field.

    Mathematical Foundation:
        Step resonator model (no exponential attenuation):
        R(ω) = R₀ for ω < ω₀, 0 otherwise
        T(ω) = T₀ for ω < ω₀, 0 otherwise
        where ω₀ is the characteristic cutoff frequency of the resonator.
    """

    def __init__(
        self,
        R0: float = 0.1,
        T0: float = 0.9,
        omega0: float = 1.0,
        frequency_axis: int = -1,
    ):
        """
        Initialize frequency-dependent resonator.

        Args:
            R0: Base reflection coefficient
            T0: Base transmission coefficient
            omega0: Characteristic frequency of the resonator
            frequency_axis: Axis along which frequency varies
        """
        self.R0 = R0
        self.T0 = T0
        self.omega0 = omega0
        self.frequency_axis = frequency_axis

    def compute_coefficients(
        self, frequencies: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute frequency-dependent reflection and transmission coefficients.

        Physical Meaning:
            Computes R(ω) and T(ω) based on the frequency content,
            implementing the resonator's frequency response.

        Args:
            frequencies: Frequency array

        Returns:
            Tuple of (R, T) coefficient arrays
        """
        # Frequency-dependent coefficients using step resonator model (no exponential)
        # Use step function with transmission/reflection coefficients
        # Step resonator: T = T0 for frequencies < omega0, R = R0 for frequencies >= omega0
        R = np.where(frequencies < self.omega0, self.R0, 0.0)
        T = np.where(frequencies < self.omega0, self.T0, 0.0)

        return R, T


class CascadeResonatorFilter:
    """
    Cascade resonator filter for multi-stage energy exchange.

    Physical Meaning:
        Implements a cascade of semi-transparent resonators where energy
        flows through multiple stages with different transmission/reflection
        characteristics at each stage.

    Mathematical Foundation:
        For N stages, the total transmission is:
        T_total = ∏ᵢ Tᵢ(ω)
        where Tᵢ(ω) is the transmission coefficient of stage i.
    """

    def __init__(self, stages: int = 3, base_R: float = 0.1, base_T: float = 0.9):
        """
        Initialize cascade resonator filter.

        Args:
            stages: Number of resonator stages
            base_R: Base reflection coefficient
            base_T: Base transmission coefficient
        """
        self.stages = stages
        self.base_R = base_R
        self.base_T = base_T
        self.resonators = []

        # Create frequency-dependent resonators for each stage
        for i in range(stages):
            # Vary parameters across stages
            R0 = base_R * (1.0 + 0.1 * i)  # Slightly increasing reflection
            T0 = base_T * (1.0 - 0.05 * i)  # Slightly decreasing transmission
            omega0 = 1.0 + 0.2 * i  # Increasing characteristic frequency

            resonator = FrequencyDependentResonator(R0, T0, omega0)
            self.resonators.append(resonator)

    def apply_cascade_filter(
        self,
        field: np.ndarray,
        frequencies: np.ndarray,
        axes: Iterable[int] = (0, 1, 2),
    ) -> np.ndarray:
        """
        Apply cascade resonator filter to field.

        Physical Meaning:
            Applies energy exchange through multiple resonator stages,
            each with different frequency-dependent characteristics.

        Args:
            field: Input field array
            frequencies: Frequency array
            axes: Axes along which to apply filtering

        Returns:
            Filtered field array
        """
        result = field.copy()

        # Apply each resonator stage sequentially
        for i, resonator in enumerate(self.resonators):
            # Compute coefficients for this stage
            R, T = resonator.compute_coefficients(frequencies)

            # Apply step resonator with frequency-dependent coefficients
            # Use scalar coefficients for simplicity in cascade
            R_scalar = np.mean(R) if len(R) > 0 else 0.1
            T_scalar = np.mean(T) if len(T) > 0 else 0.9

            result = apply_step_resonator(result, axes=axes, R=R_scalar, T=T_scalar)

        return result


def create_frequency_dependent_resonator(
    field_shape: Tuple[int, ...],
    frequency_axis: int = -1,
    parameters: Optional[Dict[str, Any]] = None,
) -> FrequencyDependentResonator:
    """
    Create frequency-dependent resonator for given field shape.

    Physical Meaning:
        Creates a resonator optimized for the given field dimensions
        and frequency characteristics.

    Args:
        field_shape: Shape of the field array
        frequency_axis: Axis along which frequency varies
        parameters: Optional resonator parameters

    Returns:
        Configured FrequencyDependentResonator
    """
    if parameters is None:
        parameters = {}

    R0 = parameters.get("R0", 0.1)
    T0 = parameters.get("T0", 0.9)
    omega0 = parameters.get("omega0", 1.0)

    return FrequencyDependentResonator(R0, T0, omega0, frequency_axis)


def create_cascade_filter(
    stages: int = 3, parameters: Optional[Dict[str, Any]] = None
) -> CascadeResonatorFilter:
    """
    Create cascade resonator filter.

    Physical Meaning:
        Creates a multi-stage resonator filter for complex energy exchange
        patterns through semi-transparent boundaries.

    Args:
        stages: Number of resonator stages
        parameters: Optional filter parameters

    Returns:
        Configured CascadeResonatorFilter
    """
    if parameters is None:
        parameters = {}

    base_R = parameters.get("base_R", 0.1)
    base_T = parameters.get("base_T", 0.9)

    return CascadeResonatorFilter(stages, base_R, base_T)
