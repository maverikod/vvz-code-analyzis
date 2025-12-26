"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Stability constraints helper for adaptive time integrators in 7D phase field theory.

Brief description of the module's purpose and its role in the 7D phase field theory.

Detailed description of the module's functionality, including:
- Physical meaning and theoretical background
- Key algorithms and methods implemented
- Dependencies and relationships with other modules
- Usage examples and typical workflows

Theoretical Background:
    This helper applies stability constraints to proposed time steps for
    fractional diffusion dynamics with operator L_β = ν(-Δ)^β + λ. It enforces
    a conservative CFL-like bound and mitigates high-frequency instabilities
    based on instantaneous error estimates.

Example:
    from bhlff.core.time.adaptive.stability import apply_stability_constraints
    dt = apply_stability_constraints(proposed_dt, error_estimate, tol, domain, params)
"""

from typing import Any
import numpy as np


def apply_stability_constraints(
    proposed_dt: float,
    error_estimate: float,
    tolerance: float,
    domain: Any,
    parameters: Any,
) -> float:
    """
    Apply stability constraints to proposed time step.

    Physical Meaning:
        Enforces a conservative time step bound for fractional diffusion
        dynamics to maintain numerical stability and accuracy, based on
        grid spacing, fractional order β, diffusion coefficient ν and
        current error behavior.

    Mathematical Foundation:
        For fractional diffusion, a CFL-like bound is used:
        dt ≤ C · Δx^(2β) / ν with conservative C = 0.1.

    Args:
        proposed_dt (float): Proposed time step size.
        error_estimate (float): Embedded method error estimate.
        tolerance (float): Target error tolerance.
        domain (Any): Computational domain with spacing information.
        parameters (Any): Physics parameters, expects .beta and .nu.

    Returns:
        float: Adjusted time step satisfying stability constraints.
    """
    adjusted_dt = proposed_dt

    if hasattr(parameters, "beta") and hasattr(parameters, "nu"):
        beta = float(parameters.beta)
        nu = float(parameters.nu)

        # Estimate characteristic grid spacing Δx
        if hasattr(domain, "dx"):
            dx = float(domain.dx)
        else:
            try:
                # If cubic isotropic grid is used
                dx = float(domain.L) / float(domain.N)
            except Exception:
                # Fallback: infer from shape along first axis
                dx = 1.0 / float(domain.shape[0] if hasattr(domain, "shape") else 128)

        # Conservative CFL-like constraint for fractional diffusion
        cfl_dt = 0.1 * (dx ** (2.0 * beta)) / max(nu, np.finfo(float).tiny)
        adjusted_dt = min(adjusted_dt, cfl_dt)

    # Spectral/high-frequency stability: reduce step if error is too large
    if error_estimate > tolerance * 10.0:
        adjusted_dt *= 0.5

    return adjusted_dt
