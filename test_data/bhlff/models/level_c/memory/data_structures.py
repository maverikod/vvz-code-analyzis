"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Data structures for quench memory analysis.

This module contains data structures used in quench memory analysis
for Level C test C3 in 7D phase field theory.

Physical Meaning:
    Defines data structures for quench memory analysis, including
    memory parameters and quench event specifications.

Example:
    >>> memory_params = MemoryParameters(gamma=0.5, tau=10.0)
    >>> quench_event = QuenchEvent(timestamp=5.0, intensity=0.8)
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class MemoryParameters:
    """
    Memory parameters for quench analysis.

    Physical Meaning:
        Defines the parameters for quench memory analysis,
        including memory strength, relaxation time, and
        spatial distribution.

    Mathematical Foundation:
        Represents memory parameters for the memory kernel:
        K(t) = (1/τ) * Θ(t_cutoff - t)  # Step resonator function
        where τ is the relaxation time and γ is the memory strength.

    Attributes:
        gamma (float): Memory strength (0 ≤ γ ≤ 1).
        tau (float): Relaxation time.
        spatial_distribution (np.ndarray): Spatial distribution of memory.
        memory_threshold (float): Threshold for memory activation.
    """

    gamma: float  # Memory strength (0 ≤ γ ≤ 1)
    tau: float  # Relaxation time
    spatial_distribution: np.ndarray = None
    memory_threshold: float = 0.1

    def __post_init__(self):
        """Initialize default spatial distribution if not provided."""
        if self.spatial_distribution is None:
            self.spatial_distribution = np.ones(1)

    @property
    def memory_strength(self) -> float:
        """
        Memory strength parameter.

        Physical Meaning:
            Returns the memory strength parameter γ,
            which controls the intensity of memory effects.

        Returns:
            float: Memory strength.
        """
        return self.gamma

    @property
    def relaxation_time(self) -> float:
        """
        Relaxation time parameter.

        Physical Meaning:
            Returns the relaxation time parameter τ,
            which controls the decay rate of memory effects.

        Returns:
            float: Relaxation time.
        """
        return self.tau

    @property
    def memory_decay_rate(self) -> float:
        """
        Memory decay rate.

        Physical Meaning:
            Computes the decay rate of memory effects
            as 1/τ.

        Returns:
            float: Memory decay rate.
        """
        return 1.0 / self.tau if self.tau > 0 else 0.0

    @property
    def memory_lifetime(self) -> float:
        """
        Memory lifetime.

        Physical Meaning:
            Computes the characteristic lifetime of memory
            effects as τ.

        Returns:
            float: Memory lifetime.
        """
        return self.tau


@dataclass
class QuenchEvent:
    """
    Quench event specification.

    Physical Meaning:
        Represents a quench event with timestamp, intensity,
        and spatial characteristics.

    Mathematical Foundation:
        Represents a quench event at time t with intensity I:
        Q(t) = I δ(t - t_quench)
        where δ is the Dirac delta function.

    Attributes:
        timestamp (float): Time of the quench event.
        intensity (float): Intensity of the quench event.
        spatial_position (np.ndarray): Spatial position of the quench.
        event_type (str): Type of quench event.
    """

    timestamp: float
    intensity: float
    spatial_position: np.ndarray = None
    event_type: str = "thermal"

    def __post_init__(self):
        """Initialize default spatial position if not provided."""
        if self.spatial_position is None:
            self.spatial_position = np.array([0.0, 0.0, 0.0])

    @property
    def event_strength(self) -> float:
        """
        Event strength.

        Physical Meaning:
            Returns the strength of the quench event,
            which determines its impact on the system.

        Returns:
            float: Event strength.
        """
        return self.intensity

    @property
    def event_duration(self) -> float:
        """
        Event duration.

        Physical Meaning:
            Computes the characteristic duration of the
            quench event.

        Returns:
            float: Event duration.
        """
        return 1.0 / self.intensity if self.intensity > 0 else 0.0

    @property
    def event_energy(self) -> float:
        """
        Event energy.

        Physical Meaning:
            Computes the energy associated with the
            quench event.

        Returns:
            float: Event energy.
        """
        return 0.5 * self.intensity**2


@dataclass
class MemoryKernel:
    """
    Memory kernel specification.

    Physical Meaning:
        Represents a memory kernel for quench analysis,
        including temporal and spatial characteristics.

    Mathematical Foundation:
        Represents a memory kernel of the form:
        K(t) = (1/τ) * Θ(t_cutoff - t)  # Step resonator function
        where τ is the relaxation time.

    Attributes:
        temporal_kernel (np.ndarray): Temporal kernel values.
        spatial_kernel (np.ndarray): Spatial kernel values.
        relaxation_time (float): Relaxation time.
        memory_strength (float): Memory strength parameter.
    """

    temporal_kernel: np.ndarray
    spatial_kernel: np.ndarray
    relaxation_time: float
    memory_strength: float

    @property
    def kernel_amplitude(self) -> float:
        """
        Kernel amplitude.

        Physical Meaning:
            Returns the amplitude of the memory kernel,
            which determines its strength.

        Returns:
            float: Kernel amplitude.
        """
        return self.memory_strength / self.relaxation_time

    @property
    def kernel_decay_rate(self) -> float:
        """
        Kernel decay rate.

        Physical Meaning:
            Computes the decay rate of the memory kernel
            as 1/τ.

        Returns:
            float: Kernel decay rate.
        """
        return 1.0 / self.relaxation_time if self.relaxation_time > 0 else 0.0

    @property
    def kernel_lifetime(self) -> float:
        """
        Kernel lifetime.

        Physical Meaning:
            Computes the characteristic lifetime of the
            memory kernel as τ.

        Returns:
            float: Kernel lifetime.
        """
        return self.relaxation_time


@dataclass
class MemoryState:
    """
    Memory state specification.

    Physical Meaning:
        Represents the current state of memory in the system,
        including memory content and activation level.

    Mathematical Foundation:
        Represents the memory state as:
        M(t) = ∫_0^t K(t-τ) a(τ) dτ
        where K is the memory kernel and a is the field.

    Attributes:
        memory_content (np.ndarray): Current memory content.
        activation_level (float): Memory activation level.
        memory_age (float): Age of the memory.
        memory_stability (float): Memory stability metric.
    """

    memory_content: np.ndarray
    activation_level: float
    memory_age: float
    memory_stability: float

    @property
    def memory_intensity(self) -> float:
        """
        Memory intensity.

        Physical Meaning:
            Returns the intensity of the memory state,
            which determines its influence on the system.

        Returns:
            float: Memory intensity.
        """
        return np.mean(np.abs(self.memory_content))

    @property
    def memory_coherence(self) -> float:
        """
        Memory coherence.

        Physical Meaning:
            Computes the coherence of the memory state,
            indicating its stability and consistency.

        Returns:
            float: Memory coherence.
        """
        return self.memory_stability * self.activation_level

    @property
    def memory_energy(self) -> float:
        """
        Memory energy.

        Physical Meaning:
            Computes the energy associated with the
            memory state.

        Returns:
            float: Memory energy.
        """
        return 0.5 * np.sum(np.abs(self.memory_content) ** 2)
