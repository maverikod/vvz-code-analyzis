"""
Internal commands for project creation.

Author: Vasiliy Zdanovskyy
email: vasilyvz@gmail.com
"""

import asyncio
import json
import logging
import shutil
import subprocess
import sys
import uuid
import zipfile as _zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database_client.client import DatabaseClient
else:
    DatabaseClient = Any

from code_analysis.core.database_driver_pkg.domain.projects import insert_project_row
from code_analysis.core.project_root_path import persist_projects_root_path_stored_value

logger = logging.getLogger(__name__)


class CreateProjectCommand:
    """
    Command to create or register a new project.

    This command:
    1. Validates that watched directory exists
    2. If project dir exists and not use_existing_dir: fails with PROJECT_DIR_EXISTS
    3. If project dir exists and use_existing_dir: creates only projectid file and registers
    4. If project dir does not exist: creates dir, projectid file, and registers in database
    5. Optionally scaffolds standard directory structure and base files
    6. Optionally extracts rules template from a zip archive
    7. Optionally creates a Python virtual environment

    Returns project ID and bootstrap report.
    """

    def __init__(
        self,
        database: DatabaseClient,
        watch_dir_id: str,
        project_name: str,
        description: str,
        project_id: Optional[str] = None,
        use_existing_dir: bool = False,
        scaffold: bool = True,
        create_venv: bool = True,
        template_zip: Optional[str] = None,
    ):
        """
        Initialize create project command.

        Args:
            self: Command instance.
            database: DatabaseClient instance.
            watch_dir_id: Watch directory ID from watch_dirs table (must exist).
            project_name: Name of project subdirectory to create in watch_dir.
            description: Human-readable description of the project (required).
            project_id: Optional project ID (UUID4). If not provided, will be generated.
            use_existing_dir: If True, when project directory already exists, create only
                projectid file and register in DB instead of failing with PROJECT_DIR_EXISTS.
            scaffold: If True, create standard directory structure and base files.
            create_venv: If True, create a Python virtual environment at .venv/.
            template_zip: Optional absolute path to a rules template zip archive.
        """
        self.database = database
        self.watch_dir_id = watch_dir_id
        self.project_name = project_name
        self.description = description
        self.project_id = project_id
        self.use_existing_dir = use_existing_dir
        self.scaffold = scaffold
        self.create_venv = create_venv
        self.template_zip = template_zip

    def _get_watch_dir_path(self) -> Optional[Path]:
        """
        Get watch directory path from watch_dir_id.

        Returns:
            Path to watch directory or None if not found.
        """
        try:
            path_str = self.database.get_watch_dir_absolute_path(
                str(self.watch_dir_id or "")
            )
            if not path_str:
                logger.error(
                    f"Watch directory {self.watch_dir_id} not found in database "
                    "or has no path set"
                )
                return None
            watch_path = Path(path_str)
            if not watch_path.exists():
                logger.error(f"Watch directory path does not exist: {watch_path}")
                return None
            return watch_path
        except Exception as e:
            logger.error(
                f"Error getting watch_dir path for {self.watch_dir_id}: {e}",
                exc_info=True,
            )
            return None

    def _scaffold_dirs(self, project_path: Path) -> List[str]:
        """
        Create standard project directory structure.

        Creates: tests/, docs/plans/, docs/aireports/, docs/agents/,
        logs/, configs/, scripts/. Empty directories get a .gitkeep.

        Args:
            project_path: Absolute path to the project root.

        Returns:
            List of created directory paths (relative to project_path).
        """
        dirs = [
            "tests",
            "docs/plans",
            "docs/aireports",
            "docs/agents",
            "logs",
            "configs",
            "scripts",
        ]
        created: List[str] = []
        for rel in dirs:
            d = project_path / rel
            d.mkdir(parents=True, exist_ok=True)
            if not any(d.iterdir()):
                (d / ".gitkeep").touch()
            created.append(rel)
            logger.info(f"Scaffolded directory: {d}")
        return created

    def _create_base_files(self, project_path: Path, slug: str) -> List[str]:
        """
        Create standard boilerplate files in the project root.

        Skips any file that already exists.

        Args:
            project_path: Absolute path to the project root.
            slug: Project slug used as the Python package name.

        Returns:
            List of created file paths (relative to project_path).
        """
        created: List[str] = []

        def _write(rel: str, content: str) -> None:
            """Create a missing scaffold file and record its relative path."""
            p = project_path / rel
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
                created.append(rel)
                logger.info(f"Created base file: {p}")

        _write(
            "pyproject.toml",
            f'[project]\nname = "{slug}"\nversion = "0.1.0"\ndescription = "{self.description}"\nauthors = [{{name = "Vasiliy Zdanovskiy", email = "vasilyvz@gmail.com"}}]\nrequires-python = ">=3.11"\ndependencies = []\n\n[tool.black]\nline-length = 88\n\n[tool.mypy]\nstrict = true\n',
        )
        _write("mypy.ini", "[mypy]\nstrict = True\nignore_missing_imports = True\n")
        _write(
            ".gitignore",
            ".venv/\n__pycache__/\n*.pyc\n*.yo\n.mypy_cache/\n.pytest_cache/\nlogs/\n*.log\n.env\ndist/\nbuild/\n*.egg-info/\n",
        )
        _write(
            f"{slug}/__init__.py",
            f'"""\nProject:     {slug}\nModule:      {slug}/__init__.py\nAuthor:      Vasiliy Zdanovskiy <vasilyvz@gmail.com>\nDescription: {self.description}\n"""\n',
        )
        _write(
            "tests/__init__.py",
            f'"""\nProject:     {slug}\nModule:      tests/__init__.py\nAuthor:      Vasiliy Zdanovskiy <vasilyvz@gmail.com>\nDescription: Test suite for {slug}\n"""\n',
        )
        return created

    def _extract_template(
        self, project_path: Path, zip_path: str
    ) -> Tuple[List[str], Optional[str]]:
        """
        Extract a rules template zip archive into the project root.

        Args:
            project_path: Absolute path to the project root.
            zip_path: Absolute path to the zip archive.

        Returns:
            Tuple of (list of extracted relative paths, error string or None).
        """
        extracted: List[str] = []
        try:
            zp = Path(zip_path)
            if not zp.exists():
                return [], f"Template zip not found: {zip_path}"
            with _zipfile.ZipFile(zp, "r") as zf:
                names = zf.namelist()
                prefix = ""
                if names and "/" in names[0]:
                    prefix = names[0].split("/")[0] + "/"
                for name in names:
                    rel = name[len(prefix) :] if name.startswith(prefix) else name
                    if not rel or rel.endswith("/"):
                        continue
                    dest = project_path / rel
                    if dest.exists():
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name) as src, open(dest, "wb") as dst:
                        dst.write(src.read())
                    extracted.append(rel)
                    logger.info(f"Extracted template file: {rel}")
            return extracted, None
        except Exception as e:
            logger.error(f"Error extracting template: {e}", exc_info=True)
            return extracted, str(e)

    def _create_venv_sync(self, project_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Create a Python virtual environment at project_path/.venv.

        Args:
            project_path: Absolute path to the project root.

        Returns:
            Tuple of (success bool, error string or None).
        """
        venv_path = project_path / ".venv"
        if venv_path.exists():
            logger.info(f"venv already exists: {venv_path}")
            return True, None
        try:
            r = subprocess.run(
                [sys.executable, "-m", "venv", str(venv_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.returncode != 0:
                err = r.stderr.strip() or "venv creation failed"
                logger.error(f"venv creation failed: {err}")
                return False, err
            logger.info(f"Created venv: {venv_path}")
            return True, None
        except subprocess.TimeoutExpired:
            return False, "venv creation timed out (120s)"
        except Exception as e:
            return False, str(e)

    async def _run_bootstrap(self, project_path: Path, slug: str) -> Dict[str, Any]:
        """
        Run optional bootstrap phases after project registration.

        Phases are best-effort and independent.

        Args:
            project_path: Absolute path to the project root.
            slug: Project slug (Python package name).

        Returns:
            Dict with keys: scaffold_dirs, template, base_files, venv.
        """
        report: Dict[str, Any] = {}
        if self.scaffold:
            try:
                report["scaffold_dirs"] = {
                    "ok": True,
                    "created": self._scaffold_dirs(project_path),
                }
            except Exception as e:
                logger.error(f"Scaffold dirs failed: {e}", exc_info=True)
                report["scaffold_dirs"] = {"ok": False, "error": str(e)}
            if self.template_zip:
                extracted, err = self._extract_template(project_path, self.template_zip)
                if err:
                    report["template"] = {
                        "ok": False,
                        "error": err,
                        "extracted": extracted,
                    }
                else:
                    report["template"] = {"ok": True, "extracted": extracted}
            else:
                report["template"] = {"ok": True, "skipped": "no template_zip provided"}
            try:
                report["base_files"] = {
                    "ok": True,
                    "created": self._create_base_files(project_path, slug),
                }
            except Exception as e:
                logger.error(f"Base files creation failed: {e}", exc_info=True)
                report["base_files"] = {"ok": False, "error": str(e)}
        else:
            report["scaffold_dirs"] = {"ok": True, "skipped": "scaffold=False"}
            report["template"] = {"ok": True, "skipped": "scaffold=False"}
            report["base_files"] = {"ok": True, "skipped": "scaffold=False"}
        if self.create_venv:
            ok, err = await asyncio.get_event_loop().run_in_executor(
                None, self._create_venv_sync, project_path
            )
            report["venv"] = (
                {"ok": ok, "path": str(project_path / ".venv")}
                if ok
                else {"ok": False, "error": err}
            )
        else:
            report["venv"] = {"ok": True, "skipped": "create_venv=False"}
        return report

    async def execute(
        self: "CreateProjectCommand",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Execute project creation atomically.

        Returns:
            Dictionary with success, project_id, message, and bootstrap_report.
        """
        transaction_id = None
        project_path = None
        projectid_path = None
        try:
            watch_dir_path = self._get_watch_dir_path()
            if not watch_dir_path:
                return {
                    "success": False,
                    "error": "WATCH_DIR_NOT_FOUND",
                    "message": f"Watch directory {self.watch_dir_id} not found in database or path not set",
                }
            if not self.project_name or not self.project_name.strip():
                return {
                    "success": False,
                    "error": "INVALID_PROJECT_NAME",
                    "message": "Project name cannot be empty",
                }
            slug = self.project_name.strip()
            project_path = watch_dir_path / slug
            if project_path.exists():
                from .base_mcp_command import BaseMCPCommand

                existing_project_id = BaseMCPCommand._get_project_id_by_root_path(
                    self.database, str(project_path)
                )
                if existing_project_id:
                    return {
                        "success": False,
                        "error": "PROJECT_ALREADY_EXISTS",
                        "message": f"Project directory already exists and is registered: {existing_project_id}",
                        "existing_project_id": existing_project_id,
                    }
                if not self.use_existing_dir:
                    return {
                        "success": False,
                        "error": "PROJECT_DIR_EXISTS",
                        "message": f"Project directory already exists: {project_path}",
                    }
                project_id = self.project_id or str(uuid.uuid4())
                projectid_path = project_path / "projectid"
                projectid_path.write_text(
                    json.dumps(
                        {"id": project_id, "description": self.description},
                        indent=4,
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                logger.info(
                    f"Created projectid file in existing directory: {projectid_path}"
                )
                root_stored = persist_projects_root_path_stored_value(
                    project_root_absolute=project_path,
                    watch_dir_id=(
                        str(self.watch_dir_id)
                        if self.watch_dir_id is not None
                        else None
                    ),
                    database=self.database,
                )
                insert_project_row(
                    self.database,
                    project_id,
                    root_stored,
                    project_path.name,
                    comment=self.description,
                    watch_dir_id=self.watch_dir_id,
                )
                logger.info(f"Registered project in database: {project_id}")
                bootstrap_report = await self._run_bootstrap(project_path, slug)
                return {
                    "success": True,
                    "project_id": project_id,
                    "project_root": str(project_path),
                    "message": f"Created projectid in existing directory and registered: {project_id}",
                    "bootstrap_report": bootstrap_report,
                }
            project_id = self.project_id or str(uuid.uuid4())
            transaction_id = self.database.begin_transaction()
            logger.info(f"Started transaction {transaction_id} for project creation")
            try:
                project_path.mkdir(parents=True, exist_ok=False)
                logger.info(f"Created project directory: {project_path}")
                projectid_path = project_path / "projectid"
                projectid_path.write_text(
                    json.dumps(
                        {"id": project_id, "description": self.description},
                        indent=4,
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                logger.info(f"Created projectid file: {projectid_path}")
                root_stored = persist_projects_root_path_stored_value(
                    project_root_absolute=project_path,
                    watch_dir_id=(
                        str(self.watch_dir_id)
                        if self.watch_dir_id is not None
                        else None
                    ),
                    database=self.database,
                )
                insert_project_row(
                    self.database,
                    project_id,
                    root_stored,
                    project_path.name,
                    comment=self.description,
                    watch_dir_id=self.watch_dir_id,
                    transaction_id=transaction_id,
                )
                logger.info(f"Registered project in database: {project_id}")
                self.database.commit_transaction(transaction_id)
                logger.info(f"Committed transaction {transaction_id}")
            except Exception:
                if transaction_id:
                    try:
                        self.database.rollback_transaction(transaction_id)
                        logger.info(f"Rolled back transaction {transaction_id}")
                    except Exception as rollback_error:
                        logger.error(f"Error during rollback: {rollback_error}")
                if projectid_path and projectid_path.exists():
                    try:
                        projectid_path.unlink()
                    except Exception:
                        pass
                if project_path and project_path.exists():
                    try:
                        shutil.rmtree(project_path)
                    except Exception:
                        pass
                raise
            bootstrap_report = await self._run_bootstrap(project_path, slug)
            return {
                "success": True,
                "project_id": project_id,
                "project_root": str(project_path),
                "message": f"Created and registered new project: {project_id}",
                "bootstrap_report": bootstrap_report,
            }
        except Exception as e:
            logger.error(f"Error creating project: {e}", exc_info=True)
            return {
                "success": False,
                "error": "CREATE_PROJECT_ERROR",
                "message": f"Failed to create project: {str(e)}",
            }
