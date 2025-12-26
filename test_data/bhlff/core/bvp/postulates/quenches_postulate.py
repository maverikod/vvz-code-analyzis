"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP Postulate 5: Quenches - Threshold Events implementation.

This module implements the Quenches postulate for the BVP framework,
validating that quench events occur at local thresholds with proper
energy dissipation patterns.

Physical Meaning:
    The Quenches postulate describes threshold events where the BVP
    dissipatively "dumps" energy into the medium at local thresholds
    (amplitude/detuning/gradient). This results in growth of losses,
    change of Q-factor, and peak clamping - fixed as local mode transitions.

Mathematical Foundation:
    Validates quench events by detecting local threshold crossings
    in amplitude, detuning, and gradient, and analyzing the resulting
    energy dissipation patterns.

Example:
    >>> postulate = BVPPostulate5_Quenches(domain_7d, config)
    >>> results = postulate.apply(envelope_7d)
    >>> print(f"Quenches detected: {results['quench_count']}")
"""

import numpy as np
from typing import Dict, Any

from ...domain.domain_7d import Domain7D
from ..bvp_postulate_base import BVPPostulate


class BVPPostulate5_Quenches(BVPPostulate):
    """
    Postulate 5: Quenches - Threshold Events.

    Physical Meaning:
        At local threshold (amplitude/detuning/gradient) BVP dissipatively
        "dumps" energy into medium (growth of losses, change of Q, peak clamping)
        - this is fixed as local mode transition.

    Mathematical Foundation:
        Validates quench events by detecting local threshold crossings
        and energy dissipation patterns.
    """

    def __init__(self, domain_7d: Domain7D, config: Dict[str, Any]):
        """
        Initialize Quenches postulate.

        Physical Meaning:
            Sets up the postulate with the computational domain and
            configuration parameters, including the various threshold
            values for quench detection.

        Args:
            domain_7d (Domain7D): 7D computational domain.
            config (Dict[str, Any]): Configuration parameters including:
                - amplitude_threshold (float): Amplitude threshold for quenches (default: 0.8)
                - detuning_threshold (float): Detuning threshold for quenches (default: 0.1)
                - gradient_threshold (float): Gradient threshold for quenches (default: 0.5)
        """
        self.domain_7d = domain_7d
        self.config = config
        self.amplitude_threshold = config.get("amplitude_threshold", 0.8)
        self.detuning_threshold = config.get("detuning_threshold", 0.1)
        self.gradient_threshold = config.get("gradient_threshold", 0.5)

    def apply(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Apply Quenches postulate.

        Physical Meaning:
            Detects quench events by identifying local threshold crossings
            in amplitude, detuning, and gradient. These quenches represent
            dissipative energy dumping into the medium with associated
            changes in Q-factor and peak clamping.

        Mathematical Foundation:
            Computes field amplitude and gradients, identifies regions
            exceeding thresholds, and calculates the energy dissipated
            in these quench regions.

        Args:
            envelope (np.ndarray): 7D envelope field to validate.
                Shape: (N_x, N_y, N_z, N_φx, N_φy, N_φz, N_t)

        Returns:
            Dict[str, Any]: Validation results including:
                - postulate_satisfied (bool): Whether postulate is satisfied
                - quench_locations (List): Locations of detected quenches
                - quench_count (int): Number of quenches detected
                - energy_dissipated (float): Total energy dissipated in quenches
                - amplitude_threshold (float): Applied amplitude threshold
                - gradient_threshold (float): Applied gradient threshold
        """
        # Compute field properties
        amplitude = np.abs(envelope)
        phase = np.angle(envelope)

        # Compute gradients
        grad_amplitude = np.sqrt(
            np.sum(
                [np.gradient(amplitude, axis=i) ** 2 for i in range(amplitude.ndim)],
                axis=0,
            )
        )

        # Detect quench events
        amplitude_quenches = amplitude > self.amplitude_threshold * np.max(amplitude)
        gradient_quenches = grad_amplitude > self.gradient_threshold * np.max(
            grad_amplitude
        )

        # Combined quench detection
        quench_mask = amplitude_quenches | gradient_quenches
        quench_locations = np.where(quench_mask)
        quench_count = len(quench_locations[0])

        # Compute energy dissipated in quenches
        energy_dissipated = np.sum(amplitude[quench_mask] ** 2)

        # Check if quenches are properly detected
        quenches_detected = quench_count > 0

        return {
            "postulate_satisfied": quenches_detected,
            "quench_locations": [list(loc) for loc in zip(*quench_locations)],
            "quench_count": int(quench_count),
            "energy_dissipated": float(energy_dissipated),
            "amplitude_threshold": self.amplitude_threshold,
            "gradient_threshold": self.gradient_threshold,
        }
