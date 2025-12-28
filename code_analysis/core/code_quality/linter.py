"""
Code linter using flake8 as a library.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def lint_with_flake8(
    file_path: Path, ignore: Optional[List[str]] = None
) -> Tuple[bool, Optional[str], List[str]]:
    """
    Lint Python code using flake8 as a library.

    Args:
        file_path: Path to Python file to lint
        ignore: List of error codes to ignore

    Returns:
        Tuple of (success, error_message, list_of_errors)
    """
    try:
        from flake8.api import legacy as flake8_legacy  # type: ignore[import-untyped]

        # Create flake8 checker
        style_guide = flake8_legacy.get_style_guide(
            ignore=ignore or [],
            max_line_length=88,
        )

        # Check file
        report = style_guide.check_files([str(file_path)])
        if report.total_errors > 0:
            # NOTE:
            # flake8's internal report API is not stable across versions and can return
            # different shapes for `get_statistics()`. To keep this tool robust, we
            # delegate detailed error collection to the subprocess output.
            return _lint_with_subprocess(file_path, ignore)

        logger.debug(f"No flake8 errors found in {file_path}")
        return (True, None, [])

    except ImportError:
        # Fallback to subprocess if flake8 is not available as library
        logger.debug("Flake8 not available as library, falling back to subprocess")
        return _lint_with_subprocess(file_path, ignore)
    except Exception as e:
        # If flake8 library path fails, fall back to subprocess to avoid hard-failing.
        logger.warning(f"flake8 library lint failed, falling back to subprocess: {e}")
        return _lint_with_subprocess(file_path, ignore)


def _lint_with_subprocess(
    file_path: Path, ignore: Optional[List[str]] = None
) -> Tuple[bool, Optional[str], List[str]]:
    """Fallback to subprocess if flake8 library is not available."""
    import os
    import subprocess

    try:
        cmd = ["flake8", str(file_path)]
        if ignore:
            cmd.extend(["--ignore", ",".join(ignore)])

        # IMPORTANT:
        # This project contains a package named `code_analysis.commands.ast`, which can
        # shadow the standard library `ast` module if PYTHONPATH is polluted (the server
        # injects command paths into PYTHONPATH for child processes). Flake8 imports
        # stdlib `ast`, so we must sanitize PYTHONPATH for this subprocess.
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        if result.returncode == 0:
            logger.debug(f"No flake8 errors found in {file_path}")
            return (True, None, [])
        else:
            stdout_lines = result.stdout.splitlines() if result.stdout else []
            stderr_lines = result.stderr.splitlines() if result.stderr else []
            errors = [e for e in (stdout_lines + stderr_lines) if e.strip()]

            # Some flake8 failures can print diagnostics only to stderr.
            # If nothing was captured, return a generic failure message.
            error_msg = (
                f"Found {len(errors)} flake8 errors"
                if errors
                else f"flake8 failed with exit code {result.returncode}"
            )
            logger.warning(f"{error_msg} in {file_path}")
            return (False, error_msg, errors)

    except subprocess.TimeoutExpired:
        logger.warning("Flake8 linting timed out")
        return (False, "Linting timed out", [])
    except FileNotFoundError:
        logger.warning("Flake8 not found, skipping linting")
        return (False, "Flake8 not installed", [])
    except Exception as e:
        logger.warning(f"Error during linting: {e}")
        return (False, str(e), [])
