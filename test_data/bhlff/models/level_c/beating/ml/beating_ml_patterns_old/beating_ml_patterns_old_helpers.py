"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Helper methods for beating ML patterns old.

This module provides helper methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class BeatingMLPatternsOldHelpersMixin:
    """Mixin providing helper methods."""
    
    def _load_trained_pattern_classifier(self):
        """
        Load trained pattern classifier model.
        
        Physical Meaning:
            Loads pre-trained Random Forest classifier for pattern classification
            based on 7D phase field theory.
            
        Returns:
            Trained classifier model or None if not available.
        """
        try:
            import pickle
            import os
            
            model_path = "models/ml/beating/pattern_classifier.pkl"
            if os.path.exists(model_path):
                with open(model_path, "rb") as f:
                    model_data = pickle.load(f)
                    return model_data["model"]
            return None
        except Exception as e:
            self.logger.warning(f"Failed to load pattern classifier: {e}")
            return None
    
    def _load_pattern_scaler(self):
        """
        Load pattern feature scaler.
        
        Physical Meaning:
            Loads feature scaler for pattern classification features.
            
        Returns:
            Trained scaler or default scaler.
        """
        try:
            import pickle
            import os
            from sklearn.preprocessing import StandardScaler
            
            scaler_path = "models/ml/beating/pattern_scaler.pkl"
            if os.path.exists(scaler_path):
                with open(scaler_path, "rb") as f:
                    scaler_data = pickle.load(f)
                    return scaler_data["scaler"]
            return StandardScaler()
        except Exception as e:
            self.logger.warning(f"Failed to load pattern scaler: {e}")
            return StandardScaler()
    
    def _extract_ml_pattern_features(self, features: Dict[str, Any]) -> np.ndarray:
        """
        Extract ML features for pattern classification.
        
        Physical Meaning:
            Extracts comprehensive features for ML pattern classification
            based on 7D phase field theory.
            
        Args:
            features (Dict[str, Any]): Input features dictionary.
            
        Returns:
            np.ndarray: ML features array.
        """
        spatial = features["spatial_features"]
        frequency = features["frequency_features"]
        pattern = features["pattern_features"]
        
        # Extract comprehensive ML features
        ml_features = [
            spatial.get("symmetry_score", 0.0),
            spatial.get("regularity_score", 0.0),
            spatial.get("complexity_score", 0.0),
            frequency.get("spectral_entropy", 0.0),
            frequency.get("frequency_spacing", 0.0),
            frequency.get("frequency_bandwidth", 0.0),
            pattern.get("symmetry_score", 0.0),
            pattern.get("regularity_score", 0.0),
            pattern.get("complexity_score", 0.0),
            pattern.get("coherence_score", 0.0),
            pattern.get("stability_score", 0.0),
        ]
        
        return np.array(ml_features)
    
    def _get_pattern_feature_importance(self, model) -> Dict[str, float]:
        """
        Get feature importance from pattern classifier.
        
        Physical Meaning:
            Extracts feature importance from trained pattern classifier
            to understand which features are most relevant.
            
        Args:
            model: Trained pattern classifier.
            
        Returns:
            Dict[str, float]: Feature importance dictionary.
        """
        try:
            if hasattr(model, "feature_importances_"):
                feature_names = [
                    "spatial_symmetry",
                    "spatial_regularity",
                    "spatial_complexity",
                    "spectral_entropy",
                    "frequency_spacing",
                    "frequency_bandwidth",
                    "pattern_symmetry",
                    "pattern_regularity",
                    "pattern_complexity",
                    "coherence_score",
                    "stability_score",
                ]
                importance_dict = {}
                for i, name in enumerate(feature_names):
                    if i < len(model.feature_importances_):
                        importance_dict[name] = float(model.feature_importances_[i])
                return importance_dict
            else:
                return {"default": 1.0}
        except Exception:
            return {"default": 1.0}
    
    def _compute_topological_charge(self, envelope: np.ndarray) -> float:
        """
        Compute topological charge using 7D phase field theory.
        
        Physical Meaning:
            Computes topological charge based on 7D phase field theory.
        """
        # Compute phase gradient
        phase = np.angle(envelope)
        grad_x = np.gradient(phase, axis=1)
        grad_y = np.gradient(phase, axis=0)
        
        # Compute topological charge
        topological_charge = np.sum(grad_x * grad_y) / (2 * np.pi)
        
        return float(topological_charge)
    
    def _compute_energy_symmetry(self, energy_density: np.ndarray) -> float:
        """
        Compute energy density symmetry.
        
        Physical Meaning:
            Computes energy density symmetry based on spatial distribution.
        """
        # Compute energy density symmetry using spatial correlation
        center = energy_density.shape[0] // 2
        left_half = energy_density[:center]
        right_half = energy_density[center:]
        
        if left_half.shape != right_half.shape:
            return 0.5
        
        correlation = np.corrcoef(left_half.flatten(), right_half.flatten())[0, 1]
        return max(0.0, min(1.0, correlation))

