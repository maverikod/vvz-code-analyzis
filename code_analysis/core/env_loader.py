"""
Load `.env` into the process environment (passwords and local overrides).

Searches upward from the current working directory for a `.env` file
(standard python-dotenv behavior).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _try_load_dotenv(path: Path, *, override: bool) -> bool:
    """Load one ``.env`` file; skip unreadable paths without failing startup."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False

    if not path.is_file():
        return False
    try:
        load_dotenv(path, override=override)
        return True
    except PermissionError:
        return False
    except OSError:
        return False


def load_dotenv_best_effort(*, override: bool = False) -> bool:
    """
    Load the first `.env` found when walking up from ``Path.cwd()``.

    Returns:
        True if a file was found and loaded, False otherwise.
    """
    try:
        from dotenv import find_dotenv
    except ImportError:
        return False

    path = find_dotenv(usecwd=True)
    if not path:
        return False
    return _try_load_dotenv(Path(path), override=override)


def load_dotenv_near_config(
    config_path: Optional[Path], *, override: bool = False
) -> bool:
    """
    Prefer loading `.env` from the directory containing the config file, then cwd walk.

    Args:
        config_path: Path to ``config.json`` (or another config file).
        override: When True, override existing environment variables.
    """
    loaded = False
    if config_path:
        candidate = Path(config_path).resolve().parent / ".env"
        if _try_load_dotenv(candidate, override=override):
            loaded = True

    secrets_dir = os.environ.get("CASMGR_SECRETS", "/var/casmgr/secrets")
    secrets_env = Path(secrets_dir).expanduser() / ".env"
    if _try_load_dotenv(secrets_env, override=override):
        loaded = True

    if load_dotenv_best_effort(override=override):
        loaded = True
    return loaded
