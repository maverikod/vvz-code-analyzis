"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

I/O utilities for failure detector.

This module provides serialization helpers for failure detection results.
"""

import json
from typing import Any, Dict


class FailureDetectorIOMixin:
    """Mixin providing result serialization utilities."""
    
    def save_results(self, results: Dict[str, Any], filename: str) -> None:
        """
        Save failure detection results to file.
        
        Args:
            results: Detection results dictionary
            filename: Output filename
        """
        serializable_results = self._make_serializable(results)
        
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(serializable_results, file, indent=2)
    
    def _make_serializable(self, obj: Any) -> Any:
        """Convert numpy arrays to lists for JSON serialization."""
        try:
            import numpy as np
        except ImportError:  # pragma: no cover - numpy is project dependency
            np = None  # type: ignore
        
        if np is not None and isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {key: self._make_serializable(value) for key, value in obj.items()}
        if isinstance(obj, list):
            return [self._make_serializable(item) for item in obj]
        return obj
