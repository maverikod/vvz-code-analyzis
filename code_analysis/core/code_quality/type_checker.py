"""
Type checker using mypy as a library.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


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
    """Fallback to subprocess if mypy library is not available."""
    import os
    import subprocess

    try:
        cmd = ["mypy", str(file_path)]
        if config_file:
            cmd.extend(["--config-file", str(config_file)])
        # Note: mypy doesn't support --ignore-errors flag
        # We'll handle ignore_errors in the result processing

        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )

        errors = []
        if result.stdout:
            errors.extend([line for line in result.stdout.split("\n") if line.strip()])
        if result.stderr:
            errors.extend([line for line in result.stderr.split("\n") if line.strip()])

        if result.returncode != 0:
            error_msg = f"Found {len(errors)} mypy errors"
            if ignore_errors:
                # Treat errors as warnings if ignore_errors=True
                logger.info(f"{error_msg} in {file_path} (ignored)")
                return (True, None, errors)
            else:
                logger.warning(f"{error_msg} in {file_path}")
                return (False, error_msg, errors)
        else:
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
