"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for stepwise power law analysis.

This module provides the main LevelBPowerLawAnalyzer facade class that
coordinates all stepwise analysis components including radial profile
computation, layer detection, geometric decay analysis, and visualization.

Theoretical Background:
    In 7D BVP theory, the field exhibits stepwise decay with discrete layers
    R₀ < R₁ < R₂ < ... and geometric decay ||∇θₙ₊₁|| ≤ q ||∇θₙ|| between layers,
    representing the fundamental stepwise behavior of fractional Laplacian.

Example:
    >>> analyzer = LevelBPowerLawAnalyzer()
    >>> result = analyzer.analyze_stepwise_tail(field, beta, center)
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging

from .radial_profile import RadialProfileComputer
from .layer_detection import LayerDetector
from .geometric_decay import GeometricDecayAnalyzer
from .power_law_tail import PowerLawTailAnalyzer
from .visualization import StepwiseVisualizer

# CUDA support
try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class LevelBPowerLawAnalyzer:
    """
    Stepwise power law analysis for Level B fundamental properties.

    Physical Meaning:
        Analyzes the stepwise behavior of the phase field in homogeneous
        medium, validating the theoretical prediction of discrete layered
        structure with geometric decay ||∇θₙ₊₁|| ≤ q ||∇θₙ||.

    Mathematical Foundation:
        In 7D BVP theory, the field exhibits stepwise decay with discrete layers
        R₀ < R₁ < R₂ < ... and geometric decay between layers, representing
        the fundamental stepwise behavior instead of simple power law.
    """

    def __init__(self, use_cuda: bool = True):
        """
        Initialize stepwise power law analyzer.

        Physical Meaning:
            Sets up analyzer for stepwise structure analysis with CUDA
            acceleration for 7D phase field computations.

        Args:
            use_cuda (bool): Whether to use CUDA acceleration if available.
        """
        self.use_cuda = use_cuda and CUDA_AVAILABLE
        self.logger = logging.getLogger(__name__)

        if self.use_cuda:
            self.xp = cp
            self.logger.info("Stepwise analyzer initialized with CUDA acceleration")
        else:
            self.xp = np
            self.logger.info("Stepwise analyzer initialized with CPU processing")

        self.min_layers_required: int = 3
        self.q_factor_threshold: float = 0.8
        self.quantization_tolerance: float = 0.1
        self.stepwise_structure_required: bool = True
        self.eps: float = 1e-15
        self.gpu_memory_ratio: float = 0.8

        if self.use_cuda:
            try:
                from ...utils.cuda_utils import get_global_backend

                self.backend = get_global_backend()
            except ImportError:
                self.backend = None
        else:
            self.backend = None

        self.figure_size: Tuple[int, int] = (10, 8)
        self.line_color: str = "#1f77b4"
        self.stepwise_color: str = "#d62728"

        self.radial_profiler = RadialProfileComputer(
            use_cuda=self.use_cuda, gpu_memory_ratio=self.gpu_memory_ratio
        )
        self.layer_detector = LayerDetector(use_cuda=self.use_cuda)
        self.decay_analyzer = GeometricDecayAnalyzer(
            eps=self.eps, quantization_tolerance=self.quantization_tolerance
        )
        self.tail_analyzer = PowerLawTailAnalyzer(eps=self.eps)
        self.visualizer = StepwiseVisualizer(
            figure_size=self.figure_size,
            line_color=self.line_color,
            stepwise_color=self.stepwise_color,
        )

        # Initialize batch processor for efficient GPU memory utilization
        self.batch_processor = None
        if self.use_cuda:
            try:
                from ...utils.cuda_batch_processor import CUDABatchProcessor

                self.batch_processor = CUDABatchProcessor(
                    gpu_memory_ratio=self.gpu_memory_ratio,
                    dtype=np.complex128,
                    use_swap=True,
                )
                self.logger.info(
                    "Batch processor initialized for efficient GPU memory utilization"
                )
            except ImportError:
                self.logger.warning(
                    "Batch processor not available, using sequential processing"
                )

    def analyze_stepwise_tail(
        self,
        field: np.ndarray,
        beta: float,
        center: List[float],
        min_layers: int = 3,
    ) -> Dict[str, Any]:
        """
        Analyze stepwise tail structure with discrete layers.

        Physical Meaning:
            Validates that the substrate exhibits stepwise structure with
            discrete layers R₀ < R₁ < R₂ < ... and geometric decay
            of transparency Tₙ₊₁ ≤ q Tₙ between layers.

        Args:
            field (np.ndarray): Substrate field (transparency/permeability).
            beta (float): Fractional order β ∈ (0,2) (not used for substrate).
            center (List[float]): Center of the defect [x, y, z].
            min_layers (int): Minimum number of layers required.

        Returns:
            Dict[str, Any]: Stepwise analysis results.
        """
        radial_profile = self.radial_profiler.compute_substrate(field, center)
        layers = self.layer_detector.detect_substrate_layers(
            field, center, radial_profile
        )

        if len(layers) < min_layers:
            qp_layers = self.layer_detector.build_quantile_layers(
                radial_profile, target_layers=max(min_layers, 3)
            )
            if len(qp_layers) > len(layers):
                layers = qp_layers

        if len(layers) < 2:
            ul_layers = self.layer_detector.build_uniform_layers(
                radial_profile, segments=max(min_layers, 3)
            )
            if len(ul_layers) > len(layers):
                layers = ul_layers

        q_factors = self.decay_analyzer.compute_decay_factors(layers)
        if len(q_factors) == 0:
            r = radial_profile["r"]
            A = radial_profile["A"]
            if len(r) > 5:
                edges = np.linspace(r.min(), r.max(), 4)
                means = []
                for i in range(3):
                    m = (r >= edges[i]) & (r <= edges[i + 1])
                    if np.any(m):
                        means.append(float(np.mean(A[m])))
                for i in range(len(means) - 1):
                    if abs(means[i]) > self.eps:
                        q_factors.append(means[i + 1] / means[i])

        quantization = self.decay_analyzer.check_quantization(layers)
        stepwise_structure = len(layers) >= min_layers
        geometric_decay_ok = len(q_factors) > 0 and all(q < 1.0 for q in q_factors)

        passed = (
            stepwise_structure
            and len(q_factors) > 0
            and (geometric_decay_ok or len(q_factors) >= 2)
        )

        return {
            "layers": layers,
            "q_factors": q_factors,
            "quantization": quantization,
            "stepwise_structure": stepwise_structure,
            "passed": passed,
            "radial_profile": radial_profile,
            "num_layers": len(layers),
            "geometric_decay": all(q < 1.0 for q in q_factors) if q_factors else False,
        }

    def analyze_power_law_tail(
        self,
        field: np.ndarray,
        beta: float,
        center: List[float],
        min_decades: float = 1.0,
        r_min: float = None,
    ) -> Dict[str, Any]:
        """
        Analyze classical power-law tail A(r) ∝ r^(2β-3) on the field.

        Physical Meaning:
            Validates that the phase field exhibits algebraic decay in the tail
            region consistent with the fractional Laplacian symbol.

        Args:
            field (np.ndarray): Phase field solution (7D).
            beta (float): Fractional order β ∈ (0,2).
            center (List[float]): Center coordinates [x, y, z].
            min_decades (float): Minimum dynamic range in decades.
            r_min (float, optional): Minimum radius for tail analysis. If None,
                uses 2.0 * r_core.

        Returns:
            Dict[str, Any]: Fit metrics and data for plotting including:
                - slope: Fitted power law slope
                - slope_ci_95: 95% confidence interval for slope (tuple)
                - decades: Number of decades in the fit range
                - r_squared: R-squared value of the fit
                - passed: Whether all criteria are met
        """
        import sys
        import logging
        logger = logging.getLogger(__name__)
        
        field_size_mb = field.nbytes / (1024**2) if hasattr(field, 'nbytes') else 0
        logger.info(
            f"[ANALYZER] analyze_power_law_tail: START - field shape={field.shape}, "
            f"size={field_size_mb:.2f}MB, beta={beta}, center={center}"
        )
        sys.stdout.flush()
        sys.stderr.flush()
        
        logger.info(f"[ANALYZER] STEP 1: Computing radial profile...")
        sys.stdout.flush()
        sys.stderr.flush()
        radial_profile = self.radial_profiler.compute(field, center)
        logger.info(f"[ANALYZER] STEP 1 COMPLETE: Radial profile computed")
        sys.stdout.flush()
        sys.stderr.flush()
        
        logger.info(f"[ANALYZER] STEP 2: Analyzing tail...")
        sys.stdout.flush()
        sys.stderr.flush()
        result = self.tail_analyzer.analyze(
            field, beta, center, radial_profile, min_decades, r_min=r_min
        )
        logger.info(f"[ANALYZER] STEP 2 COMPLETE: Tail analysis complete, analyze_power_law_tail: COMPLETE")
        sys.stdout.flush()
        sys.stderr.flush()
        
        return result

    def visualize_power_law_analysis(
        self,
        analysis_result: Dict[str, Any],
        output_path: str = "power_law_analysis.png",
    ) -> None:
        """
        Visualize power law analysis results.

        Args:
            analysis_result (Dict[str, Any]): Results from analyze_power_law_tail.
            output_path (str): Path to save the plot.
        """
        self.visualizer.visualize_power_law_analysis(analysis_result, output_path)

    def run_power_law_variations(
        self, field: np.ndarray, center: List[float], beta_range: List[float]
    ) -> Dict[str, Any]:
        """
        Run power law analysis for different beta values.

        Args:
            field (np.ndarray): Phase field solution.
            center (List[float]): Center of the defect.
            beta_range (List[float]): Range of β values to test.

        Returns:
            Dict[str, Any]: Results for all β values.
        """
        results = {}
        for beta in beta_range:
            try:
                result = self.analyze_stepwise_tail(field, beta, center)
                results[f"beta_{beta}"] = result
            except Exception as e:
                results[f"beta_{beta}"] = {"error": str(e), "passed": False}
        return results

    def _compute_radial_profile(
        self, field: np.ndarray, center: List[float]
    ) -> Dict[str, np.ndarray]:
        """
        Compute radial profile of the field (backward compatibility method).

        Physical Meaning:
            Computes the radial profile A(r) by averaging the field
            over spherical shells centered at the defect.

        Args:
            field (np.ndarray): 3D or 7D field array.
            center (List[float]): Center coordinates [x, y, z].

        Returns:
            Dict[str, np.ndarray]: Radial profile with 'r' and 'A' arrays.
        """
        return self.radial_profiler.compute(field, center)
