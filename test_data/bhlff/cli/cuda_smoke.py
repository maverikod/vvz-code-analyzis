"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CLI: CUDA smoke test for Level E modules.

Run a small GPU-backed total energy computation to validate CUDA environment.

Example:
    bhlff-cuda-smoke --N 8 --phi 8 --t 8 -v
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any, Dict

import numpy as np


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="BHLFF CUDA smoke test")
    p.add_argument("--N", type=int, default=8, help="Spatial grid size per axis")
    p.add_argument("--phi", type=int, default=8, help="Phase grid size per axis")
    p.add_argument("--t", type=int, default=8, help="Temporal grid size")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logs")
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("bhlff.cuda_smoke")

    sys.path.insert(0, ".")

    try:
        import cupy as cp

        cuda_ok = cp.cuda.is_available()
        dev_count = cp.cuda.runtime.getDeviceCount() if cuda_ok else 0
        mem_info = cp.cuda.Device(0).mem_info if cuda_ok else (0, 0)
        logger.info(
            "CuPy: %s | CUDA available: %s | devices: %s",
            cp.__version__,
            cuda_ok,
            dev_count,
        )
        if not cuda_ok:
            print("[ERROR] CUDA not available in current environment.")
            return 2
        logger.info("GPU[0] mem (free,total) bytes: %s", mem_info)
    except Exception as e:
        print(f"[ERROR] CuPy initialization failed: {e}")
        return 2

    try:
        from bhlff.core.domain import Domain
        from bhlff.models.level_e.cuda import SolitonEnergyCalculatorCUDA
    except Exception as e:
        print(f"[ERROR] Project imports failed: {e}")
        return 2

    N = int(args.N)
    N_phi = int(args.phi)
    N_t = int(args.t)

    domain = Domain(L=1.0, N=N, dimensions=7, N_phi=N_phi, N_t=N_t, T=1.0)
    params: Dict[str, Any] = {
        "mu": 1.0,
        "beta": 1.0,
        "lambda": 0.1,
        "S4": 0.1,
        "S6": 0.01,
        "F2": 1.0,
        "N_c": 3,
    }

    print("[INFO] Creating small synthetic 7D field...")
    rng = np.random.default_rng(42)
    shape = (N, N, N, N_phi, N_phi, N_phi, N_t)
    field = (rng.standard_normal(shape) + 1j * rng.standard_normal(shape)).astype(
        np.complex128
    )

    print("[INFO] Initializing CUDA energy calculator (with block processing)...")
    calc = SolitonEnergyCalculatorCUDA(domain, params, use_cuda=True)

    print("[INFO] Computing total energy (verbose logs enabled with -v)...")
    total_energy = calc.compute_total_energy(field)
    print(f"[RESULT] Total energy: {float(total_energy):.6e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
