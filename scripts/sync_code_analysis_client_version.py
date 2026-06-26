#!/usr/bin/env python3
"""
Copy ``[project].version`` from the repository root ``pyproject.toml`` into
``client/code_analysis_client/version.txt`` (single line, no BOM).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def read_project_version(pyproject_path: Path) -> str:
    """Return read project version."""
    text = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r'(?m)^version = "([^"]+)"', text)
    if not match:
        raise RuntimeError(f'No version = "..." in {pyproject_path}')
    return match.group(1).strip()


def main() -> int:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (parent of client/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print version only; do not write version.txt",
    )
    args = parser.parse_args()
    root = args.repo_root.resolve()
    pyproject = root / "pyproject.toml"
    target = root / "client" / "code_analysis_client" / "version.txt"
    ver = read_project_version(pyproject)
    print(f"Root project version: {ver!r}")
    print(f"Target file: {target}")
    if args.dry_run:
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(ver + "\n", encoding="utf-8")
    print("Written.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
