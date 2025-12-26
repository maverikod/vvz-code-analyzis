"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Field projection methods.

This module provides field projection methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class FieldProjectionProjectionsMixin:
    """Mixin providing field projection methods."""
    
    def project_em_field(self, field: np.ndarray) -> np.ndarray:
        """
        Project onto electromagnetic window.
        
        Physical Meaning:
            Extracts the electromagnetic component of the phase
            field, corresponding to U(1) gauge interactions
            and phase gradient flows.
        """
        return self._em_projector.project(field)
    
    def project_strong_field(self, field: np.ndarray) -> np.ndarray:
        """
        Project onto strong interaction window.
        
        Physical Meaning:
            Extracts the strong interaction component, corresponding
            to high-Q localized modes and steep amplitude gradients
            near the core.
        """
        return self._strong_projector.project(field)
    
    def project_weak_field(self, field: np.ndarray) -> np.ndarray:
        """
        Project onto weak interaction window.
        
        Physical Meaning:
            Extracts the weak interaction component, corresponding
            to chiral combinations and parity-breaking envelope
            functions with low Q and leakage.
        """
        return self._weak_projector.project(field)
    
    def project_field_windows(self, field: np.ndarray) -> Dict[str, Any]:
        """
        Project fields onto different frequency-amplitude windows.
        
        Physical Meaning:
            Separates the unified phase field into different
            interaction regimes based on frequency and amplitude
            characteristics.
        """
        self.logger.info("Projecting fields onto interaction windows")

        # Project onto each window
        em_projection = self.project_em_field(field)
        strong_projection = self.project_strong_field(field)
        weak_projection = self.project_weak_field(field)

        # Analyze field signatures
        signatures = self._signature_analyzer.analyze_field_signatures(
            {"em": em_projection, "strong": strong_projection, "weak": weak_projection}
        )

        results = {
            "em_projection": em_projection,
            "strong_projection": strong_projection,
            "weak_projection": weak_projection,
            "signatures": signatures,
        }

        self.logger.info("Field projection completed")
        return results
    
    def analyze_field_signatures(
        self, projections: Dict[str, np.ndarray]
    ) -> Dict[str, Any]:
        """
        Analyze characteristic signatures of each field type.
        
        Physical Meaning:
            Computes characteristic signatures for each interaction
            type, including localization, range, and anisotropy
            properties.
        """
        return self._signature_analyzer.analyze_field_signatures(projections)

