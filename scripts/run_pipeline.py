#!/usr/bin/env python3
"""Backward-compatible wrapper for the package-level pipeline CLI."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from code_analysis.pipeline_cli import main


if __name__ == "__main__":
    sys.exit(main())
