"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for BVP source generators.

This module provides the base BVPSourceGeneratorsBase class with common
initialization and utility methods.
"""

from typing import Dict, Any

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except Exception:
    CUDA_AVAILABLE = False


class BVPSourceGeneratorsBase:
    """
    Base class for BVP source generators.
    
    Physical Meaning:
        Provides base functionality for generating different types of base sources
        that can be modulated by the BVP framework for phase field evolution.
    """
    
    def __init__(self, domain: "Domain", config: Dict[str, Any]) -> None:
        """
        Initialize BVP source generators.
        
        Args:
            domain: Computational domain for source generation.
            config: Source generator configuration.
        """
        self.domain = domain
        self.config = config
        use_cuda_flag = bool(config.get("use_cuda", True))  # CUDA required by default
        if use_cuda_flag and not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA is required for BVPSourceGenerators. "
                "Install cupy to enable GPU acceleration."
            )
        self.use_cuda = use_cuda_flag and CUDA_AVAILABLE
    
    def generate_base_source(self, source_type: str) -> 'FieldArray':
        """
        Generate base source of specified type.
        
        Physical Meaning:
            Generates a base source of the specified type for BVP modulation.
            
        Args:
            source_type: Type of source to generate.
            
        Returns:
            FieldArray: Base source field.
            
        Raises:
            ValueError: If source type is not supported.
        """
        if source_type == "gaussian":
            return self.generate_gaussian_source()
        elif source_type == "point":
            return self.generate_point_source()
        elif source_type == "distributed":
            return self.generate_distributed_source()
        elif source_type == "plane_wave":
            return self.generate_plane_wave_source()
        else:
            raise ValueError(f"Unsupported source type: {source_type}")
    
    def get_supported_source_types(self) -> list:
        """
        Get supported source types.
        
        Returns:
            list: Supported source types.
        """
        return ["gaussian", "point", "distributed", "plane_wave"]
    
    def get_source_info(self, source_type: str) -> Dict[str, Any]:
        """
        Get information about source type.
        
        Args:
            source_type: Source type to get information about.
            
        Returns:
            Dict[str, Any]: Source type information.
        """
        source_info = {
            "gaussian": {
                "description": "Gaussian source distribution",
                "formula": "s(x) = A * exp(-|x-x₀|²/σ²)",
                "parameters": [
                    "gaussian_amplitude",
                    "gaussian_center",
                    "gaussian_width",
                ],
            },
            "point": {
                "description": "Point source at specified location",
                "formula": "s(x) = A * δ(x-x₀)",
                "parameters": ["point_amplitude", "point_location"],
            },
            "distributed": {
                "description": "Distributed source with spatial distribution",
                "formula": "s(x) = A * f(x)",
                "parameters": ["distributed_amplitude", "distribution_type"],
            },
            "plane_wave": {
                "description": "Plane wave source with specified wave vector",
                "formula": "s(x) = A * exp(i * k · x)",
                "parameters": ["plane_wave_amplitude", "plane_wave_mode"],
            },
        }
        
        return source_info.get(source_type, {})

