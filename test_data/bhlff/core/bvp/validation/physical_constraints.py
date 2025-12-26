"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Physical constraints validation for BVP methods.

This module implements validation of physical constraints including
energy conservation, causality, phase coherence, and structure preservation.
"""

import numpy as np
from typing import Dict, Any, Tuple, Optional
import logging


class PhysicalConstraintsValidator:
    """
    Validator for physical constraints in BVP methods.

    Physical Meaning:
        Validates that BVP results satisfy fundamental physical
        constraints including energy conservation, causality, phase
        coherence, and 7D structure preservation.
    """

    def __init__(self, domain_shape: Tuple[int, ...], parameters: Dict[str, Any]):
        """
        Initialize physical constraints validator.

        Physical Meaning:
            Sets up validator with domain information and physical
            parameters for comprehensive constraint validation.

        Args:
            domain_shape (Tuple[int, ...]): Shape of the computational domain.
            parameters (Dict[str, Any]): Physical parameters for validation.
        """
        self.domain_shape = domain_shape
        self.parameters = parameters
        self.logger = logging.getLogger(__name__)

        # Physical constraints
        self.physical_constraints = self._setup_physical_constraints()

    def _setup_physical_constraints(self) -> Dict[str, Any]:
        """Setup physical constraints for validation."""
        return {
            "energy_conservation_tolerance": 1e-6,
            "causality_tolerance": 1e-8,
            "phase_coherence_minimum": 0.1,
            "amplitude_bounds": (1e-15, 1e12),
            "frequency_bounds": (1e-6, 1e15),
            "phase_bounds": (-2 * np.pi, 2 * np.pi),
            "gradient_bounds": (1e-20, 1e10),
        }

    def validate_energy_conservation(
        self,
        field: np.ndarray,
        energy: Optional[Dict[str, float]],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Validate energy conservation.

        Physical Meaning:
            Validates that energy is conserved throughout the simulation,
            ensuring that the total energy remains constant within tolerance.

        Mathematical Foundation:
            Checks: |E_final - E_initial| < tolerance

        Args:
            field (np.ndarray): Field data for energy calculation.
            energy (Optional[Dict[str, float]]): Energy data if available.
            metadata (Dict[str, Any]): Metadata containing initial energy.

        Returns:
            Dict[str, Any]: Energy conservation validation result.
        """
        try:
            tolerance = self.physical_constraints["energy_conservation_tolerance"]

            # Calculate current energy if not provided
            if energy is None:
                current_energy = self._calculate_field_energy(field)
            else:
                current_energy = energy.get("total", 0.0)

            # Get initial energy from metadata
            initial_energy = metadata.get("initial_energy", current_energy)

            # Check energy conservation
            energy_difference = abs(current_energy - initial_energy)
            energy_conserved = energy_difference < tolerance

            return {
                "valid": energy_conserved,
                "current_energy": float(current_energy),
                "initial_energy": float(initial_energy),
                "energy_difference": float(energy_difference),
                "tolerance": tolerance,
                "violations": (
                    []
                    if energy_conserved
                    else [
                        f"Energy not conserved: difference {energy_difference} > tolerance {tolerance}"
                    ]
                ),
            }

        except Exception as e:
            return {
                "valid": False,
                "current_energy": None,
                "initial_energy": None,
                "energy_difference": None,
                "tolerance": None,
                "violations": [f"Energy conservation validation error: {str(e)}"],
            }

    def validate_causality(
        self, field: np.ndarray, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate causality constraints.

        Physical Meaning:
            Validates that the field evolution respects causality,
            ensuring that information cannot propagate faster than light.

        Mathematical Foundation:
            Checks: |∇φ| ≤ c (speed of light constraint)

        Args:
            field (np.ndarray): Field data for causality check.
            metadata (Dict[str, Any]): Metadata containing speed of light.

        Returns:
            Dict[str, Any]: Causality validation result.
        """
        try:
            tolerance = self.physical_constraints["causality_tolerance"]
            speed_of_light = metadata.get("speed_of_light", 3e8)

            # Calculate field gradients
            gradients = self._calculate_field_gradients(field)
            max_gradient = np.max(np.abs(gradients))

            # Check causality
            causality_satisfied = max_gradient <= speed_of_light + tolerance

            return {
                "valid": causality_satisfied,
                "max_gradient": float(max_gradient),
                "speed_of_light": float(speed_of_light),
                "tolerance": tolerance,
                "violations": (
                    []
                    if causality_satisfied
                    else [
                        f"Causality violated: max gradient {max_gradient} > speed of light {speed_of_light}"
                    ]
                ),
            }

        except Exception as e:
            return {
                "valid": False,
                "max_gradient": None,
                "speed_of_light": None,
                "tolerance": None,
                "violations": [f"Causality validation error: {str(e)}"],
            }

    def validate_phase_coherence(
        self,
        field: np.ndarray,
        phase: Optional[np.ndarray],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Validate phase coherence.

        Physical Meaning:
            Validates that the phase field maintains sufficient coherence
            for physical validity according to 7D theory principles.

        Mathematical Foundation:
            Checks: |⟨exp(iφ)⟩| ≥ minimum_coherence

        Args:
            field (np.ndarray): Field data for coherence calculation.
            phase (Optional[np.ndarray]): Phase data if available.
            metadata (Dict[str, Any]): Metadata containing coherence requirements.

        Returns:
            Dict[str, Any]: Phase coherence validation result.
        """
        try:
            minimum_coherence = self.physical_constraints["phase_coherence_minimum"]

            # Calculate phase coherence
            if phase is not None:
                coherence = self._calculate_phase_coherence(phase)
            else:
                # Extract phase from field if complex
                if np.iscomplexobj(field):
                    phase = np.angle(field)
                    coherence = self._calculate_phase_coherence(phase)
                else:
                    coherence = 1.0  # Assume perfect coherence for real fields

            # Check coherence
            coherence_satisfied = coherence >= minimum_coherence

            return {
                "valid": coherence_satisfied,
                "coherence": float(coherence),
                "minimum_coherence": minimum_coherence,
                "warnings": (
                    []
                    if coherence_satisfied
                    else [
                        f"Phase coherence below minimum: {coherence} < {minimum_coherence}"
                    ]
                ),
            }

        except Exception as e:
            return {
                "valid": False,
                "coherence": None,
                "minimum_coherence": None,
                "warnings": [f"Phase coherence validation error: {str(e)}"],
            }

    def validate_7d_structure(
        self, field: np.ndarray, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate 7D structure preservation.

        Physical Meaning:
            Validates that the field maintains the 7D structure
            required by the phase field theory framework.

        Mathematical Foundation:
            Checks: field.ndim == 7 and field.shape == domain_shape

        Args:
            field (np.ndarray): Field data for structure validation.
            metadata (Dict[str, Any]): Metadata containing structure requirements.

        Returns:
            Dict[str, Any]: 7D structure validation result.
        """
        try:
            # Check dimensionality
            correct_dimensions = field.ndim == 7

            # Check shape
            correct_shape = field.shape == self.domain_shape

            # Check structure preservation
            structure_preserved = correct_dimensions and correct_shape

            return {
                "valid": structure_preserved,
                "field_dimensions": field.ndim,
                "required_dimensions": 7,
                "field_shape": field.shape,
                "required_shape": self.domain_shape,
                "violations": (
                    []
                    if structure_preserved
                    else [
                        (
                            f"Wrong dimensions: {field.ndim} != 7"
                            if not correct_dimensions
                            else ""
                        ),
                        (
                            f"Wrong shape: {field.shape} != {self.domain_shape}"
                            if not correct_shape
                            else ""
                        ),
                    ]
                ),
            }

        except Exception as e:
            return {
                "valid": False,
                "field_dimensions": None,
                "required_dimensions": 7,
                "field_shape": None,
                "required_shape": self.domain_shape,
                "violations": [f"7D structure validation error: {str(e)}"],
            }

    def validate_amplitude_bounds(
        self, field: np.ndarray, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate amplitude bounds.

        Physical Meaning:
            Validates that field amplitudes are within physically
            reasonable bounds according to the 7D theory framework.

        Mathematical Foundation:
            Checks: amplitude_min ≤ |field| ≤ amplitude_max

        Args:
            field (np.ndarray): Field data for amplitude validation.
            metadata (Dict[str, Any]): Metadata containing amplitude bounds.

        Returns:
            Dict[str, Any]: Amplitude bounds validation result.
        """
        try:
            amplitude_bounds = self.physical_constraints["amplitude_bounds"]
            min_amplitude, max_amplitude = amplitude_bounds

            # Calculate field amplitudes
            if np.iscomplexobj(field):
                amplitudes = np.abs(field)
            else:
                amplitudes = np.abs(field)

            min_amp = np.min(amplitudes)
            max_amp = np.max(amplitudes)

            # Check bounds
            within_bounds = (min_amp >= min_amplitude) and (max_amp <= max_amplitude)

            return {
                "valid": within_bounds,
                "min_amplitude": float(min_amp),
                "max_amplitude": float(max_amp),
                "required_min": min_amplitude,
                "required_max": max_amplitude,
                "violations": (
                    []
                    if within_bounds
                    else [
                        (
                            f"Amplitude below minimum: {min_amp} < {min_amplitude}"
                            if min_amp < min_amplitude
                            else ""
                        ),
                        (
                            f"Amplitude above maximum: {max_amp} > {max_amplitude}"
                            if max_amp > max_amplitude
                            else ""
                        ),
                    ]
                ),
            }

        except Exception as e:
            return {
                "valid": False,
                "min_amplitude": None,
                "max_amplitude": None,
                "required_min": None,
                "required_max": None,
                "violations": [f"Amplitude bounds validation error: {str(e)}"],
            }

    def validate_gradient_bounds(
        self, field: np.ndarray, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate gradient bounds.

        Physical Meaning:
            Validates that field gradients are within physically
            reasonable bounds according to the 7D theory framework.

        Mathematical Foundation:
            Checks: gradient_min ≤ |∇field| ≤ gradient_max

        Args:
            field (np.ndarray): Field data for gradient validation.
            metadata (Dict[str, Any]): Metadata containing gradient bounds.

        Returns:
            Dict[str, Any]: Gradient bounds validation result.
        """
        try:
            gradient_bounds = self.physical_constraints["gradient_bounds"]
            min_gradient, max_gradient = gradient_bounds

            # Calculate field gradients
            gradients = self._calculate_field_gradients(field)
            gradient_magnitudes = np.abs(gradients)

            min_grad = np.min(gradient_magnitudes)
            max_grad = np.max(gradient_magnitudes)

            # Check bounds
            within_bounds = (min_grad >= min_gradient) and (max_grad <= max_gradient)

            return {
                "valid": within_bounds,
                "min_gradient": float(min_grad),
                "max_gradient": float(max_grad),
                "required_min": min_gradient,
                "required_max": max_gradient,
                "violations": (
                    []
                    if within_bounds
                    else [
                        (
                            f"Gradient below minimum: {min_grad} < {min_gradient}"
                            if min_grad < min_gradient
                            else ""
                        ),
                        (
                            f"Gradient above maximum: {max_grad} > {max_gradient}"
                            if max_grad > max_gradient
                            else ""
                        ),
                    ]
                ),
            }

        except Exception as e:
            return {
                "valid": False,
                "min_gradient": None,
                "max_gradient": None,
                "required_min": None,
                "required_max": None,
                "violations": [f"Gradient bounds validation error: {str(e)}"],
            }

    def _calculate_field_energy(self, field: np.ndarray) -> float:
        """Calculate field energy."""
        if np.iscomplexobj(field):
            return float(np.sum(np.abs(field) ** 2))
        else:
            return float(np.sum(field**2))

    def _calculate_field_gradients(self, field: np.ndarray) -> np.ndarray:
        """Calculate field gradients."""
        gradients = []
        for axis in range(field.ndim):
            grad = np.gradient(field, axis=axis)
            gradients.append(grad)
        return np.array(gradients)

    def _calculate_phase_coherence(self, phase: np.ndarray) -> float:
        """Calculate phase coherence."""
        exp_phase = np.exp(1j * phase)
        coherence = np.abs(np.mean(exp_phase))
        return float(coherence)
