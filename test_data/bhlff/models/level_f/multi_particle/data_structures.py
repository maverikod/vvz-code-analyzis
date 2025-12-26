"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Data structures for multi-particle systems.

This module contains data structures used in multi-particle system
analysis for Level F in 7D phase field theory.

Physical Meaning:
    Defines data structures for multi-particle systems, including
    particle representation and system parameters.

Example:
    >>> particle = Particle(position=np.array([5, 10, 10]), charge=1, phase=0)
    >>> system_params = SystemParameters(interaction_range=2.0, interaction_strength=1.0)
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class Particle:
    """
    Particle in multi-particle system.

    Physical Meaning:
        Represents a topological defect with position, charge, phase,
        and energy in the 7D phase field theory.

    Mathematical Foundation:
        Represents a particle with:
        - Position: x = (x, y, z) in 3D space
        - Charge: q ∈ ℤ (topological charge)
        - Phase: φ ∈ [0, 2π) (initial phase)
        - Energy: E_eff (effective energy from field configuration)

    Attributes:
        position (np.ndarray): 3D coordinates of the particle
        charge (int): Topological charge q ∈ ℤ
        phase (float): Initial phase φ ∈ [0, 2π)
        energy (float): Effective energy E_eff from field configuration
    """

    position: np.ndarray
    charge: int
    phase: float = 0.0
    energy: float = 1.0

    def __post_init__(self):
        """Initialize particle properties."""
        # Ensure position is numpy array
        if not isinstance(self.position, np.ndarray):
            self.position = np.array(self.position)

        # Ensure position is 3D
        if len(self.position) != 3:
            raise ValueError("Position must be 3D")

        # Normalize phase to [0, 2π)
        self.phase = self.phase % (2 * np.pi)

        # Ensure energy is positive
        if self.energy <= 0:
            raise ValueError("Energy must be positive")

    @property
    def x(self) -> float:
        """
        X coordinate of the particle.

        Physical Meaning:
            Returns the x-coordinate of the particle position.

        Returns:
            float: X coordinate.
        """
        return float(self.position[0])

    @property
    def y(self) -> float:
        """
        Y coordinate of the particle.

        Physical Meaning:
            Returns the y-coordinate of the particle position.

        Returns:
            float: Y coordinate.
        """
        return float(self.position[1])

    @property
    def z(self) -> float:
        """
        Z coordinate of the particle.

        Physical Meaning:
            Returns the z-coordinate of the particle position.

        Returns:
            float: Z coordinate.
        """
        return float(self.position[2])

    @property
    def is_positive_charge(self) -> bool:
        """
        Check if particle has positive charge.

        Physical Meaning:
            Returns True if the particle has positive topological charge.

        Returns:
            bool: True if charge > 0.
        """
        return self.charge > 0

    @property
    def is_negative_charge(self) -> bool:
        """
        Check if particle has negative charge.

        Physical Meaning:
            Returns True if the particle has negative topological charge.

        Returns:
            bool: True if charge < 0.
        """
        return self.charge < 0

    @property
    def is_neutral_charge(self) -> bool:
        """
        Check if particle has neutral charge.

        Physical Meaning:
            Returns True if the particle has zero topological charge.

        Returns:
            bool: True if charge == 0.
        """
        return self.charge == 0

    def distance_to(self, other: "Particle") -> float:
        """
        Calculate distance to another particle.

        Physical Meaning:
            Calculates the Euclidean distance between
            this particle and another particle.

        Args:
            other (Particle): Other particle.

        Returns:
            float: Distance between particles.
        """
        return float(np.linalg.norm(self.position - other.position))

    def angle_to(self, other: "Particle") -> float:
        """
        Calculate angle to another particle.

        Physical Meaning:
            Calculates the angle between the position
            vectors of this particle and another particle.

        Args:
            other (Particle): Other particle.

        Returns:
            float: Angle in radians.
        """
        # Calculate angle between position vectors
        dot_product = np.dot(self.position, other.position)
        norm_product = np.linalg.norm(self.position) * np.linalg.norm(other.position)

        if norm_product == 0:
            return 0.0

        # Clamp to avoid numerical errors
        cos_angle = np.clip(dot_product / norm_product, -1.0, 1.0)
        angle = np.arccos(cos_angle)

        return float(angle)

    def phase_difference(self, other: "Particle") -> float:
        """
        Calculate phase difference with another particle.

        Physical Meaning:
            Calculates the phase difference between
            this particle and another particle.

        Args:
            other (Particle): Other particle.

        Returns:
            float: Phase difference in radians.
        """
        phase_diff = self.phase - other.phase

        # Normalize to [-π, π]
        while phase_diff > np.pi:
            phase_diff -= 2 * np.pi
        while phase_diff < -np.pi:
            phase_diff += 2 * np.pi

        return float(phase_diff)

    def interaction_strength(
        self, other: "Particle", interaction_range: float
    ) -> float:
        """
        Calculate interaction strength with another particle.

        Physical Meaning:
            Calculates the interaction strength between
            this particle and another particle based on
            their distance and charges.

        Args:
            other (Particle): Other particle.
            interaction_range (float): Interaction range.

        Returns:
            float: Interaction strength.
        """
        distance = self.distance_to(other)

        # Calculate interaction strength
        if distance > interaction_range:
            return 0.0

        # Interaction strength decreases with distance
        strength = (1.0 - distance / interaction_range) ** 2

        # Charge-dependent interaction
        charge_factor = self.charge * other.charge

        return float(strength * charge_factor)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert particle to dictionary.

        Physical Meaning:
            Converts the particle to a dictionary representation
            for serialization and storage.

        Returns:
            Dict[str, Any]: Particle dictionary.
        """
        return {
            "position": self.position.tolist(),
            "charge": self.charge,
            "phase": self.phase,
            "energy": self.energy,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Particle":
        """
        Create particle from dictionary.

        Physical Meaning:
            Creates a particle from a dictionary representation.

        Args:
            data (Dict[str, Any]): Particle data.

        Returns:
            Particle: Created particle.
        """
        return cls(
            position=np.array(data["position"]),
            charge=data["charge"],
            phase=data["phase"],
            energy=data["energy"],
        )

    def __str__(self) -> str:
        """
        String representation of particle.

        Physical Meaning:
            Returns a string representation of the particle
            for debugging and display.

        Returns:
            str: String representation.
        """
        return f"Particle(position={self.position}, charge={self.charge}, phase={self.phase:.3f}, energy={self.energy:.3f})"

    def __repr__(self) -> str:
        """
        Detailed string representation of particle.

        Physical Meaning:
            Returns a detailed string representation of the particle
            for debugging and display.

        Returns:
            str: Detailed string representation.
        """
        return f"Particle(position={self.position}, charge={self.charge}, phase={self.phase:.3f}, energy={self.energy:.3f})"


@dataclass
class SystemParameters:
    """
    Parameters for multi-particle system.

    Physical Meaning:
        Defines the parameters for a multi-particle system,
        including interaction range, strength, and other
        system properties.

    Attributes:
        interaction_range (float): Range of particle interactions
        interaction_strength (float): Strength of interactions
        phase_coherence_length (float): Phase coherence length
        temperature (float): System temperature
        damping (float): Damping coefficient
    """

    interaction_range: float = 2.0
    interaction_strength: float = 1.0
    phase_coherence_length: float = 1.0
    temperature: float = 0.0
    damping: float = 0.1

    def __post_init__(self):
        """Initialize system parameters."""
        # Ensure positive values
        if self.interaction_range <= 0:
            raise ValueError("Interaction range must be positive")
        if self.interaction_strength < 0:
            raise ValueError("Interaction strength must be non-negative")
        if self.phase_coherence_length <= 0:
            raise ValueError("Phase coherence length must be positive")
        if self.temperature < 0:
            raise ValueError("Temperature must be non-negative")
        if self.damping < 0:
            raise ValueError("Damping must be non-negative")

    @property
    def is_high_temperature(self) -> bool:
        """
        Check if system is at high temperature.

        Physical Meaning:
            Returns True if the system temperature is high
            compared to the interaction energy scale.

        Returns:
            bool: True if high temperature.
        """
        # High temperature if T > interaction_strength
        return self.temperature > self.interaction_strength

    @property
    def is_low_temperature(self) -> bool:
        """
        Check if system is at low temperature.

        Physical Meaning:
            Returns True if the system temperature is low
            compared to the interaction energy scale.

        Returns:
            bool: True if low temperature.
        """
        # Low temperature if T < interaction_strength / 10
        return self.temperature < self.interaction_strength / 10.0

    @property
    def is_strongly_damped(self) -> bool:
        """
        Check if system is strongly damped.

        Physical Meaning:
            Returns True if the system has strong damping.

        Returns:
            bool: True if strongly damped.
        """
        # Strongly damped if damping > 0.5
        return self.damping > 0.5

    @property
    def is_weakly_damped(self) -> bool:
        """
        Check if system is weakly damped.

        Physical Meaning:
            Returns True if the system has weak damping.

        Returns:
            bool: True if weakly damped.
        """
        # Weakly damped if damping < 0.1
        return self.damping < 0.1

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert system parameters to dictionary.

        Physical Meaning:
            Converts the system parameters to a dictionary
            representation for serialization and storage.

        Returns:
            Dict[str, Any]: System parameters dictionary.
        """
        return {
            "interaction_range": self.interaction_range,
            "interaction_strength": self.interaction_strength,
            "phase_coherence_length": self.phase_coherence_length,
            "temperature": self.temperature,
            "damping": self.damping,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SystemParameters":
        """
        Create system parameters from dictionary.

        Physical Meaning:
            Creates system parameters from a dictionary representation.

        Args:
            data (Dict[str, Any]): System parameters data.

        Returns:
            SystemParameters: Created system parameters.
        """
        return cls(
            interaction_range=data.get("interaction_range", 2.0),
            interaction_strength=data.get("interaction_strength", 1.0),
            phase_coherence_length=data.get("phase_coherence_length", 1.0),
            temperature=data.get("temperature", 0.0),
            damping=data.get("damping", 0.1),
        )

    def __str__(self) -> str:
        """
        String representation of system parameters.

        Physical Meaning:
            Returns a string representation of the system parameters
            for debugging and display.

        Returns:
            str: String representation.
        """
        return f"SystemParameters(range={self.interaction_range:.3f}, strength={self.interaction_strength:.3f}, temp={self.temperature:.3f})"

    def __repr__(self) -> str:
        """
        Detailed string representation of system parameters.

        Physical Meaning:
            Returns a detailed string representation of the system parameters
            for debugging and display.

        Returns:
            str: Detailed string representation.
        """
        return f"SystemParameters(range={self.interaction_range:.3f}, strength={self.interaction_strength:.3f}, temp={self.temperature:.3f}, damping={self.damping:.3f})"
