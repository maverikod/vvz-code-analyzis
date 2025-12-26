"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Step 03 demo: Time integrators for dynamic 7D BVP.

Runs a small demonstration of Crank-Nicolson or Adaptive integrator
using a tiny grid and a trivial source to validate wiring.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import numpy as np

from bhlff.core.domain import Domain, Parameters
from bhlff.core.time import CrankNicolsonIntegrator, AdaptiveIntegrator


def _load_config(path: Path) -> Dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Step 03 time integrators demo")
    parser.add_argument(
        "--config",
        type=Path,
        required=False,
        default=Path("configs/bvp_7d_config.json"),
    )
    parser.add_argument(
        "--integrator",
        choices=(
            "cn",
            "adaptive",
        ),
        default="cn",
    )
    parser.add_argument("--nt", type=int, default=64)
    parser.add_argument("--nx", type=int, default=32)
    return parser


def _make_domain(nx: int, nt: int, T: float) -> Domain:
    return Domain(L=1.0, N=nx, N_phi=8, N_t=nt, T=T)


def _make_parameters(cfg: Dict[str, Any]) -> Parameters:
    phys = cfg.get("physics", {})
    mu = float(phys.get("mu", 1.0))
    beta = float(phys.get("beta", 1.0))
    lam = float(phys.get("lambda", 0.0))
    nu = float(phys.get("nu", 1.0))
    return Parameters(mu=mu, beta=beta, lambda_param=lam, nu=nu)


def _build_integrator(name: str, domain: Domain, params: Parameters):
    if name == "cn":
        return CrankNicolsonIntegrator(domain, params)
    return AdaptiveIntegrator(domain, params)


def _prepare_fields(
    domain: Domain,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    """
    Prepare initial fields and sources for integration.
    
    Physical Meaning:
        Creates initial field configuration and time-dependent sources
        for phase field evolution, using FieldArray for automatic
        memory management of large 7D arrays.
    """
    from bhlff.core.arrays import FieldArray
    
    spatial_shape = (
        domain.N,
        domain.N,
        domain.N,
    )
    full_shape = domain.shape
    nt = domain.N_t

    # Initial field in full 7D shape (complex) - use FieldArray for automatic swap
    initial_field = FieldArray(shape=full_shape, dtype=np.complex128)
    initial = initial_field.array
    seed = np.zeros(spatial_shape, dtype=np.float64)
    seed[0, 0, 0] = 1.0
    # Broadcast seed across phase dims and initial time slice
    initial[:, :, :, :, :, :, 0] = 0.0 + 0.0j

    # Time points
    t = np.linspace(0.0, domain.T, nt)
    source_t = np.sin(2 * np.pi * t / max(domain.T, 1e-6))

    # Source over time: (nt,)+full_shape - use FieldArray for automatic swap
    source_over_time_field = FieldArray(shape=(nt,) + full_shape, dtype=np.complex128)
    source_over_time = source_over_time_field.array
    # Build a spatial source and broadcast over phase dims
    spatial_source_full_field = FieldArray(shape=full_shape, dtype=np.complex128)
    spatial_source_full = spatial_source_full_field.array
    spatial_source_full[0, 0, 0, :, :, :, :] = 1.0 + 0.0j
    for i in range(nt):
        source_over_time[i] = spatial_source_full * source_t[i]

    time_points = t.astype(np.float64)
    return initial, source_over_time, time_points


def main(argv: Any = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    cfg = _load_config(args.config)
    T = float(cfg.get("time", {}).get("T", 1.0))

    domain = _make_domain(nx=int(args.nx), nt=int(args.nt), T=T)
    params = _make_parameters(cfg)
    integrator = _build_integrator(args.integrator, domain, params)

    initial, source_time, time_points = _prepare_fields(domain)

    # Some integrators expect source per time step shape alignment
    result = integrator.integrate(initial, source_time, time_points)

    # Basic diagnostics
    final_field = result[-1]
    l2 = float(np.linalg.norm(final_field))
    print(
        "Step 03 demo finished: integrator="
        f"{args.integrator}, grid={args.nx}^3, nt={args.nt}, "
        f"L2(final)={l2:.6e}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
