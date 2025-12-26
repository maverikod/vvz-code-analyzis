"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Analysis methods for domain effects analyzer.

This module provides analysis methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any, List


class DomainEffectsAnalyzerAnalysisMixin:
    """Mixin providing analysis methods."""
    
    def analyze_domain_size_effects(self, domain_sizes: List[float]) -> Dict[str, Any]:
        """
        Analyze effects of finite domain size.
        
        Physical Meaning:
            Investigates how the finite computational domain
            affects results, particularly for long-range
            interactions and boundary effects.
        
        Args:
            domain_sizes: List of domain sizes to test
        
        Returns:
            Domain size analysis results
        """
        results = {}
        
        for domain_size in domain_sizes:
            print(f"Analyzing domain size: {domain_size}")
            
            # Create configuration with specified domain size
            config = self._create_domain_config(domain_size)
            
            # Run simulation
            output = self._run_simulation(config)
            
            # Compute metrics
            metrics = self._compute_metrics(output)
            
            results[domain_size] = {
                "config": config,
                "output": output,
                "metrics": metrics,
            }
        
        # Analyze domain size effects
        domain_analysis = self._analyze_domain_effects(results)
        
        return {"domain_results": results, "domain_analysis": domain_analysis}
    
    def _analyze_domain_effects(
        self, results: Dict[float, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze effects of domain size on results."""
        domain_sizes = sorted(results.keys())
        domain_effects = {}
        
        for metric in self.convergence_metrics:
            if metric in results[domain_sizes[0]]["metrics"]:
                # Extract values for this metric
                values = [
                    results[domain_size]["metrics"][metric]
                    for domain_size in domain_sizes
                ]
                
                # Analyze domain size dependence
                dependence = self._analyze_domain_dependence(domain_sizes, values)
                domain_effects[metric] = dependence
        
        # Overall domain size analysis
        overall_analysis = self._analyze_overall_domain_effects(domain_effects)
        
        return {
            "domain_effects": domain_effects,
            "overall_analysis": overall_analysis,
            "domain_sizes": domain_sizes,
        }
    
    def _analyze_domain_dependence(
        self, domain_sizes: List[float], values: List[float]
    ) -> Dict[str, Any]:
        """Analyze dependence of metric on domain size."""
        if len(values) < 2:
            return {"dependence": "insufficient_data", "slope": 0.0}
        
        # Compute slope of values vs domain size
        slope = np.polyfit(domain_sizes, values, 1)[0]
        
        # Assess dependence
        if abs(slope) < 0.01:
            dependence = "independent"
        elif abs(slope) < 0.1:
            dependence = "weak"
        elif abs(slope) < 1.0:
            dependence = "moderate"
        else:
            dependence = "strong"
        
        # Compute correlation safely
        try:
            correlation = np.corrcoef(domain_sizes, values)[0, 1]
            if np.isnan(correlation):
                correlation = 0.0
        except:
            correlation = 0.0
        
        return {"dependence": dependence, "slope": slope, "correlation": correlation}
    
    def _analyze_overall_domain_effects(
        self, domain_effects: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze overall domain size effects."""
        dependencies = [effects["dependence"] for effects in domain_effects.values()]
        
        # Count different types of dependence
        independent_count = dependencies.count("independent")
        weak_count = dependencies.count("weak")
        moderate_count = dependencies.count("moderate")
        strong_count = dependencies.count("strong")
        
        # Overall assessment
        if independent_count > len(dependencies) / 2:
            overall_dependence = "independent"
        elif weak_count > len(dependencies) / 2:
            overall_dependence = "weak"
        elif moderate_count > len(dependencies) / 2:
            overall_dependence = "moderate"
        else:
            overall_dependence = "strong"
        
        return {
            "overall_dependence": overall_dependence,
            "independent_count": independent_count,
            "weak_count": weak_count,
            "moderate_count": moderate_count,
            "strong_count": strong_count,
        }

