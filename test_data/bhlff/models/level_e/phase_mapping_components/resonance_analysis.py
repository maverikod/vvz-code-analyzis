"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Resonance analysis for phase mapping.

This module implements resonance analysis functionality
for classifying resonances as emergent vs fundamental
in 7D phase field theory.

Theoretical Background:
    Resonance analysis applies criteria to distinguish between
    emergent resonances (arising from interactions) and
    fundamental resonances (new particles).

Example:
    >>> analyzer = ResonanceAnalyzer()
    >>> classifications = analyzer.classify_resonances(resonance_data)
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple


class ResonanceAnalyzer:
    """
    Resonance analysis for classification.

    Physical Meaning:
        Analyzes resonances to distinguish between emergent
        and fundamental types based on universality, shape
        quality, and ecology criteria.
    """

    def __init__(self):
        """
        Initialize resonance analyzer.

        Physical Meaning:
            Sets up the analyzer for studying resonance
            classification in 7D phase field theory.
        """
        self.universality_threshold = 0.7
        self.shape_quality_threshold = 0.6
        self.ecology_threshold = 0.5
        self.fundamental_threshold = 0.7
        self.emergent_threshold = 0.4

    def classify_resonances(
        self, resonance_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Classify resonances as emergent vs fundamental.

        Physical Meaning:
            Applies criteria from 7d-00-18.md to distinguish between
            emergent resonances (arising from interactions) and
            fundamental resonances (new particles).
        """
        classifications = []

        for resonance in resonance_data:
            # Apply classification criteria
            universality = self._compute_universality(resonance)
            shape_quality = self._compute_shape_quality(resonance)
            ecology_score = self._compute_ecology_score(resonance)

            # Combine scores
            overall_score = (universality + shape_quality + ecology_score) / 3

            # Classify
            if overall_score > 0.7:
                classification = "fundamental"
            elif overall_score > 0.4:
                classification = "emergent"
            else:
                classification = "unclear"

            classifications.append(
                {
                    "resonance": resonance,
                    "universality": universality,
                    "shape_quality": shape_quality,
                    "ecology_score": ecology_score,
                    "overall_score": overall_score,
                    "classification": classification,
                }
            )

        return {
            "classifications": classifications,
            "summary": self._summarize_classifications(classifications),
        }

    def _compute_universality(self, resonance: Dict[str, Any]) -> float:
        """Compute universality score for resonance."""
        # Extract frequency and Q factor data
        frequencies = resonance.get("frequencies", [])
        q_factors = resonance.get("q_factors", [])

        if not frequencies or not q_factors:
            return 0.0

        # Compute coefficient of variation
        freq_cv = (
            np.std(frequencies) / np.mean(frequencies)
            if np.mean(frequencies) > 0
            else 1.0
        )
        q_cv = np.std(q_factors) / np.mean(q_factors) if np.mean(q_factors) > 0 else 1.0

        # Universality score
        universality = 1.0 / (1.0 + freq_cv + q_cv)

        return universality

    def _compute_shape_quality(self, resonance: Dict[str, Any]) -> float:
        """Compute shape quality score for resonance."""
        # Extract width and shape data
        widths = resonance.get("widths", [])
        shapes = resonance.get("shapes", [])

        if not widths or not shapes:
            return 0.0

        # Compute coefficient of variation
        width_cv = np.std(widths) / np.mean(widths) if np.mean(widths) > 0 else 1.0
        shape_cv = np.std(shapes) / np.mean(shapes) if np.mean(shapes) > 0 else 1.0

        # Shape quality score
        shape_quality = 1.0 / (1.0 + width_cv + shape_cv)

        return shape_quality

    def _compute_ecology_score(self, resonance: Dict[str, Any]) -> float:
        """Compute ecology score for resonance."""
        # Extract diversity and consistency data
        diversity = resonance.get("diversity", 0.5)
        consistency = resonance.get("consistency", 0.5)

        # Ecology score
        ecology_score = (diversity + consistency) / 2

        return ecology_score

    def _summarize_classifications(
        self, classifications: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Summarize classification results."""
        fundamental_count = sum(
            1 for c in classifications if c["classification"] == "fundamental"
        )
        emergent_count = sum(
            1 for c in classifications if c["classification"] == "emergent"
        )
        unclear_count = sum(
            1 for c in classifications if c["classification"] == "unclear"
        )

        total_count = len(classifications)

        return {
            "total_resonances": total_count,
            "fundamental_count": fundamental_count,
            "emergent_count": emergent_count,
            "unclear_count": unclear_count,
            "fundamental_percentage": fundamental_count / total_count * 100,
            "emergent_percentage": emergent_count / total_count * 100,
            "unclear_percentage": unclear_count / total_count * 100,
        }
