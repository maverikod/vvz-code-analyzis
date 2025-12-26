"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Command-line interface for quench detection in the BHLFF framework.

This module implements the `bhlff quench-detect` command that solves the
stationary 7D boundary value problem (BVP) for a specified configuration and
executes CUDA-accelerated quench detection. It provides detailed logging of
each stage, including solver runtime, quench detection passes, and accuracy
metrics, helping researchers analyse the birth of topological defects in the
Base High-frequency Landscape Field Framework.

Theoretical Background:
    Solves the BVP envelope equation in 7D space-time:
        ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x, φ, t)
    and applies quench detection thresholds for amplitude, detuning, and
    gradient criteria, indicating irreversible energy transfers into defect
    formation.

Example:
    >>> from bhlff.cli.quench_detect import main
    >>> main(["--config", "configs/level_a/A06_quench_detection.json", "--verbose"])
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np

from ..core.bvp.quench_detector import QuenchDetector
from ..core.domain.config import PhaseConfig, SpatialConfig, TemporalConfig
from ..core.domain.domain import Domain
from ..core.domain.domain_7d import Domain7D
from ..core.fft.fft_solver_7d_advanced import FFTSolver7DAdvanced


def _load_config(config_path: Path) -> Dict[str, Any]:
    """
    Load detection configuration from JSON file.

    Physical Meaning:
        Provides domain, physics, and quench parameters for solving the BVP
        envelope equation and applying quench thresholds.

    Args:
        config_path (Path): Path to configuration JSON.

    Returns:
        Dict[str, Any]: Parsed configuration dictionary.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def _create_neutralized_gaussian_7d(
    shape: Tuple[int, int, int, int, int, int, int],
    center: Tuple[float, float, float, float, float, float, float],
    sigma: float,
    domain_length: float,
) -> np.ndarray:
    """
    Create zero-mean Gaussian source in 7D space-time.

    Physical Meaning:
        Generates a localized perturbation in the spatial subspace of M₇ =
        ℝ³ₓ × 𝕋³_φ × ℝₜ with neutralized mean, suitable for λ = 0 regimes.
        Uses FieldArray for automatic memory management of large 7D arrays.

    Mathematical Foundation:
        s(x, φ, t) = g_σ(x) - ḡ where g_σ is spatial Gaussian and ḡ its mean.

    Args:
        shape (Tuple[int, ...]): Target 7D tensor shape.
        center (Tuple[float, ...]): Continuous centre coordinates.
        sigma (float): Gaussian width.
        domain_length (float): Spatial domain length.

    Returns:
        np.ndarray: Complex source tensor with zero mean (underlying array from FieldArray).
    """
    from bhlff.core.arrays import FieldArray
    
    n_spatial = shape[0]
    n_phase = shape[3]
    n_time = shape[6]

    grid = np.linspace(0.0, domain_length, n_spatial, endpoint=False)
    X, Y, Z = np.meshgrid(grid, grid, grid, indexing="ij")

    dx = X - center[0]
    dy = Y - center[1]
    dz = Z - center[2]
    r_sq = dx**2 + dy**2 + dz**2

    exponent = np.clip(-r_sq / (2.0 * sigma**2), -700.0, 700.0)
    gaussian = np.exp(exponent)
    gaussian -= np.mean(gaussian)

    # Use FieldArray for automatic swap management of large 7D arrays
    source_field = FieldArray(shape=shape, dtype=np.complex128)
    source = source_field.array
    for i_phi1 in range(n_phase):
        for i_phi2 in range(n_phase):
            for i_phi3 in range(n_phase):
                for i_t in range(n_time):
                    source[:, :, :, i_phi1, i_phi2, i_phi3, i_t] = gaussian

    return source


def _compute_gradient_magnitude_7d(field: np.ndarray, dx: float) -> np.ndarray:
    """
    Compute magnitude of spatial gradient for the envelope field.

    Physical Meaning:
        Evaluates |∇A| across spatial axes to assess gradient-based quench
        thresholds in the 7D phase field.

    Args:
        field (np.ndarray): Envelope field tensor.
        dx (float): Spatial step size.

    Returns:
        np.ndarray: Gradient magnitude tensor.
    """
    grad_x = np.gradient(field.real, dx, axis=0) + 1j * np.gradient(field.imag, dx, axis=0)
    grad_y = np.gradient(field.real, dx, axis=1) + 1j * np.gradient(field.imag, dx, axis=1)
    grad_z = np.gradient(field.real, dx, axis=2) + 1j * np.gradient(field.imag, dx, axis=2)
    return np.sqrt(np.abs(grad_x) ** 2 + np.abs(grad_y) ** 2 + np.abs(grad_z) ** 2)


def _configure_logging(verbose: bool) -> None:
    """
    Configure root logging level for CLI execution.

    Args:
        verbose (bool): When True, enable DEBUG level logging.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


