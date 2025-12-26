"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for time stability analyzer.

This module provides the base TimeStabilityAnalyzerBase class with common
initialization and main analysis methods.
"""

from typing import Dict, Any, List


class TimeStabilityAnalyzerBase:
    """
    Base class for time step stability analysis.
    
    Physical Meaning:
        Provides base functionality for investigating numerical stability
        of time integration schemes and optimal time step selection.
    """
    
    def __init__(self, reference_config: Dict[str, Any]):
        """
        Initialize time stability analyzer.
        
        Args:
            reference_config: Reference configuration for comparison
        """
        self.reference_config = reference_config
        self._setup_convergence_metrics()
    
    def _setup_convergence_metrics(self) -> None:
        """Setup metrics for convergence analysis."""
        self.convergence_metrics = [
            "power_law_exponent",
            "topological_charge",
            "energy",
            "quality_factor",
            "stability",
        ]
    
    def analyze_time_step_stability(self, time_steps: List[float]) -> Dict[str, Any]:
        """
        Analyze stability with respect to time step.
        
        Physical Meaning:
            Investigates numerical stability of time integration
            schemes and optimal time step selection.
            
        Args:
            time_steps: List of time steps to test
            
        Returns:
            Time step stability analysis
        """
        results = {}
        
        for dt in time_steps:
            print(f"Analyzing time step: {dt}")
            
            # Create configuration with specified time step
            config = self._create_time_step_config(dt)
            
            # Run simulation
            output = self._run_simulation(config)
            
            # Compute metrics
            metrics = self._compute_metrics(output)
            
            results[dt] = {"config": config, "output": output, "metrics": metrics}
        
        # Analyze time step stability
        stability_analysis = self._analyze_time_step_stability(results)
        
        return {"time_step_results": results, "stability_analysis": stability_analysis}
    
    def _create_time_step_config(self, dt: float) -> Dict[str, Any]:
        """Create configuration with specified time step."""
        config = self.reference_config.copy()
        config["dt"] = dt
        return config
    
    def _compute_metrics(self, output: Dict[str, Any]) -> Dict[str, float]:
        """Compute convergence metrics from simulation output."""
        metrics = {}
        
        for metric in self.convergence_metrics:
            if metric in output:
                metrics[metric] = output[metric]
        
        return metrics

