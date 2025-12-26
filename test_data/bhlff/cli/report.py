"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Report entry point for BHLFF (`bhlff-report`).

Generates reports based on configuration (integrate with reporting utils).
"""

import argparse
import json
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate BHLFF reports")
    parser.add_argument("--config", type=Path, required=True)
    return parser


def main(argv: Any = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config_path: Path = args.config
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    _ = json.loads(config_path.read_text(encoding="utf-8"))
    print(f"Loaded report config: {config_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
