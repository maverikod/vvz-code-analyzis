"""
Type checker using mypy as a library.

When no config is provided, uses a minimal config that excludes .venv, venv,
and .mypy_cache so mypy does not crawl the virtualenv (major speedup).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Minimal mypy config to exclude .venv/venv so single-file runs don't crawl them
_MYPY_EXCLUDE_VENV_CONFIG = b"""[mypy]
exclude = (\\.venv|venv|\\.mypy_cache)/
"""


def type_check_with_mypy(
    file_path: Path,
    config_file: Optional[Path] = None,
    ignore_errors: bool = False,
) -> Tuple[bool, Optional[str], List[str]]:
    """
    Type check Python code using mypy as a library.

    Args:
        file_path: Path to Python file to type check
        config_file: Optional path to mypy config file
        ignore_errors: If True, treat errors as warnings

    Returns:
        Tuple of (success, error_message, list_of_errors)
    """
    # IMPORTANT:
    # The server process can inject command paths into PYTHONPATH (spawn-mode helpers),
    # and this project contains a package named `code_analysis.commands.ast` that may
    # shadow the stdlib `ast` module for in-process tooling. Running mypy via its
    # library API inside the server process can therefore fail in non-obvious ways.
    # To keep the MCP command robust, always run mypy via subprocess with sanitized
    # environment (see `_type_check_with_subprocess`).
    return _type_check_with_subprocess(file_path, config_file, ignore_errors)


def _type_check_with_subprocess(
    file_path: Path,
    config_file: Optional[Path] = None,
    ignore_errors: bool = False,
) -> Tuple[bool, Optional[str], List[str]]:
    """
    Run mypy in a subprocess with sanitized environment.

    Notes:
        When a mypy config is provided and points to this repository (i.e. the
        config lives next to the `code_analysis/` package), we run mypy against
        the whole package (`-p code_analysis`) instead of a single file.

        This avoids common mypy pitfalls for single-file checks:
        - duplicated module discovery (same file as top-level and package module);
        - relative-import resolution failures.

    Args:
        file_path: Path to Python file to type check.
        config_file: Optional path to mypy config file.
        ignore_errors: If True, treat errors as warnings.

    Returns:
        Tuple of (success, error_message, list_of_errors).
    """
    import os
    import subprocess

    try:
        cmd: list[str]
        cwd: Optional[str] = None
        tmp_config: Optional[Path] = None

        if config_file:
            project_root = config_file.parent.resolve()
            package_root = project_root / "code_analysis"

            if package_root.exists() and package_root.is_dir():
                # Package-aware run for this repo.
                cmd = [
                    "mypy",
                    "--config-file",
                    str(config_file),
                    "-p",
                    "code_analysis",
                ]
                cwd = str(project_root)
            else:
                # Fallback: file-only run.
                cmd = ["mypy", str(file_path), "--config-file", str(config_file)]
        else:
            # No config: use minimal config that excludes .venv/venv so mypy
            # does not crawl the project's virtualenv (avoids ~minutes per file).
            with tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=".ini",
                prefix="mypy_exclude_venv_",
                delete=False,
            ) as f:
                f.write(_MYPY_EXCLUDE_VENV_CONFIG)
                tmp_config = Path(f.name)
            cmd = ["mypy", str(file_path), "--config-file", str(tmp_config)]

        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
            cwd=cwd,
        )

        if tmp_config is not None:
            try:
                tmp_config.unlink(missing_ok=True)
            except OSError:
                pass

        errors: List[str] = []
        if result.stdout:
            errors.extend([line for line in result.stdout.split("\n") if line.strip()])
        if result.stderr:
            errors.extend([line for line in result.stderr.split("\n") if line.strip()])

        if result.returncode != 0:
            error_msg = f"Found {len(errors)} mypy errors"
            if ignore_errors:
                logger.info(f"{error_msg} in {file_path} (ignored)")
                return (True, None, errors)
            logger.warning(f"{error_msg} in {file_path}")
            return (False, error_msg, errors)

        logger.debug(f"No mypy errors found in {file_path}")
        return (True, None, [])

    except subprocess.TimeoutExpired:
        logger.warning("Mypy type checking timed out")
        return (False, "Type checking timed out", [])
    except FileNotFoundError:
        logger.warning("Mypy not found, skipping type checking")
        return (False, "Mypy not installed", [])
    except Exception as e:
        logger.warning(f"Error during type checking: {e}")
        return (False, str(e), [])


def type_check_project_with_mypy(
    project_path: Path,
    config_file: Optional[Path] = None,
    timeout_sec: int = 120,
) -> Tuple[bool, Dict[str, List[str]]]:
    """
    Run mypy once on the whole project directory (excluding .venv/venv).

    Much faster than per-file runs. Returns per-file error lines keyed by
    normalized absolute path.

    Args:
        project_path: Root directory to check.
        config_file: Optional mypy config (if None, uses exclude-venv config).
        timeout_sec: Subprocess timeout.

    Returns:
        (success, per_file_errors). per_file_errors maps path str -> list of
        error/note lines for that file.
    """
    per_file: Dict[str, List[str]] = {}
    project_path = project_path.resolve()
    cwd = str(project_path)

    if config_file:
        config_path = str(config_file)
    else:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".ini",
            prefix="mypy_exclude_venv_",
            delete=False,
        ) as f:
            f.write(_MYPY_EXCLUDE_VENV_CONFIG)
            config_path = f.name
    try:
        cmd = ["mypy", str(project_path), "--config-file", config_path]
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=env,
            cwd=cwd,
        )
    finally:
        if not config_file:
            try:
                os.unlink(config_path)
            except OSError:
                pass

    out = (result.stdout or "") + "\n" + (result.stderr or "")
    for line in out.split("\n"):
        line = line.strip()
        if not line or (": error:" not in line and ": note:" not in line):
            continue
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        file_part = parts[0].strip()
        try:
            p = (
                (project_path / file_part).resolve()
                if not Path(file_part).is_absolute()
                else Path(file_part).resolve()
            )
            key = str(p)
            if key not in per_file:
                per_file[key] = []
            per_file[key].append(line)
        except Exception:
            continue
    return (result.returncode == 0, per_file)
