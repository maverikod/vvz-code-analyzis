"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Topological charge analyzer for Level B BVP interface.

This module implements analysis of topological charge of defects in the BVP
envelope for the Level B BVP interface, computing winding numbers and
topological characteristics.

Physical Meaning:
    Calculates the topological charge of defects in the BVP envelope
    using the winding number around closed loops in the field, which
    characterizes the topological structure of the field configuration.

Mathematical Foundation:
    Computes topological charge using circulation of phase gradients
    around closed loops, representing the winding number of the field
    phase around topological defects.

Example:
    >>> analyzer = TopologicalChargeAnalyzer()
    >>> charge_data = analyzer.compute_topological_charge(envelope)
"""

import numpy as np
from typing import Dict, Any


class TopologicalChargeAnalyzer:
    """
    Topological charge analyzer for Level B BVP interface.

    Physical Meaning:
        Calculates the topological charge of defects in the BVP envelope
        using the winding number around closed loops in the field, which
        characterizes the topological structure of the field configuration.

    Mathematical Foundation:
        Computes topological charge using circulation of phase gradients
        around closed loops, representing the winding number of the field
        phase around topological defects.
    """

    def compute_topological_charge(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Compute topological charge of defects.

        Physical Meaning:
            Calculates the topological charge of defects in the BVP envelope
            using the winding number around closed loops in the field.

        Mathematical Foundation:
            Computes circulation of phase gradients around small loops
            and converts to topological charge using winding number formula.

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            Dict[str, Any]: Dictionary containing:
                - topological_charge: Total topological charge
                - charge_locations: List of charge locations
                - charge_stability: Stability measure of charges
        """
        # Convert to complex field for phase analysis
        if np.iscomplexobj(envelope):
            field = envelope
        else:
            # Create complex field from real envelope
            field = envelope.astype(complex)

        # Compute phase field
        phase = np.angle(field)

        # Find phase singularities (defects)
        # Compute phase gradients
        grad_phase_x = np.gradient(phase, axis=0)
        grad_phase_y = np.gradient(phase, axis=1)
        grad_phase_z = np.gradient(phase, axis=2)

        # Handle phase wrapping
        grad_phase_x = np.unwrap(grad_phase_x, axis=0)
        grad_phase_y = np.unwrap(grad_phase_y, axis=1)
        grad_phase_z = np.unwrap(grad_phase_z, axis=2)

        # Compute winding number around each point
        # For 3D, we compute the circulation around small loops
        charge_locations = []
        total_charge = 0.0

        # Sample points for charge detection
        step = max(1, min(envelope.shape) // 16)  # Adaptive sampling
        for i in range(step, envelope.shape[0] - step, step):
            for j in range(step, envelope.shape[1] - step, step):
                for k in range(step, envelope.shape[2] - step, step):
                    # Compute circulation around small loop
                    try:
                        # 2D circulation in xy plane
                        circulation_xy = (
                            grad_phase_x[i + 1, j, k]
                            - grad_phase_x[i - 1, j, k]
                            + grad_phase_y[i, j + 1, k]
                            - grad_phase_y[i, j - 1, k]
                        )

                        # 2D circulation in xz plane
                        circulation_xz = (
                            grad_phase_x[i + 1, j, k]
                            - grad_phase_x[i - 1, j, k]
                            + grad_phase_z[i, j, k + 1]
                            - grad_phase_z[i, j, k - 1]
                        )

                        # 2D circulation in yz plane
                        circulation_yz = (
                            grad_phase_y[i, j + 1, k]
                            - grad_phase_y[i, j - 1, k]
                            + grad_phase_z[i, j, k + 1]
                            - grad_phase_z[i, j, k - 1]
                        )

                        # Average circulation as charge estimate
                        circulation = (
                            circulation_xy + circulation_xz + circulation_yz
                        ) / 3.0

                        # Convert to topological charge (winding number)
                        charge = circulation / (2 * np.pi)

                        # Threshold for significant charge
                        if abs(charge) > 0.1:
                            charge_locations.append((i, j, k))
                            total_charge += charge

                    except (IndexError, ValueError):
                        continue

        # Compute charge stability (how well-defined the charges are)
        if len(charge_locations) > 0:
            # Stability based on charge magnitude and spatial distribution
            charge_magnitudes = [abs(total_charge / len(charge_locations))] * len(
                charge_locations
            )
            charge_stability = min(1.0, np.mean(charge_magnitudes))
        else:
            charge_stability = 0.0

        return {
            "topological_charge": float(total_charge),
            "charge_locations": charge_locations,
            "charge_stability": float(charge_stability),
        }

    def analyze_phase_structure(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze phase structure of the field.

        Physical Meaning:
            Analyzes the phase structure of the BVP envelope to understand
            the topological characteristics and phase coherence.

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            Dict[str, Any]: Dictionary containing phase structure analysis.
        """
        # Convert to complex field for phase analysis
        if np.iscomplexobj(envelope):
            field = envelope
        else:
            field = envelope.astype(complex)

        # Compute phase field
        phase = np.angle(field)
        amplitude = np.abs(field)

        # Compute phase gradients
        grad_phase_x = np.gradient(phase, axis=0)
        grad_phase_y = np.gradient(phase, axis=1)
        grad_phase_z = np.gradient(phase, axis=2)

        # Handle phase wrapping
        grad_phase_x = np.unwrap(grad_phase_x, axis=0)
        grad_phase_y = np.unwrap(grad_phase_y, axis=1)
        grad_phase_z = np.unwrap(grad_phase_z, axis=2)

        # Compute phase gradient magnitude
        grad_phase_magnitude = np.sqrt(
            grad_phase_x**2 + grad_phase_y**2 + grad_phase_z**2
        )

        # Analyze phase coherence
        phase_coherence = np.mean(np.cos(phase))  # Average coherence
        phase_variance = np.var(phase)  # Phase variance

        # Analyze phase gradient statistics
        grad_mean = np.mean(grad_phase_magnitude)
        grad_std = np.std(grad_phase_magnitude)
        grad_max = np.max(grad_phase_magnitude)

        # Find regions of high phase gradient (potential defects)
        high_grad_threshold = grad_mean + 2 * grad_std
        high_grad_regions = grad_phase_magnitude > high_grad_threshold
        high_grad_fraction = np.sum(high_grad_regions) / high_grad_regions.size

        return {
            "phase_coherence": float(phase_coherence),
            "phase_variance": float(phase_variance),
            "gradient_mean": float(grad_mean),
            "gradient_std": float(grad_std),
            "gradient_max": float(grad_max),
            "high_gradient_fraction": float(high_grad_fraction),
        }
