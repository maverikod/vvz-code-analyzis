"""
Code linter using the flake8 CLI in a subprocess.

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
    Lint Python code using the flake8 CLI in a subprocess.

    In-process ``flake8.api.legacy.get_style_guide().check_files()`` is not used:
    it has no wall-clock timeout and could block the server on pathological inputs.
    Subprocess ``flake8`` is capped at 30 seconds and runs with a sanitized
    ``PYTHONPATH`` (see ``_lint_with_subprocess``).
    """
    return _lint_with_subprocess(file_path, ignore)


def _lint_with_subprocess(
    file_path: Path, ignore: Optional[List[str]] = None
) -> Tuple[bool, Optional[str], List[str]]:
    """Run flake8 in a subprocess with timeout and sanitized environment."""
    import subprocess

    from .tool_runtime import module_missing, sanitized_env, tool_command

    try:
        # Resolve flake8 via the server interpreter (python -m flake8), never a
        # bare PATH binary — see tool_runtime for the PATH-drift rationale.
        cmd = tool_command("flake8", "--max-line-length=88", str(file_path))
        if ignore:
            cmd.extend(["--ignore", ",".join(ignore)])

        # Sanitize PYTHONPATH so the project's `code_analysis.commands.ast`
        # package cannot shadow the stdlib `ast` module flake8 imports.
        env = sanitized_env()

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        if module_missing(result.stderr, "flake8"):
            logger.warning("Flake8 module not importable from server interpreter")
            return (False, "Flake8 not installed", [])

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
