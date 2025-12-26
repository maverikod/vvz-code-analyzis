"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Main CLI entry point for BHLFF.

This module implements the top-level CLI `bhlff` with subcommands to run
experiments, analyses, reports, and Step 03 time integrators demo.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from .analyze import main as analyze_main
from .quench_detect import main as quench_main
from .run import main as run_main
from .report import main as report_main
from .step03 import main as step03_main
from .step04_level_a import main as step04_main


def _load_json_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bhlff", description="BHLFF CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    run_parser = subparsers.add_parser("run", help="Run experiments")
    run_parser.add_argument(
        "--config", type=Path, default=Path("configs/bvp_7d_config.json")
    )
    run_parser.set_defaults(
        func=lambda args: run_main(
            [
                "--config",
                str(args.config),
            ]
        )
    )

    # analyze
    analyze_parser = subparsers.add_parser("analyze", help="Analyze outputs")
    analyze_parser.add_argument(
        "--config", type=Path, default=Path("configs/reporting.json")
    )
    analyze_parser.set_defaults(
        func=lambda args: analyze_main(["--config", str(args.config)])
    )

    # report
    report_parser = subparsers.add_parser("report", help="Generate reports")
    report_parser.add_argument(
        "--config", type=Path, default=Path("configs/reporting.json")
    )
    report_parser.set_defaults(
        func=lambda args: report_main(["--config", str(args.config)])
    )

    # quench-detect
    quench_parser = subparsers.add_parser(
        "quench-detect", help="Run quench detection workflow"
    )
    quench_parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/level_a/A06_quench_detection.json"),
        help="Path to quench detection configuration JSON",
    )
    quench_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Directory for storing detection artefacts",
    )
    quench_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    quench_parser.set_defaults(
        func=lambda args: quench_main(
            [
                "--config",
                str(args.config),
                *(
                    ["--output", str(args.output)]
                    if args.output is not None
                    else []
                ),
                *(["--verbose"] if args.verbose else []),
            ]
        )
    )

    # step-03
    step03_parser = subparsers.add_parser(
        "step-03", help="Run Step 03 time integrators demo"
    )
    step03_parser.add_argument(
        "--config", type=Path, default=Path("configs/bvp_7d_config.json")
    )

    # step-04
    step04_parser = subparsers.add_parser(
        "step-04", help="Run Step 04 Level A validation tests"
    )
    step04_parser.add_argument(
        "--minimal",
        action="store_true",
        help="Run minimal smoke (A01, A03)",
    )
    step04_parser.add_argument(
        "--k",
        default="",
        help="Pytest -k expression to filter tests",
    )
    step04_parser.add_argument(
        "--maxfail", type=int, default=1, help="Stop after N failures"
    )
    step04_parser.set_defaults(
        func=lambda args: step04_main(
            (["--minimal"] if args.minimal else [])
            + [
                "--k",
                args.k,
                "--maxfail",
                str(args.maxfail),
            ]
        )
    )
    step03_parser.add_argument(
        "--integrator",
        choices=["cn", "adaptive"],
        default="cn",
    )
    step03_parser.add_argument(
        "--nt", type=int, default=64, help="Number of time steps"
    )
    step03_parser.add_argument(
        "--nx", type=int, default=32, help="Grid size per spatial axis"
    )
    step03_parser.set_defaults(
        func=lambda args: step03_main(
            [
                "--config",
                str(args.config),
                "--integrator",
                args.integrator,
                "--nt",
                str(args.nt),
                "--nx",
                str(args.nx),
            ]
        )
    )

    return parser


def main(argv: Any = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
        return int(result) if isinstance(result, int) else 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
