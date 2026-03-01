"""
Project sandbox: run Python code only from a given project root.

Runs a script in a subprocess with cwd and PYTHONPATH restricted to the
project root so that only code from that project (and the standard library)
can be executed. Used for registered projects only.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class VenvNotFoundError(Exception):
    """Raised when project .venv or venv is not found."""


@dataclass
class SandboxRunResult:
    """Result of running a script in the project sandbox.

    Attributes:
        stdout: Standard output (text).
        stderr: Standard error (text).
        returncode: Process return code (None if timed out).
        timed_out: True if the process was killed due to timeout.
    """

    stdout: str
    stderr: str
    returncode: Optional[int]
    timed_out: bool


def run_in_project_sandbox(
    root_path: Path,
    script_relative_path: str,
    args: Optional[List[str]] = None,
    timeout_seconds: Optional[int] = None,
) -> SandboxRunResult:
    """
    Run a Python script under the project sandbox.

    The script must be inside root_path. Execution uses:
    - cwd = root_path
    - PYTHONPATH = root_path only (imports limited to project + stdlib)
    - If root_path/.venv or root_path/venv exists: uses that venv's Python
      (interpreter, VIRTUAL_ENV, PATH) so project dependencies are available.
      Raises VenvNotFoundError if neither .venv nor venv is found.

    Args:
        root_path: Absolute path to the project root (must exist).
        script_relative_path: Path to the script relative to root_path.
            Must not escape the project (e.g. no ".." outside root).
        args: Optional list of arguments passed to the script (argv[1:]).
        timeout_seconds: Optional timeout in seconds; process is killed if exceeded.

    Returns:
        SandboxRunResult with stdout, stderr, returncode, and timed_out flag.

    Raises:
        ValueError: If root_path does not exist, or script path is outside project.
        FileNotFoundError: If the script file does not exist.
        VenvNotFoundError: If neither .venv nor venv exists under root_path.
    """
    root_resolved = root_path.resolve()
    if not root_resolved.is_dir():
        raise ValueError(f"Project root is not a directory: {root_path}")

    # Resolve script path: always relative to project root, no escape.
    script_path = (root_resolved / script_relative_path).resolve()
    if not script_path.is_relative_to(root_resolved):
        raise ValueError(
            f"Script path must be inside project root: {script_relative_path} "
            f"(resolved to {script_path})"
        )
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")
    if not script_path.is_file():
        raise ValueError(f"Path is not a file: {script_path}")

    # Prefer project's .venv/bin/python so project dependencies are used
    venv_python: Optional[Path] = None
    for cand in [
        root_resolved / ".venv" / "bin" / "python",
        root_resolved / "venv" / "bin" / "python",
    ]:
        if cand.exists():
            venv_python = cand
            break

    if venv_python is None:
        raise VenvNotFoundError(
            f"Project virtual environment not found under {root_resolved}. "
            "Expected .venv/bin/python or venv/bin/python. "
            "Create a venv in the project root (e.g. python -m venv .venv)."
        )

    interpreter = str(venv_python)
    venv_dir = venv_python.parent.parent
    logger.debug(
        "Using project venv: %s (interpreter=%s)",
        venv_dir,
        interpreter,
    )

    cmd = [interpreter, str(script_path)]
    if args:
        cmd.extend(args)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(root_resolved)
    if venv_dir is not None:
        env["VIRTUAL_ENV"] = str(venv_dir)
        venv_bin = venv_dir / "bin"
        if venv_bin.exists():
            path_prepend = str(venv_bin)
            env["PATH"] = path_prepend + os.pathsep + env.get("PATH", "")

    logger.debug(
        "Running in project sandbox: cwd=%s PYTHONPATH=%s cmd=%s",
        root_resolved,
        env["PYTHONPATH"],
        cmd,
    )
    try:
        result = subprocess.run(
            cmd,
            cwd=str(root_resolved),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return SandboxRunResult(
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            returncode=result.returncode,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as e:
        out = getattr(e, "output", None) or getattr(e, "stdout", None)
        err = getattr(e, "stderr", None)
        stdout_str = (
            out.decode(errors="replace") if isinstance(out, bytes) else (out or "")
        )
        stderr_str = (
            err.decode(errors="replace") if isinstance(err, bytes) else (err or "")
        )
        return SandboxRunResult(
            stdout=stdout_str,
            stderr=stderr_str,
            returncode=None,
            timed_out=True,
        )
