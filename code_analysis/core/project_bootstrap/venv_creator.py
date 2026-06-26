"""Create and validate virtual environments for bootstrapped projects."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)
# @node-id: e95abe95-93fc-4f6b-81ad-a87339f1143d


@dataclass
class VenvResult:
    """Result of venv creation."""

    success: bool
    venv_path: Optional[Path] = None
    python_version: str = ""
    pip_version: str = ""
    message: str = ""
    already_exists: bool = False
    errors: list[str] = field(default_factory=list)


# @node-id: 1fef4c80-0c51-4961-8985-774b1fadcf41


class VenvCreator:
    """Creates a .venv virtualenv inside the project root.

    Validates system Python and pip availability before creating.
    Uses `python -m venv` to create the environment.
    """

    VENV_DIR = ".venv"
    # @node-id: 666f449b-b4d5-43ed-a5a1-7552a3114748

    def __init__(
        self,
        project_root: Path,
        python_executable: str = "python3",
    ) -> None:
        """Initialise VenvCreator.

        Args:
            project_root: Absolute path to the project directory.
            python_executable: Path or name of the Python interpreter to use.
        """
        self.project_root = Path(project_root)
        self.python_executable = python_executable

    # @node-id: 4441dc54-c004-4422-b011-b0fbd4264cc4

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(self, force: bool = False) -> VenvResult:
        """Create .venv virtualenv.

        Args:
            force: If True, recreate even if .venv already exists.

        Returns:
            VenvResult with outcome details.
        """
        errors: list[str] = []

        # 1. Check Python
        python_check = self._check_python()
        if not python_check["ok"]:
            return VenvResult(
                success=False,
                message=python_check["error"],
                errors=[python_check["error"]],
            )

        # 2. Check pip
        pip_check = self._check_pip(python_check["executable"])
        if not pip_check["ok"]:
            errors.append(pip_check["error"])
            logger.warning("pip not found: %s", pip_check["error"])

        venv_path = self.project_root / self.VENV_DIR

        # 3. Already exists?
        if venv_path.exists() and not force:
            logger.info(".venv already exists at %s, skipping creation", venv_path)
            return VenvResult(
                success=True,
                venv_path=venv_path,
                python_version=python_check.get("version", ""),
                pip_version=pip_check.get("version", ""),
                message=".venv already exists",
                already_exists=True,
                errors=errors,
            )

        # 4. Create venv
        try:
            result = subprocess.run(
                [python_check["executable"], "-m", "venv", str(venv_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                msg = f"venv creation failed: {result.stderr.strip()}"
                return VenvResult(success=False, message=msg, errors=[msg])
        except Exception as exc:
            msg = f"venv creation exception: {exc}"
            return VenvResult(success=False, message=msg, errors=[msg])

        logger.info("Created .venv at %s", venv_path)
        return VenvResult(
            success=True,
            venv_path=venv_path,
            python_version=python_check.get("version", ""),
            pip_version=pip_check.get("version", ""),
            message=f"Created .venv at {venv_path}",
            errors=errors,
        )

    # @node-id: 62713a25-248b-4a79-8b3f-cf1133fc84ee

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_python(self) -> dict:
        """Check that the configured Python executable is available."""
        executable = shutil.which(self.python_executable) or self.python_executable
        try:
            result = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                version = (result.stdout or result.stderr).strip()
                return {"ok": True, "executable": executable, "version": version}
            return {
                "ok": False,
                "error": (
                    f"Python executable '{executable}' returned "
                    f"non-zero exit code: {result.returncode}"
                ),
            }
        except FileNotFoundError:
            return {
                "ok": False,
                "error": f"Python executable not found: '{self.python_executable}'",
            }
        except Exception as exc:
            return {"ok": False, "error": f"Python check failed: {exc}"}

    # @node-id: 0d79fb4a-b4bf-43c8-9e51-7a4257cc94a0

    def _check_pip(self, python_executable: str) -> dict:
        """Check pip availability via the Python executable."""
        try:
            result = subprocess.run(
                [python_executable, "-m", "pip", "--version"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                return {"ok": True, "version": version}
            return {
                "ok": False,
                "error": f"pip not available via '{python_executable} -m pip': {result.stderr.strip()}",
            }
        except Exception as exc:
            return {"ok": False, "error": f"pip check failed: {exc}"}
