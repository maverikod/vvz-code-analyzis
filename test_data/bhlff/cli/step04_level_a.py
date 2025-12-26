"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Step 04 Level A test runner.

Runs Level A validation tests (A01–A05, A11–A12) with minimal parameters to
verify functionality and collects a simple summary.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, List


def _run_pytests(pytest_args: List[str]) -> int:
    import pytest  # local import to avoid hard dependency at import time

    return pytest.main(pytest_args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Level A validation tests")
    parser.add_argument(
        "--minimal",
        action="store_true",
        help="Run a minimal smoke subset (A01, A03) to verify functionality",
    )
    parser.add_argument(
        "--k",
        default="",
        help=("Pytest -k expression to filter tests (overrides --minimal)"),
    )
    parser.add_argument(
        "--maxfail",
        type=int,
        default=1,
        help="Stop after N failures (passed to pytest)",
    )
    return parser


def main(argv: Any = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    tests_root = Path("tests/unit/test_level_a")
    if not tests_root.exists():
        print(f"ERROR: tests folder not found: {tests_root}")
        return 1

    if args.k:
        pytest_args = [
            str(tests_root),
            "-k",
            args.k,
            "--maxfail",
            str(args.maxfail),
            "-q",
        ]
    elif args.minimal:
        # Run only two basic files explicitly
        pytest_args = [
            str(tests_root / "test_A01_plane_wave.py"),
            str(tests_root / "test_A03_zero_mode.py"),
            "--maxfail",
            str(args.maxfail),
            "-q",
        ]
    else:
        kexpr = "A01 or A02 or A03 or A04 or A05 or A11 or A12"
        pytest_args = [
            str(tests_root),
            "-k",
            kexpr,
            "--maxfail",
            str(args.maxfail),
            "-q",
        ]
    code = _run_pytests(pytest_args)
    return 0 if code == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
