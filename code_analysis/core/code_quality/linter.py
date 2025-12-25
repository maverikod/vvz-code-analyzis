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
        from flake8.api import legacy as flake8_legacy

        # Create flake8 checker
        style_guide = flake8_legacy.get_style_guide(
            ignore=ignore or [],
            max_line_length=88,
        )

        # Check file
        report = style_guide.check_files([str(file_path)])
        errors = []

        if report.total_errors > 0:
            # Collect error messages
            for line_number, code, text, _ in report.get_statistics(""):
                errors.append(f"{file_path}:{line_number}: {code} {text}")

            error_msg = f"Found {report.total_errors} flake8 errors"
            logger.warning(f"{error_msg} in {file_path}")
            return (False, error_msg, errors)
        else:
            logger.debug(f"No flake8 errors found in {file_path}")
            return (True, None, [])

    except ImportError:
        # Fallback to subprocess if flake8 is not available as library
        logger.debug("Flake8 not available as library, falling back to subprocess")
        return _lint_with_subprocess(file_path, ignore)
    except Exception as e:
        error_msg = f"Error during linting: {str(e)}"
        logger.warning(error_msg)
        return (False, error_msg, [])


def _lint_with_subprocess(
    file_path: Path, ignore: Optional[List[str]] = None
) -> Tuple[bool, Optional[str], List[str]]:
    """Fallback to subprocess if flake8 library is not available."""
    import subprocess

    try:
        cmd = ["flake8", str(file_path)]
        if ignore:
            cmd.extend(["--ignore", ",".join(ignore)])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            logger.debug(f"No flake8 errors found in {file_path}")
            return (True, None, [])
        else:
            errors = result.stdout.split("\n") if result.stdout else []
            errors = [e for e in errors if e.strip()]
            error_msg = f"Found {len(errors)} flake8 errors"
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