def run_quench_detection(config: Dict[str, Any], output_dir: Path, logger: logging.Logger) -> Dict[str, Any]:
    """
    Execute stationary BVP solving and quench detection workflow.

    Physical Meaning:
        Solves the envelope equation for the provided configuration and
        evaluates quench thresholds to identify defect-forming events.

    Args:
        config (Dict[str, Any]): Configuration dictionary.
        output_dir (Path): Directory for saving diagnostic artefacts.
        logger (logging.Logger): Logger for progress reporting.

    Returns:
        Dict[str, Any]: Metrics and status information for the detection run.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    domain_length = float(config["domain"]["L"])
    grid_size = int(config["domain"]["N"])
    mu = float(config["physics"]["mu"])
    beta = float(config["physics"]["beta"])
    lambda_param = float(config["physics"]["lambda"])
    sigma = float(config["source"]["sigma"])
    centre = tuple(float(x) for x in config["source"]["center"])
    centre_7d = centre + (0.0, 0.0, 0.0, 0.0)

    amplitude_threshold = float(config["quench"]["amplitude_threshold"])
    detuning_threshold = float(config["quench"]["detuning_threshold"])
    gradient_threshold = float(config["quench"]["gradient_threshold"])

    tolerance_detection = float(config["tolerance"]["detection_accuracy"])
    tolerance_stability = float(config["tolerance"]["map_stability"])

    n_phase = 2
    n_time = 2
    shape_7d = (grid_size, grid_size, grid_size, n_phase, n_phase, n_phase, n_time)
    dx = domain_length / grid_size

    logger.info(
        "Preparing neutralized Gaussian source (N=%d, sigma=%.4f)",
        grid_size,
        sigma,
    )
    source_start = time.perf_counter()
    source_7d = _create_neutralized_gaussian_7d(shape_7d, centre_7d, sigma, domain_length)
    logger.info(
        "Source generated in %.2fs (min=%.3e, max=%.3e)",
        time.perf_counter() - source_start,
        float(np.min(source_7d.real)),
        float(np.max(source_7d.real)),
    )

    domain = Domain(
        L=domain_length,
        N=grid_size,
        N_phi=n_phase,
        N_t=n_time,
        T=1.0,
        dimensions=7,
    )

    solver_params = {"mu": mu, "beta": beta, "lambda": lambda_param}
    logger.info("Solving stationary BVP with FFTSolver7DAdvanced: %s", solver_params)
    solver = FFTSolver7DAdvanced(domain, solver_params)
    solve_start = time.perf_counter()
    envelope = solver.solve_stationary(source_7d)
    solve_elapsed = time.perf_counter() - solve_start
    logger.info(
        "Stationary solve completed in %.2fs (max|a|=%.5f)",
        solve_elapsed,
        float(np.max(np.abs(envelope))),
    )

    spatial_config = SpatialConfig(
        L_x=domain_length,
        L_y=domain_length,
        L_z=domain_length,
        N_x=grid_size,
        N_y=grid_size,
        N_z=grid_size,
    )
    phase_config = PhaseConfig(N_phi_1=n_phase, N_phi_2=n_phase, N_phi_3=n_phase)
    temporal_config = TemporalConfig(T_max=1.0, N_t=n_time)
    domain_7d = Domain7D(spatial_config, phase_config, temporal_config)

    detector_config = {
        "amplitude_threshold": amplitude_threshold,
        "detuning_threshold": detuning_threshold,
        "gradient_threshold": gradient_threshold,
        "carrier_frequency": 1.0,
    }
    logger.info("Initialising QuenchDetector with config %s", detector_config)
    detector = QuenchDetector(domain_7d, detector_config)

    detection_start = time.perf_counter()
    results_1 = detector.detect_quenches(envelope)
    detection_time_1 = time.perf_counter() - detection_start
    logger.info(
        "Detection pass #1 completed in %.2fs (detected=%s, count=%d)",
        detection_time_1,
        results_1.get("quenches_detected"),
        len(results_1.get("quench_locations", [])),
    )

    gradient_start = time.perf_counter()
    gradient_magnitude = _compute_gradient_magnitude_7d(envelope, dx)
    logger.info(
        "Gradient magnitude evaluated in %.2fs (max=%.5f)",
        time.perf_counter() - gradient_start,
        float(np.max(gradient_magnitude)),
    )

    envelope_amplitude = np.abs(envelope[:, :, :, 0, 0, 0, 0])
    gradient_slice = (
        gradient_magnitude[:, :, :, 0, 0, 0, 0]
        if gradient_magnitude.ndim == 7
        else gradient_magnitude
    )

    amplitude_mask = envelope_amplitude > amplitude_threshold
    gradient_mask = gradient_slice > gradient_threshold
    logger.info(
        "Amplitude threshold exceedances: %d | Gradient threshold exceedances: %d",
        int(np.sum(amplitude_mask)),
        int(np.sum(gradient_mask)),
    )

    detection_start = time.perf_counter()
    results_2 = detector.detect_quenches(envelope)
    detection_time_2 = time.perf_counter() - detection_start
    logger.info(
        "Detection pass #2 completed in %.2fs (count=%d)",
        detection_time_2,
        len(results_2.get("quench_locations", [])),
    )

    amp_locations = {
        (int(loc[0]), int(loc[1]), int(loc[2]))
        for loc in results_1.get("amplitude_quenches", [])
        if len(loc) >= 3
    }
    grad_locations = {
        (int(loc[0]), int(loc[1]), int(loc[2]))
        for loc in results_1.get("gradient_quenches", [])
        if len(loc) >= 3
    }

    amplitude_expected = int(np.sum(amplitude_mask))
    gradient_expected = int(np.sum(gradient_mask))

    accuracy_amp = (
        1.0
        if amplitude_expected == 0 and not amp_locations
        else len(amp_locations) / max(amplitude_expected, 1)
    )
    accuracy_grad = (
        1.0
        if gradient_expected == 0 and not grad_locations
        else len(grad_locations) / max(gradient_expected, 1)
    )

    total_1 = len(results_1.get("quench_locations", []))
    total_2 = len(results_2.get("quench_locations", []))
    stability = 1.0 if total_1 == 0 else abs(total_1 - total_2) / max(total_1, 1)

    status = (
        "PASS"
        if (accuracy_amp >= tolerance_detection or amplitude_expected == 0)
        and (accuracy_grad >= tolerance_detection or gradient_expected == 0)
        and stability <= tolerance_stability
        else "FAIL"
    )

    logger.info(
        "Detection summary: status=%s | accuracy_amp=%.3f | accuracy_grad=%.3f | stability=%.3f",
        status,
        accuracy_amp,
        accuracy_grad,
        stability,
    )

    np.save(output_dir / "envelope_amplitude.npy", envelope_amplitude)
    np.save(output_dir / "gradient_magnitude.npy", gradient_slice)

    quench_map = np.zeros((grid_size, grid_size, grid_size), dtype=float)
    for loc in results_1.get("quench_locations", []):
        if len(loc) >= 3:
            i, j, k = int(loc[0]), int(loc[1]), int(loc[2])
            if 0 <= i < grid_size and 0 <= j < grid_size and 0 <= k < grid_size:
                quench_map[i, j, k] = 1.0
    np.save(output_dir / "quench_map.npy", quench_map)

    metrics = {
        "status": status,
        "tolerance_detection": tolerance_detection,
        "tolerance_stability": tolerance_stability,
        "accuracy_amplitude": float(accuracy_amp),
        "accuracy_gradient": float(accuracy_grad),
        "stability": float(stability),
        "amplitude_expected": amplitude_expected,
        "gradient_expected": gradient_expected,
        "detected_quenches_pass1": total_1,
        "detected_quenches_pass2": total_2,
        "solve_time_seconds": float(solve_elapsed),
        "detection_time_pass1": detection_time_1,
        "detection_time_pass2": detection_time_2,
    }

    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return metrics


def build_parser() -> argparse.ArgumentParser:
    """
    Build argument parser for the CLI command.

    Returns:
        argparse.ArgumentParser: Configured parser.
    """
    parser = argparse.ArgumentParser(description="Run BHLFF quench detection command")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/level_a/A06_quench_detection.json"),
        help="Path to quench detection configuration JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Directory to store outputs (defaults to output/<test_id>)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser


def main(argv: Any = None) -> int:
    """
    CLI entry point for quench detection.

    Args:
        argv (Any, optional): Command-line arguments. Defaults to None.

    Returns:
        int: Exit status (0 on success, 1 on failure).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)
    logger = logging.getLogger("bhlff.cli.quench_detect")

    config = _load_config(args.config)
    output_dir = args.output or Path("output") / str(config.get("test_id", "quench_detection"))

    metrics = run_quench_detection(config, output_dir, logger)
    return 0 if metrics["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


