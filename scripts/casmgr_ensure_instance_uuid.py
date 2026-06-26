#!/usr/bin/env python3
"""
Ensure ``registration.instance_uuid`` in casmgr config is a valid UUID4.

Called from ``debian/postinst`` after the package venv is installed.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from code_analysis.core.config_instance_uuid import ensure_instance_uuid_in_config

DEFAULT_CONFIG = Path("/etc/casmgr/config.json")


def main(argv: list[str] | None = None) -> int:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Ensure registration.instance_uuid is a valid UUID4.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"Config file path (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report whether a UUID would be generated without writing the file",
    )
    args = parser.parse_args(argv)
    new_uuid = ensure_instance_uuid_in_config(args.config, dry_run=args.dry_run)
    if new_uuid:
        prefix = "Would generate" if args.dry_run else "Generated"
        print(f"{prefix} registration.instance_uuid: {new_uuid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
