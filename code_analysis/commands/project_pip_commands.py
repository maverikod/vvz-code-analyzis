"""
MCP commands: manage Python packages in a registered project's venv via pip.

These commands run ``python -m pip`` in the project sandbox (same rules as
``run_project_module`` / ``run_project_script``). Names use the ``project_pip_*``
prefix to avoid confusion with AST/import dependency analysis commands.

**Contract:** Every ``project_pip_*`` command requires ``project_id``. The server
resolves a **registered** project root from the database; pip is invoked only with
that root's ``.venv`` or ``venv`` Python (never the server venv or an arbitrary path).
``project_pip_install`` is always dispatched through the background job queue because
installs can run for a long time; list/show/uninstall/check/search stay on the direct
handler (``use_queue=False``).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.project_bootstrap import VenvCreator
from ..core.project_pip_logging import write_project_pip_session_log
from ..core.project_sandbox import (
    SandboxRunResult,
    VenvNotFoundError,
    run_pip_in_project_sandbox,
)

logger = logging.getLogger(__name__)


def _job_id_from_execute_kwargs(kwargs: Dict[str, Any]) -> Optional[str]:
    """Optional queue job id from ``context`` when present."""
    ctx = kwargs.get("context")
    if not isinstance(ctx, dict):
        return None
    jid = ctx.get("job_id")
    if isinstance(jid, str) and jid.strip():
        return jid.strip()
    return None


def _merge_pip_log_data(
    command_name: str,
    project_id: str,
    pip_args: List[str],
    result: SandboxRunResult,
    kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    """Append session log paths from :func:`write_project_pip_session_log`."""
    return write_project_pip_session_log(
        command_name=command_name,
        project_id=project_id,
        pip_args=pip_args,
        stdout=result.stdout,
        stderr=result.stderr,
        returncode=result.returncode,
        timed_out=result.timed_out,
        job_id=_job_id_from_execute_kwargs(kwargs),
    )


def _strip_packages(packages: Optional[List[str]]) -> List[str]:
    """Return non-empty package specifications with surrounding space removed."""
    out: List[str] = []
    if not packages:
        return out
    for p in packages:
        if isinstance(p, str) and p.strip():
            out.append(p.strip())
    return out


def _normalize_dist_name(name: str) -> str:
    """PEP 503-style normalization for comparing distribution names."""
    return name.strip().lower().replace("_", "-")


def _project_name_from_requirement_spec(spec: str) -> str:
    """
    Extract the project name from a single requirement-ish string (no PyPI fetch).

    Strips extras ``[...]``, version clauses, and environment markers after ``;``.
    """
    s = (spec or "").strip()
    if not s:
        return ""
    head = s.split(";", 1)[0].strip()
    head = head.split("[", 1)[0].strip()
    for op in ("===", "==", ">=", "<=", "!=", "~=", ">", "<"):
        if op in head:
            head = head.split(op, 1)[0].strip()
            break
    return head.strip()


def _parse_pip_list_json(stdout: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Parse ``pip list --format=json`` stdout. Returns (rows, error_message)."""
    text = (stdout or "").strip()
    if not text:
        return [], "empty pip list output"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return [], f"invalid JSON from pip list: {e}"
    if not isinstance(data, list):
        return [], "pip list JSON is not an array"
    rows: List[Dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict) and "name" in item:
            rows.append(item)
    return rows, None


def _installed_by_normalized_name(
    pip_list_rows: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Map normalized distribution name -> row from ``pip list --format=json``."""
    index: Dict[str, Dict[str, Any]] = {}
    for row in pip_list_rows:
        raw_name = str(row.get("name", ""))
        if not raw_name:
            continue
        key = _normalize_dist_name(raw_name)
        index[key] = row
    return index


def _resolve_requirements_file(root: Path, relative: str) -> Path:
    """Resolve a requirements file path under project root; must be a file."""
    rel = (relative or "").strip().replace("\\", "/").lstrip("/")
    if not rel:
        raise ValueError("requirements_file must be non-empty")
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as e:
        raise ValueError(
            f"requirements_file must stay inside project root: {relative!r}"
        ) from e
    if not candidate.is_file():
        raise ValueError(f"requirements file not found or not a file: {candidate}")
    return candidate


class ProjectPipInstallCommand(BaseMCPCommand):
    """Install packages into the project's virtual environment using pip.

    Runs always via the job queue: pip resolution and downloads can take a long time.
    Requires ``project_id``; only that project's ``.venv`` or ``venv`` is used—never
    the server interpreter or another project's environment.
    """

    name = "project_pip_install"
    version = "1.0.0"
    descr = (
        "Install Python distribution packages into the project's venv using pip "
        "(queued; project venv package management, not import-graph analysis)"
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True  # Long-running pip install; always run via queue

    @classmethod
    def get_schema(cls: type["ProjectPipInstallCommand"]) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        Used by MCP Proxy for request validation. Keep it strict and deterministic.

        Returns:
            JSON schema dict with top-level and per-parameter ``examples``.
        """
        return {
            "type": "object",
            "description": (
                "Runs ``python -m pip install`` in the registered project's sandbox only: "
                "the interpreter is that project's ``.venv`` or ``venv`` Python (never the server "
                "venv or another project). Same cwd/PYTHONPATH rules as ``run_project_module``. "
                "This command is always executed via the job queue because installs may run for a long time; "
                "poll with ``queue_get_job_status`` using the returned ``job_id``. "
                "Provide package names and/or a requirements file path relative to the project root. "
                "By default (``bootstrap_venv=true``), a missing ``.venv``/``venv`` is created "
                "automatically before pip runs and the install is retried once; set "
                "``bootstrap_venv=false`` to require an existing venv (fails with ``VENV_NOT_FOUND``)."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "Required. Registered project UUID (from ``projectid`` or ``list_projects``). "
                        "Selects exactly one project; pip runs only in that project's ``.venv``/``venv``. "
                        "Root path is resolved from the database."
                    ),
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                "packages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Package specs for pip (e.g. ``requests``, ``pkg==1.0``). "
                        "Can be empty if ``requirements_file`` is set; at least one source is required overall."
                    ),
                    "default": [],
                    "examples": [
                        ["requests"],
                        ["httpx", "pydantic"],
                        ["somepkg==2.1.0"],
                    ],
                },
                "requirements_file": {
                    "type": ["string", "null"],
                    "description": (
                        "Optional path to a requirements file, relative to project root. "
                        "Must stay inside the project directory (no ``..`` traversal)."
                    ),
                    "examples": ["requirements.txt", "requirements/dev.txt"],
                },
                "upgrade": {
                    "type": "boolean",
                    "description": "If true, append ``--upgrade`` to ``pip install``.",
                    "default": False,
                    "examples": [False, True],
                },
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "Optional timeout in seconds for the pip subprocess. "
                        "If exceeded, the process is killed; see ``timed_out`` in the success payload."
                    ),
                    "examples": [120, 300, 600],
                },
                "bootstrap_venv": {
                    "type": "boolean",
                    "description": (
                        "Optional. Default true. "
                        "If no .venv/venv exists under the project root, create one first "
                        "using python -m venv (same bootstrap as create_project's create_venv), "
                        "then retry the pip install once. "
                        "If false, a missing venv fails immediately with VENV_NOT_FOUND "
                        "(previous behavior)."
                    ),
                    "default": True,
                    "examples": [True, False],
                },
                "python_executable": {
                    "type": "string",
                    "description": (
                        "Optional Python interpreter used only for venv bootstrap "
                        "when bootstrap_venv creates a new .venv. Default: 'python3'. "
                        "Ignored when an existing venv is found or bootstrap_venv is false."
                    ),
                    "default": "python3",
                    "examples": ["python3", "python3.11"],
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
            "examples": [
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "packages": ["requests"],
                },
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "requirements_file": "requirements.txt",
                    "upgrade": True,
                    "timeout_seconds": 300,
                },
            ],
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate install options and require an existing project."""
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    @classmethod
    def metadata(cls: type["ProjectPipInstallCommand"]) -> Dict[str, Any]:
        """
        Rich metadata for AI clients (aligned with ``run_project_module`` / ``run_project_script``).
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The ``project_pip_install`` command runs ``python -m pip install`` inside the "
                "virtual environment of the **single** project identified by ``project_id`` only: "
                "``.venv`` or ``venv`` under that project's root. It never targets the server process "
                "venv, the code-analysis tool venv, or any other registered project. "
                "``project_id`` is mandatory. Execution uses the same sandbox as ``run_project_module`` "
                "and ``run_project_script``: cwd and ``PYTHONPATH`` are that project root, and the "
                "interpreter is that project venv's Python. This command manages **installed distributions** "
                "in that venv only; it is **not** static import-graph or ``find_dependencies`` analysis.\n\n"
                "The handler always runs **via the job queue** (``use_queue=True``): submit the command, "
                "receive a ``job_id``, and poll ``queue_get_job_status`` until completion—pip installs "
                "often take a long time (network, resolution, builds).\n\n"
                "Operation flow:\n"
                "1. Resolve project root from the database by ``project_id`` (project must exist)\n"
                "2. Require at least one of: non-empty ``packages`` after trimming, or a non-empty "
                "``requirements_file`` path\n"
                "3. If ``requirements_file`` is set, resolve it under the project root (rejects traversal outside root)\n"
                "4. Build pip arguments: ``install --no-input``, optional ``--upgrade``, optional ``-r <file>``, then package specs\n"
                "5. In the queue worker, run ``asyncio.to_thread(run_pip_in_project_sandbox, ...)`` so the pip subprocess "
                "does not block the worker event loop\n"
                "6. If that call raises ``VenvNotFoundError`` and ``bootstrap_venv`` is true (default), create "
                "``.venv`` via ``VenvCreator`` (using ``python_executable``) under ``asyncio.to_thread``, then "
                "retry the pip install exactly once; if ``bootstrap_venv`` is false, fail immediately with "
                "``VENV_NOT_FOUND``\n"
                "7. If the bootstrap step itself fails, return ``VENV_BOOTSTRAP_FAILED`` with the bootstrap "
                "message/errors in ``data`` (never masked as a plain ``VENV_NOT_FOUND``); if bootstrap succeeds "
                "but the retried pip call still cannot find the interpreter, return ``VENV_NOT_FOUND`` with a "
                "message noting the bootstrap outcome\n"
                "8. Persist stdout/stderr to a session file under the server's ``log_dir/project_pip/`` (see "
                "``pip_output_log_path`` in the result) and return stdout, stderr, returncode, timed_out, and "
                "``pip_args`` for traceability (in the **completed job** result)\n\n"
                "Important notes:\n"
                "- Pip is invoked non-interactively (``--no-input``)\n"
                "- By default (``bootstrap_venv=true``), a missing ``.venv``/``venv`` is created automatically "
                "(same bootstrap as ``create_project``'s ``create_venv``, using ``python_executable``) and the "
                "pip install is retried once; set ``bootstrap_venv=false`` to keep the previous hard-stop "
                "behavior (``VENV_NOT_FOUND``) instead\n"
                "- If the bootstrap step itself fails, the command returns ``VENV_BOOTSTRAP_FAILED`` with the "
                "bootstrap message/errors in ``data``; it never masks that as a plain ``VENV_NOT_FOUND``\n"
                "- Network and index configuration follow the project venv's pip as usual\n"
                "- ``timeout_seconds`` caps the pip subprocess; the server's queue/job limits may also apply separately"
            ),
            "parameters": {
                "project_id": {
                    "description": (
                        "Required. Registered project UUID (from ``projectid`` or ``list_projects``). "
                        "Installs apply only to that project's ``.venv``/``venv``. "
                        "If the project is missing or the root path is invalid, ``VALIDATION_ERROR`` is returned."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "550e8400-e29b-41d4-a716-446655440000",
                        "c86dded6-6f93-4fb0-be54-b6d7b739eeb9",
                    ],
                },
                "packages": {
                    "description": (
                        "List of pip requirement strings (e.g. ``requests``, ``pkg==1.0``). "
                        "Empty is allowed only when ``requirements_file`` provides install sources."
                    ),
                    "type": "array",
                    "required": False,
                    "items": {"type": "string"},
                    "examples": [
                        ["requests"],
                        ["httpx", "pydantic"],
                    ],
                },
                "requirements_file": {
                    "description": (
                        "Optional path to a requirements file relative to the project root. "
                        "Must resolve to a regular file inside the project root."
                    ),
                    "type": ["string", "null"],
                    "required": False,
                    "examples": ["requirements.txt", "requirements/dev.txt", None],
                },
                "upgrade": {
                    "description": "When true, pip receives ``--upgrade`` so existing packages may be upgraded.",
                    "type": "boolean",
                    "required": False,
                    "examples": [False, True],
                },
                "timeout_seconds": {
                    "description": (
                        "Optional wall-clock limit for the pip process. On timeout, ``timed_out`` is true "
                        "and ``returncode`` may be None depending on sandbox behavior."
                    ),
                    "type": "integer",
                    "required": False,
                    "minimum": 1,
                    "examples": [120, 300, 600],
                },
                "bootstrap_venv": {
                    "description": (
                        "When true (default), a missing project venv is created automatically "
                        "before pip runs (same bootstrap as ``create_project``'s ``create_venv``) and "
                        "the install is retried once. When false, a missing venv fails "
                        "immediately with ``VENV_NOT_FOUND`` (previous behavior)."
                    ),
                    "type": "boolean",
                    "required": False,
                    "examples": [True, False],
                },
                "python_executable": {
                    "description": (
                        "Python interpreter used only when ``bootstrap_venv`` creates a new venv. "
                        "Ignored if a venv already exists or ``bootstrap_venv`` is false. Default: 'python3'."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": ["python3", "python3.11"],
                },
            },
            "usage_examples": [
                {
                    "description": "Install named packages",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "packages": ["requests", "httpx"],
                    },
                    "explanation": "Runs ``pip install --no-input requests httpx`` in the project venv.",
                },
                {
                    "description": "Install from requirements file with upgrade",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "packages": [],
                        "requirements_file": "requirements.txt",
                        "upgrade": True,
                        "timeout_seconds": 600,
                    },
                    "explanation": "Installs from ``requirements.txt`` with ``--upgrade`` and a long timeout for large resolves.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "Project not found or project root invalid",
                    "example": "Unknown ``project_id`` or missing directory on disk",
                    "solution": "Use ``list_projects`` / ``create_project`` and ensure the root path exists.",
                },
                "INVALID_PARAMS": {
                    "description": "Neither packages nor requirements file provides install sources",
                    "example": "``packages``: [] and ``requirements_file`` null or empty",
                    "solution": "Pass at least one package or a non-empty ``requirements_file``.",
                },
                "INVALID_PATH": {
                    "description": "Requirements path escapes the project root or is not a file",
                    "example": "``requirements_file``: ``../outside.txt``",
                    "solution": "Use a path under the project root that exists and is a file.",
                },
                "VENV_NOT_FOUND": {
                    "description": (
                        "No ``.venv``/``venv`` Python under the project root, and either "
                        "``bootstrap_venv`` is false or the retried pip call after a successful "
                        "bootstrap still cannot find the interpreter"
                    ),
                    "example": "``bootstrap_venv``: false on a fresh checkout without a virtual environment",
                    "solution": (
                        "Leave ``bootstrap_venv`` at its default (``true``) so the venv is created "
                        "automatically, or create one manually (e.g. ``python -m venv .venv``) and retry."
                    ),
                },
                "VENV_BOOTSTRAP_FAILED": {
                    "description": (
                        "``bootstrap_venv`` was true and no venv existed, but automatic venv creation "
                        "itself failed (e.g. ``python_executable`` missing or pip unavailable)"
                    ),
                    "example": "``python_executable``: ``'python3.99'`` does not exist on the server",
                    "solution": (
                        "Check ``details.bootstrap_message`` / ``details.bootstrap_errors``, fix "
                        "``python_executable`` or server Python availability, or create the venv manually."
                    ),
                },
                "INTERNAL_ERROR": {
                    "description": "Unexpected failure in the command handler",
                    "example": "Unhandled exception after validation",
                    "solution": "Inspect server logs for a stack trace.",
                },
            },
            "return_value": {
                "success": {
                    "description": (
                        "When invoked through the API, the immediate response is a queued job (``job_id``); "
                        "poll until the job completes. The success payload below is the command result "
                        "attached to the finished job. Pip finished or was stopped by timeout."
                    ),
                    "data": {
                        "stdout": "pip stdout",
                        "stderr": "pip stderr",
                        "returncode": "Process exit code (may be None if timed out)",
                        "timed_out": "True if the subprocess hit ``timeout_seconds``",
                        "project_id": "Project UUID",
                        "pip_args": "List of arguments passed to ``python -m pip`` (after ``pip``)",
                        "pip_output_log_path": (
                            "Absolute path to a UTF-8 session log file under ``<server log_dir>/project_pip/``, "
                            "or null if the file could not be written"
                        ),
                        "pip_output_log_relative": (
                            "Session log path relative to the server config directory when applicable, else null"
                        ),
                        "pip_logs_directory": "Resolved server ``log_dir`` (from config ``server.log_dir``)",
                        "pip_log_write_error": "null if the log file was written; otherwise an error message",
                    },
                    "example": {
                        "stdout": "Successfully installed requests-2.32.0\n",
                        "stderr": "",
                        "returncode": 0,
                        "timed_out": False,
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "pip_args": [
                            "install",
                            "--no-input",
                            "requests",
                        ],
                        "pip_output_log_path": "/path/to/repo/logs/project_pip/project_pip_install_20260405T120000Z_a1b2c3d4.log",
                        "pip_output_log_relative": "logs/project_pip/project_pip_install_20260405T120000Z_a1b2c3d4.log",
                        "pip_logs_directory": "/path/to/repo/logs",
                        "pip_log_write_error": None,
                    },
                },
                "error": {
                    "description": "Validation, path, venv, bootstrap, or internal error",
                    "code": (
                        "VALIDATION_ERROR, INVALID_PARAMS, INVALID_PATH, "
                        "VENV_NOT_FOUND, VENV_BOOTSTRAP_FAILED, INTERNAL_ERROR"
                    ),
                    "message": "Human-readable message",
                    "data": (
                        "Optional structured details for validation errors, or bootstrap "
                        "details (``bootstrap_message``/``bootstrap_errors``) for "
                        "``VENV_BOOTSTRAP_FAILED``"
                    ),
                },
            },
            "best_practices": [
                "Poll ``queue_get_job_status`` after submission; do not assume a quick synchronous return",
                "Prefer pinning versions in ``requirements_file`` or explicit ``pkg==version`` strings for reproducible installs",
                "Use ``timeout_seconds`` on slow networks or large dependency trees",
                "Do not confuse this command with AST/import analysis; use dependency tools for graphs",
                "Keep ``requirements_file`` paths relative to the project root and inside the repo",
            ],
        }

    async def execute(
        self: "ProjectPipInstallCommand",
        project_id: str,
        packages: Optional[List[str]] = None,
        requirements_file: Optional[str] = None,
        upgrade: bool = False,
        timeout_seconds: Optional[int] = None,
        bootstrap_venv: bool = True,
        python_executable: str = "python3",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Install packages or a requirements file in the project sandbox.

        On a missing project venv, bootstraps ``.venv`` via ``VenvCreator`` when
        ``bootstrap_venv`` is true (default) and retries the pip install once.
        """
        try:
            root_path = BaseMCPCommand._resolve_project_root(project_id)
            pkgs = _strip_packages(packages)
            req_raw = (requirements_file or "").strip() if requirements_file else ""
            if not pkgs and not req_raw:
                return ErrorResult(
                    code="INVALID_PARAMS",
                    message=(
                        "Provide at least one package in ``packages`` or a non-empty "
                        "``requirements_file`` path."
                    ),
                )
            pip_args = ["install", "--no-input"]
            if upgrade:
                pip_args.append("--upgrade")
            if req_raw:
                try:
                    req_path = _resolve_requirements_file(root_path, req_raw)
                except ValueError as e:
                    return ErrorResult(
                        code="INVALID_PATH",
                        message=str(e),
                    )
                pip_args.extend(["-r", str(req_path)])
            pip_args.extend(pkgs)
            try:
                result = await asyncio.to_thread(
                    run_pip_in_project_sandbox,
                    root_path,
                    pip_args,
                    timeout_seconds,
                )
            except ValueError as e:
                return ErrorResult(code="INVALID_PATH", message=str(e))
            except VenvNotFoundError as e:
                if not bootstrap_venv:
                    return ErrorResult(code="VENV_NOT_FOUND", message=str(e))
                venv_result = await asyncio.to_thread(
                    VenvCreator(root_path, python_executable=python_executable).create
                )
                if not venv_result.success:
                    return ErrorResult(
                        code="VENV_BOOTSTRAP_FAILED",
                        message=(
                            "Automatic venv bootstrap failed before pip install "
                            f"could run: {venv_result.message}"
                        ),
                        details={
                            "bootstrap_message": venv_result.message,
                            "bootstrap_errors": venv_result.errors,
                        },
                    )
                try:
                    result = await asyncio.to_thread(
                        run_pip_in_project_sandbox,
                        root_path,
                        pip_args,
                        timeout_seconds,
                    )
                except ValueError as e_retry:
                    return ErrorResult(
                        code="INVALID_PATH",
                        message=(
                            "venv bootstrap succeeded but the retried pip "
                            f"install hit an invalid path: {e_retry}"
                        ),
                    )
                except VenvNotFoundError as e_retry:
                    return ErrorResult(
                        code="VENV_NOT_FOUND",
                        message=(
                            "venv bootstrap reported success but pip still "
                            f"cannot find the project interpreter: {e_retry}"
                        ),
                    )
            data = {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "timed_out": result.timed_out,
                "project_id": project_id,
                "pip_args": pip_args,
            }
            data.update(
                _merge_pip_log_data(
                    ProjectPipInstallCommand.name,
                    project_id,
                    pip_args,
                    result,
                    kwargs,
                )
            )
            return SuccessResult(data=data)
        except Exception as e:
            from ..core.exceptions import ValidationError

            if isinstance(e, ValidationError):
                return ErrorResult(
                    code="VALIDATION_ERROR",
                    message=e.message,
                    data=getattr(e, "details", {}),
                )
            logger.exception("project_pip_install failed: %s", e)
            return ErrorResult(code="INTERNAL_ERROR", message=str(e))


class ProjectPipListCommand(BaseMCPCommand):
    """
    List installed packages in the project's venv (pip list / pip freeze).

    ``project_id`` is **required**: it selects the registered project whose ``.venv``/``venv`` is used.
    """

    name = "project_pip_list"
    version = "1.0.0"
    descr = (
        "List installed Python packages in the project's venv (pip list or pip freeze)"
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["ProjectPipListCommand"]) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        Returns:
            JSON schema dict with top-level and per-parameter ``examples``.
        """
        return {
            "type": "object",
            "description": (
                "Runs ``python -m pip list`` or ``python -m pip freeze`` in the project sandbox. "
                "**Required:** ``project_id`` — must identify a **registered** project; pip uses only that "
                "project's ``.venv`` or ``venv`` under the resolved root. "
                "``list_format`` selects human-readable columns, JSON list output, or ``pip freeze`` lines. "
                "Requires ``.venv`` or ``venv`` under the project root."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "**Required.** Registered project UUID (from ``projectid`` or ``list_projects``). "
                        "Selects the project whose venv is listed; root path is resolved from the database."
                    ),
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                "list_format": {
                    "type": "string",
                    "enum": ["columns", "json", "freeze"],
                    "default": "columns",
                    "description": (
                        "``columns``: ``pip list`` (default); ``json``: "
                        "``pip list --format=json``; ``freeze``: ``pip freeze``."
                    ),
                    "examples": ["columns", "json", "freeze"],
                },
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "Optional timeout in seconds for the pip subprocess. "
                        "If exceeded, the process is killed; see ``timed_out`` in the response."
                    ),
                    "examples": [30, 60, 120],
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
            "examples": [
                {"project_id": "550e8400-e29b-41d4-a716-446655440000"},
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "list_format": "freeze",
                    "timeout_seconds": 60,
                },
            ],
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate list options and require an existing project."""
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    @classmethod
    def metadata(cls: type["ProjectPipListCommand"]) -> Dict[str, Any]:
        """Rich metadata for AI clients (aligned with ``run_project_module`` / ``run_project_script``)."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The ``project_pip_list`` command lists packages installed in the project's virtual "
                "environment by running ``python -m pip`` with either ``list`` or ``freeze`` semantics. "
                "``project_id`` is mandatory and picks exactly one registered project; listing never "
                "inspects another path or the server venv. "
                "It uses the same sandbox as other project commands: cwd and ``PYTHONPATH`` are the project root, "
                "and the interpreter is the project venv's Python. This is **runtime package inventory**, "
                "not static import analysis.\n\n"
                "Operation flow:\n"
                "1. Resolve project root from ``project_id``\n"
                "2. Map ``list_format`` to pip arguments: ``columns`` → ``pip list``; ``json`` → "
                "``pip list --format=json``; ``freeze`` → ``pip freeze``\n"
                "3. Run ``run_pip_in_project_sandbox`` under ``asyncio.to_thread``\n"
                "4. Persist stdout/stderr to ``<server log_dir>/project_pip/`` and return stdout/stderr, "
                "returncode, timed_out, the normalized ``list_format``, and ``pip_output_log_path``\n\n"
                "Important notes:\n"
                "- Invalid ``list_format`` values yield ``INVALID_PARAMS``\n"
                "- Missing venv yields ``VENV_NOT_FOUND``"
            ),
            "parameters": {
                "project_id": {
                    "description": (
                        "**Required.** Registered project UUID. Fails with ``VALIDATION_ERROR`` if the project "
                        "or root path is invalid. Pip runs only in that project's ``.venv``/``venv``."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "550e8400-e29b-41d4-a716-446655440000",
                        "c86dded6-6f93-4fb0-be54-b6d7b739eeb9",
                    ],
                },
                "list_format": {
                    "description": (
                        "Output style: ``columns`` (default table), ``json`` (machine-readable), "
                        "or ``freeze`` (``name==version`` lines)."
                    ),
                    "type": "string",
                    "required": False,
                    "enum": ["columns", "json", "freeze"],
                    "examples": ["columns", "json", "freeze"],
                },
                "timeout_seconds": {
                    "description": "Optional subprocess timeout in seconds.",
                    "type": "integer",
                    "required": False,
                    "minimum": 1,
                    "examples": [30, 60, 120],
                },
            },
            "usage_examples": [
                {
                    "description": "Default table listing",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    },
                    "explanation": "Runs ``pip list`` in the project venv.",
                },
                {
                    "description": "Freeze-style requirements lines",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "list_format": "freeze",
                    },
                    "explanation": "Runs ``pip freeze``; suitable for copying into a requirements file.",
                },
                {
                    "description": "JSON list for tooling",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "list_format": "json",
                        "timeout_seconds": 60,
                    },
                    "explanation": "Runs ``pip list --format=json`` with an optional timeout.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "Project not found or root path invalid",
                    "example": "Unknown ``project_id``",
                    "solution": "Register the project and ensure the root directory exists.",
                },
                "INVALID_PARAMS": {
                    "description": "``list_format`` is not one of columns, json, freeze",
                    "example": '``list_format``: ``"plain"``',
                    "solution": "Use ``columns``, ``json``, or ``freeze`` (case-insensitive).",
                },
                "INVALID_PATH": {
                    "description": "Project root path is not usable",
                    "example": "Resolved path is not a directory",
                    "solution": "Fix project registration paths on disk.",
                },
                "VENV_NOT_FOUND": {
                    "description": "Project venv missing",
                    "example": "No ``.venv``/``venv`` Python under root",
                    "solution": "Create a virtual environment in the project root.",
                },
                "INTERNAL_ERROR": {
                    "description": "Unexpected handler failure",
                    "example": "Unhandled exception",
                    "solution": "Check server logs.",
                },
            },
            "return_value": {
                "success": {
                    "description": "Pip completed or timed out",
                    "data": {
                        "stdout": "List/freeze output",
                        "stderr": "pip stderr",
                        "returncode": "Exit code (may be None if timed out)",
                        "timed_out": "Timeout flag",
                        "project_id": "Project UUID",
                        "list_format": "Normalized format: columns, json, or freeze",
                        "pip_output_log_path": "Absolute path to session log file, or null if write failed",
                        "pip_output_log_relative": "Path relative to server config dir when applicable",
                        "pip_logs_directory": "Resolved server log_dir",
                        "pip_log_write_error": "null on success",
                    },
                    "example": {
                        "stdout": "Package    Version\n---------- -------\npip        24.0\n",
                        "stderr": "",
                        "returncode": 0,
                        "timed_out": False,
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "list_format": "columns",
                        "pip_output_log_path": "/path/to/repo/logs/project_pip/project_pip_list_20260405T120000Z_a1b2c3d4.log",
                        "pip_output_log_relative": "logs/project_pip/project_pip_list_20260405T120000Z_a1b2c3d4.log",
                        "pip_logs_directory": "/path/to/repo/logs",
                        "pip_log_write_error": None,
                    },
                },
                "error": {
                    "description": "Validation, params, path, venv, or internal error",
                    "code": (
                        "VALIDATION_ERROR, INVALID_PARAMS, INVALID_PATH, "
                        "VENV_NOT_FOUND, INTERNAL_ERROR"
                    ),
                    "message": "Human-readable message",
                    "data": "Optional validation details",
                },
            },
            "best_practices": [
                "Use ``freeze`` when you need ``pip install -r``-compatible lines",
                "Use ``json`` when parsing output programmatically",
                "Set ``timeout_seconds`` if the environment is very large or slow",
            ],
        }

    async def execute(
        self: "ProjectPipListCommand",
        project_id: str,
        list_format: str = "columns",
        timeout_seconds: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """List distributions installed in the project sandbox."""
        try:
            root_path = BaseMCPCommand._resolve_project_root(project_id)
            fmt = (list_format or "columns").strip().lower()
            if fmt == "freeze":
                pip_args = ["freeze"]
            elif fmt == "json":
                pip_args = ["list", "--format=json"]
            elif fmt == "columns":
                pip_args = ["list"]
            else:
                return ErrorResult(
                    code="INVALID_PARAMS",
                    message=(
                        f"Invalid list_format: {list_format!r}. "
                        "Use columns, json, or freeze."
                    ),
                )
            try:
                result = await asyncio.to_thread(
                    run_pip_in_project_sandbox,
                    root_path,
                    pip_args,
                    timeout_seconds,
                )
            except ValueError as e:
                return ErrorResult(code="INVALID_PATH", message=str(e))
            except VenvNotFoundError as e:
                return ErrorResult(code="VENV_NOT_FOUND", message=str(e))
            data = {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "timed_out": result.timed_out,
                "project_id": project_id,
                "list_format": fmt,
            }
            data.update(
                _merge_pip_log_data(
                    ProjectPipListCommand.name,
                    project_id,
                    pip_args,
                    result,
                    kwargs,
                )
            )
            return SuccessResult(data=data)
        except Exception as e:
            from ..core.exceptions import ValidationError

            if isinstance(e, ValidationError):
                return ErrorResult(
                    code="VALIDATION_ERROR",
                    message=e.message,
                    data=getattr(e, "details", {}),
                )
            logger.exception("project_pip_list failed: %s", e)
            return ErrorResult(code="INTERNAL_ERROR", message=str(e))


class ProjectPipShowCommand(BaseMCPCommand):
    """
    Show metadata for installed packages (pip show).

    ``project_id`` is **required**: it selects the registered project whose ``.venv``/``venv`` is used.
    """

    name = "project_pip_show"
    version = "1.0.0"
    descr = (
        "Show details for installed Python packages in the project's venv (pip show)"
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["ProjectPipShowCommand"]) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        Returns:
            JSON schema dict with top-level and per-parameter ``examples``.
        """
        return {
            "type": "object",
            "description": (
                "Runs ``python -m pip show`` for one or more distribution names in the project venv. "
                "**Required:** ``project_id`` — must identify a **registered** project; pip uses only that "
                "project's ``.venv`` or ``venv``. "
                "Shows metadata (version, location, dependencies) for **installed** packages only."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "**Required.** Registered project UUID (from ``projectid`` or ``list_projects``). "
                        "Selects the project whose venv is queried; root path is resolved from the database."
                    ),
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                "packages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": (
                        "One or more distribution names as understood by pip (e.g. ``pip``, ``requests``)."
                    ),
                    "examples": [["pip"], ["requests", "urllib3"]],
                },
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "Optional timeout in seconds for the pip subprocess. "
                        "If exceeded, see ``timed_out`` in the success payload."
                    ),
                    "examples": [30, 60],
                },
            },
            "required": ["project_id", "packages"],
            "additionalProperties": False,
            "examples": [
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "packages": ["pip"],
                },
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "packages": ["requests", "charset-normalizer"],
                    "timeout_seconds": 60,
                },
            ],
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate package names and require an existing project."""
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    @classmethod
    def metadata(cls: type["ProjectPipShowCommand"]) -> Dict[str, Any]:
        """Rich metadata for AI clients (aligned with ``run_project_module`` / ``run_project_script``)."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The ``project_pip_show`` command runs ``python -m pip show`` for one or more "
                "distribution **names** in the project's venv. ``project_id`` is mandatory and selects "
                "the registered project; pip never targets another root or the server venv. "
                "It returns pip's human-readable metadata "
                "block (version, summary, location, requires, etc.). This reflects **installed** "
                "packages in the sandbox venv, not static analysis of source imports.\n\n"
                "Operation flow:\n"
                "1. Resolve project root and strip empty package strings\n"
                "2. If no non-empty names remain, return ``INVALID_PARAMS``\n"
                "3. Invoke ``pip show <names...>`` via ``run_pip_in_project_sandbox``\n"
                "4. Persist stdout/stderr to ``<server log_dir>/project_pip/`` and return stdout/stderr, "
                "process metadata, and ``pip_output_log_path``\n\n"
                "Note: pip may exit non-zero if a name is not installed; check ``returncode`` and stderr."
            ),
            "parameters": {
                "project_id": {
                    "description": (
                        "**Required.** Registered project UUID; invalid projects yield ``VALIDATION_ERROR``. "
                        "Pip runs only in that project's ``.venv``/``venv``."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "550e8400-e29b-41d4-a716-446655440000",
                        "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                    ],
                },
                "packages": {
                    "description": (
                        "Non-empty list of distribution names. After stripping, at least one name is required."
                    ),
                    "type": "array",
                    "required": True,
                    "items": {"type": "string"},
                    "minItems": 1,
                    "examples": [
                        ["pip"],
                        ["requests", "idna"],
                    ],
                },
                "timeout_seconds": {
                    "description": "Optional subprocess timeout in seconds.",
                    "type": "integer",
                    "required": False,
                    "minimum": 1,
                    "examples": [30, 60],
                },
            },
            "usage_examples": [
                {
                    "description": "Show metadata for pip itself",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "packages": ["pip"],
                    },
                    "explanation": "Runs ``pip show pip`` inside the project venv.",
                },
                {
                    "description": "Show multiple packages",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "packages": ["requests", "certifi"],
                        "timeout_seconds": 60,
                    },
                    "explanation": "Shows combined output for several installed distributions.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "Project not found or root invalid",
                    "example": "Unknown ``project_id``",
                    "solution": "Fix registration or use a valid UUID from ``list_projects``.",
                },
                "INVALID_PARAMS": {
                    "description": "No usable package names after stripping",
                    "example": '``packages``: ["", "  "]',
                    "solution": "Provide at least one non-empty distribution name.",
                },
                "INVALID_PATH": {
                    "description": "Project root path error",
                    "example": "Path not a directory",
                    "solution": "Ensure the project root exists on disk.",
                },
                "VENV_NOT_FOUND": {
                    "description": "Missing project venv",
                    "example": "No ``.venv``/``venv``",
                    "solution": "Create a venv under the project root.",
                },
                "INTERNAL_ERROR": {
                    "description": "Unexpected failure",
                    "example": "Unhandled exception",
                    "solution": "Check server logs.",
                },
            },
            "return_value": {
                "success": {
                    "description": "Subprocess finished (pip may still report errors in stderr or non-zero code)",
                    "data": {
                        "stdout": "pip show output",
                        "stderr": "pip stderr",
                        "returncode": "Process exit code",
                        "timed_out": "Timeout flag",
                        "project_id": "Project UUID",
                        "packages": "Sanitized list of names passed to pip",
                        "pip_output_log_path": "Absolute path to session log file, or null if write failed",
                        "pip_output_log_relative": "Path relative to server config dir when applicable",
                        "pip_logs_directory": "Resolved server log_dir",
                        "pip_log_write_error": "null on success",
                    },
                    "example": {
                        "stdout": "Name: pip\nVersion: 24.0\n...",
                        "stderr": "",
                        "returncode": 0,
                        "timed_out": False,
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "packages": ["pip"],
                        "pip_output_log_path": "/path/to/repo/logs/project_pip/project_pip_show_20260405T120000Z_a1b2c3d4.log",
                        "pip_output_log_relative": "logs/project_pip/project_pip_show_20260405T120000Z_a1b2c3d4.log",
                        "pip_logs_directory": "/path/to/repo/logs",
                        "pip_log_write_error": None,
                    },
                },
                "error": {
                    "description": "Validation or environment error before/during sandbox setup",
                    "code": (
                        "VALIDATION_ERROR, INVALID_PARAMS, INVALID_PATH, "
                        "VENV_NOT_FOUND, INTERNAL_ERROR"
                    ),
                    "message": "Human-readable message",
                    "data": "Optional validation details",
                },
            },
            "best_practices": [
                "Use exact distribution names as shown by ``project_pip_list``",
                "Inspect ``returncode`` and stderr when a package might be missing",
                "Prefer listing one package when debugging a single dependency",
            ],
        }

    async def execute(
        self: "ProjectPipShowCommand",
        project_id: str,
        packages: List[str],
        timeout_seconds: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Show pip metadata for packages in the project sandbox."""
        try:
            root_path = BaseMCPCommand._resolve_project_root(project_id)
            pkgs = _strip_packages(packages)
            if not pkgs:
                return ErrorResult(
                    code="INVALID_PARAMS",
                    message="packages must contain at least one non-empty name.",
                )
            pip_args = ["show"] + pkgs
            try:
                result = await asyncio.to_thread(
                    run_pip_in_project_sandbox,
                    root_path,
                    pip_args,
                    timeout_seconds,
                )
            except ValueError as e:
                return ErrorResult(code="INVALID_PATH", message=str(e))
            except VenvNotFoundError as e:
                return ErrorResult(code="VENV_NOT_FOUND", message=str(e))
            data = {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "timed_out": result.timed_out,
                "project_id": project_id,
                "packages": pkgs,
            }
            data.update(
                _merge_pip_log_data(
                    ProjectPipShowCommand.name,
                    project_id,
                    pip_args,
                    result,
                    kwargs,
                )
            )
            return SuccessResult(data=data)
        except Exception as e:
            from ..core.exceptions import ValidationError

            if isinstance(e, ValidationError):
                return ErrorResult(
                    code="VALIDATION_ERROR",
                    message=e.message,
                    data=getattr(e, "details", {}),
                )
            logger.exception("project_pip_show failed: %s", e)
            return ErrorResult(code="INTERNAL_ERROR", message=str(e))


class ProjectPipUninstallCommand(BaseMCPCommand):
    """
    Remove packages from the project's venv (pip uninstall -y).

    ``project_id`` is **required**: it selects the registered project whose ``.venv``/``venv`` is used.
    """

    name = "project_pip_uninstall"
    version = "1.0.0"
    descr = (
        "Uninstall Python distribution packages from the project's venv (pip uninstall)"
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["ProjectPipUninstallCommand"]) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        Returns:
            JSON schema dict with top-level and per-parameter ``examples``.
        """
        return {
            "type": "object",
            "description": (
                "Runs ``python -m pip uninstall -y`` for the given distribution names in the project "
                "sandbox. **Required:** ``project_id`` — must identify a **registered** project; pip uses only "
                "that project's ``.venv`` or ``venv``. "
                "Uninstall is **non-interactive** (``-y``). Only affects that project venv."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "**Required.** Registered project UUID (from ``projectid`` or ``list_projects``). "
                        "Selects the project whose venv is modified; root path is resolved from the database."
                    ),
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                "packages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": (
                        "Distribution names to remove. At least one non-empty name after trimming is required."
                    ),
                    "examples": [["foobar"], ["pkg-a", "pkg-b"]],
                },
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "Optional timeout in seconds for the pip subprocess. "
                        "If exceeded, see ``timed_out`` in the success payload."
                    ),
                    "examples": [60, 120],
                },
            },
            "required": ["project_id", "packages"],
            "additionalProperties": False,
            "examples": [
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "packages": ["some-test-package"],
                },
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "packages": ["a", "b"],
                    "timeout_seconds": 120,
                },
            ],
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate uninstall package names and require an existing project."""
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    @classmethod
    def metadata(cls: type["ProjectPipUninstallCommand"]) -> Dict[str, Any]:
        """Rich metadata for AI clients (aligned with ``run_project_module`` / ``run_project_script``)."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The ``project_pip_uninstall`` command runs ``python -m pip uninstall -y`` for one or more "
                "distribution names in the project's venv. ``project_id`` is mandatory and selects the "
                "registered project; uninstall never targets another path or the server venv. "
                "It is **destructive** for the venv: removed "
                "packages are gone until reinstalled. The command does not modify project source code or "
                "perform static dependency analysis.\n\n"
                "Operation flow:\n"
                "1. Resolve project root and strip empty package strings\n"
                "2. If no names remain, return ``INVALID_PARAMS``\n"
                "3. Run ``pip uninstall -y <names...>`` in the sandbox\n"
                "4. Persist stdout/stderr to ``<server log_dir>/project_pip/`` and return stdout/stderr, "
                "process metadata, and ``pip_output_log_path``\n\n"
                "Safety: ``-y`` avoids interactive prompts; double-check package names before calling."
            ),
            "parameters": {
                "project_id": {
                    "description": (
                        "**Required.** Registered project UUID; invalid projects yield ``VALIDATION_ERROR``. "
                        "Pip runs only in that project's ``.venv``/``venv``."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "550e8400-e29b-41d4-a716-446655440000",
                        "c86dded6-6f93-4fb0-be54-b6d7b739eeb9",
                    ],
                },
                "packages": {
                    "description": (
                        "List of distribution names to remove. At least one non-empty name after stripping."
                    ),
                    "type": "array",
                    "required": True,
                    "items": {"type": "string"},
                    "minItems": 1,
                    "examples": [
                        ["requests"],
                        ["tmp-pkg", "another-pkg"],
                    ],
                },
                "timeout_seconds": {
                    "description": "Optional subprocess timeout in seconds.",
                    "type": "integer",
                    "required": False,
                    "minimum": 1,
                    "examples": [60, 120],
                },
            },
            "usage_examples": [
                {
                    "description": "Remove a single package",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "packages": ["obsolete-dep"],
                    },
                    "explanation": "Runs ``pip uninstall -y obsolete-dep`` in the project venv.",
                },
                {
                    "description": "Remove multiple packages with timeout",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "packages": ["pkg-a", "pkg-b"],
                        "timeout_seconds": 120,
                    },
                    "explanation": "Batch uninstall with a generous timeout for slow filesystems.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "Project not found or root invalid",
                    "example": "Unknown ``project_id``",
                    "solution": "Fix registration or project root path.",
                },
                "INVALID_PARAMS": {
                    "description": "No usable package names after stripping",
                    "example": "``packages``: []",
                    "solution": "Provide at least one distribution name.",
                },
                "INVALID_PATH": {
                    "description": "Project root path error",
                    "example": "Not a directory",
                    "solution": "Ensure the project root exists.",
                },
                "VENV_NOT_FOUND": {
                    "description": "Missing project venv",
                    "example": "No ``.venv``/``venv``",
                    "solution": "Create a venv under the project root.",
                },
                "INTERNAL_ERROR": {
                    "description": "Unexpected failure",
                    "example": "Unhandled exception",
                    "solution": "Check server logs.",
                },
            },
            "return_value": {
                "success": {
                    "description": "Subprocess completed (pip may still report warnings in stderr)",
                    "data": {
                        "stdout": "pip uninstall output",
                        "stderr": "pip stderr",
                        "returncode": "Process exit code",
                        "timed_out": "Timeout flag",
                        "project_id": "Project UUID",
                        "packages": "Sanitized list of names passed to pip",
                        "pip_output_log_path": "Absolute path to session log file, or null if write failed",
                        "pip_output_log_relative": "Path relative to server config dir when applicable",
                        "pip_logs_directory": "Resolved server log_dir",
                        "pip_log_write_error": "null on success",
                    },
                    "example": {
                        "stdout": "Found existing installation: obsolete-dep 1.0\nUninstalling obsolete-dep-1.0:\n  Successfully uninstalled obsolete-dep-1.0\n",
                        "stderr": "",
                        "returncode": 0,
                        "timed_out": False,
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "packages": ["obsolete-dep"],
                        "pip_output_log_path": "/path/to/repo/logs/project_pip/project_pip_uninstall_20260405T120000Z_a1b2c3d4.log",
                        "pip_output_log_relative": "logs/project_pip/project_pip_uninstall_20260405T120000Z_a1b2c3d4.log",
                        "pip_logs_directory": "/path/to/repo/logs",
                        "pip_log_write_error": None,
                    },
                },
                "error": {
                    "description": "Validation or environment error",
                    "code": (
                        "VALIDATION_ERROR, INVALID_PARAMS, INVALID_PATH, "
                        "VENV_NOT_FOUND, INTERNAL_ERROR"
                    ),
                    "message": "Human-readable message",
                    "data": "Optional validation details",
                },
            },
            "best_practices": [
                "Confirm package names with ``project_pip_list`` or ``project_pip_show`` before uninstalling",
                "Avoid uninstalling packages still required by the project unless you intend to break imports",
                "Use a timeout on shared or slow disks",
            ],
        }

    async def execute(
        self: "ProjectPipUninstallCommand",
        project_id: str,
        packages: List[str],
        timeout_seconds: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Uninstall packages from the project sandbox without prompting."""
        try:
            root_path = BaseMCPCommand._resolve_project_root(project_id)
            pkgs = _strip_packages(packages)
            if not pkgs:
                return ErrorResult(
                    code="INVALID_PARAMS",
                    message="packages must contain at least one non-empty name.",
                )
            pip_args = ["uninstall", "-y"] + pkgs
            try:
                result = await asyncio.to_thread(
                    run_pip_in_project_sandbox,
                    root_path,
                    pip_args,
                    timeout_seconds,
                )
            except ValueError as e:
                return ErrorResult(code="INVALID_PATH", message=str(e))
            except VenvNotFoundError as e:
                return ErrorResult(code="VENV_NOT_FOUND", message=str(e))
            data = {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "timed_out": result.timed_out,
                "project_id": project_id,
                "packages": pkgs,
            }
            data.update(
                _merge_pip_log_data(
                    ProjectPipUninstallCommand.name,
                    project_id,
                    pip_args,
                    result,
                    kwargs,
                )
            )
            return SuccessResult(data=data)
        except Exception as e:
            from ..core.exceptions import ValidationError

            if isinstance(e, ValidationError):
                return ErrorResult(
                    code="VALIDATION_ERROR",
                    message=e.message,
                    data=getattr(e, "details", {}),
                )
            logger.exception("project_pip_uninstall failed: %s", e)
            return ErrorResult(code="INTERNAL_ERROR", message=str(e))


class ProjectPipCheckCommand(BaseMCPCommand):
    """
    Check whether distribution names are installed in the project venv (exact name match).

    Uses ``pip list --format=json`` in the sandbox; compares **normalized** PEP 503 names
    (no network, no PyPI).
    """

    name = "project_pip_check"
    version = "1.0.0"
    descr = (
        "Check exact presence of named distributions in the project's venv using pip list JSON "
        "(no PyPI access)"
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["ProjectPipCheckCommand"]) -> Dict[str, Any]:
        """Return the schema for checking installed distribution names."""
        return {
            "type": "object",
            "description": (
                "Runs ``python -m pip list --format=json`` once in the registered project's sandbox, "
                "then reports whether each requested **distribution name** is present in that "
                "environment. Matching uses PEP 503–style normalization (case-insensitive; "
                "underscores vs hyphens). Requirement strings like ``pkg==1.0`` use only the "
                "project name portion for lookup. **No PyPI or index access.** "
                "**Required:** ``project_id`` and non-empty ``packages``."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "**Required.** Registered project UUID. Pip uses only that project's "
                        "``.venv`` or ``venv``."
                    ),
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                "packages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": (
                        "One or more distribution names or requirement-style strings; only the "
                        "project name is used for presence checks (e.g. ``requests``, ``pip``, "
                        "``numpy>=1.0``)."
                    ),
                    "examples": [["pip", "setuptools"], ["requests", "httpx"]],
                },
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional timeout in seconds for the pip subprocess.",
                    "examples": [30, 60, 120],
                },
            },
            "required": ["project_id", "packages"],
            "additionalProperties": False,
            "examples": [
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "packages": ["pip", "wheel"],
                },
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "packages": ["requests>=2.0"],
                    "timeout_seconds": 60,
                },
            ],
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate requested distributions and require an existing project."""
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    @classmethod
    def metadata(cls: type["ProjectPipCheckCommand"]) -> Dict[str, Any]:
        """Return registration metadata for installed-package checks."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The ``project_pip_check`` command answers whether specific **distributions** are "
                "installed in the project's venv. It runs ``python -m pip list --format=json`` "
                "exactly once in the project sandbox (same interpreter and cwd rules as other "
                "``project_pip_*`` commands), parses the JSON, and for each requested string "
                "extracts a **project name** (strip extras and version clauses) and tests "
                "membership using **normalized** names—so ``PyYAML`` and ``pyyaml`` match the "
                "same installed row. This is **not** ``pip install`` dry-run and does not contact "
                "PyPI; it only reflects what is already installed.\n\n"
                "Operation flow:\n"
                "1. Resolve project root from ``project_id``\n"
                "2. Run ``pip list --format=json`` via ``run_pip_in_project_sandbox``\n"
                "3. Parse JSON into an index keyed by normalized distribution name\n"
                "4. For each entry in ``packages``, set ``installed`` and copy ``name``/``version`` "
                "from the matching row when present\n"
                "5. Append session log fields from ``write_project_pip_session_log``\n\n"
                "If pip exits non-zero or stdout is not valid JSON, ``parse_error`` may be set and "
                "``results`` entries default to ``installed: false``."
            ),
            "parameters": {
                "project_id": {
                    "description": (
                        "**Required.** Registered project UUID; invalid projects yield ``VALIDATION_ERROR``."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "550e8400-e29b-41d4-a716-446655440000",
                        "c86dded6-6f93-4fb0-be54-b6d7b739eeb9",
                    ],
                },
                "packages": {
                    "description": (
                        "Non-empty list of names or requirement-like strings; empty tokens are skipped; "
                        "if none remain, ``INVALID_PARAMS``."
                    ),
                    "type": "array",
                    "required": True,
                    "items": {"type": "string"},
                    "minItems": 1,
                    "examples": [["pip"], ["requests", "charset-normalizer"]],
                },
                "timeout_seconds": {
                    "description": "Optional subprocess timeout in seconds.",
                    "type": "integer",
                    "required": False,
                    "minimum": 1,
                    "examples": [30, 60],
                },
            },
            "usage_examples": [
                {
                    "description": "Verify setuptools and pip",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "packages": ["pip", "setuptools"],
                    },
                    "explanation": "Returns structured rows with ``installed`` true/false per name.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "Project not found or root invalid",
                    "example": "Unknown ``project_id``",
                    "solution": "Use ``list_projects`` / ``create_project``.",
                },
                "INVALID_PARAMS": {
                    "description": "No usable package strings after stripping",
                    "example": '``packages``: ["", "  "]',
                    "solution": "Provide at least one non-empty name.",
                },
                "INVALID_PATH": {
                    "description": "Project root path error",
                    "example": "Not a directory",
                    "solution": "Fix paths on disk.",
                },
                "VENV_NOT_FOUND": {
                    "description": "Missing ``.venv``/``venv``",
                    "example": "No venv under root",
                    "solution": "Create a venv in the project root.",
                },
                "INTERNAL_ERROR": {
                    "description": "Unexpected handler failure",
                    "example": "Unhandled exception",
                    "solution": "Check server logs.",
                },
            },
            "return_value": {
                "success": {
                    "description": "Always returns subprocess fields plus structured ``results`` when pip ran",
                    "data": {
                        "stdout": "Raw ``pip list --format=json`` stdout",
                        "stderr": "pip stderr",
                        "returncode": "Exit code (may be None if timed out)",
                        "timed_out": "Timeout flag",
                        "project_id": "Project UUID",
                        "pip_args": "``['list', '--format=json']``",
                        "results": "List of per-request objects (requested, normalized, installed, name, version)",
                        "all_requested_installed": "True if every non-skipped request resolved to installed",
                        "parse_error": "null or message if JSON could not be parsed",
                        "pip_output_log_path": "Session log path or null",
                        "pip_output_log_relative": "Relative log path when applicable",
                        "pip_logs_directory": "Server log_dir",
                        "pip_log_write_error": "null on success",
                    },
                    "example": {
                        "stdout": '[{"name": "pip", "version": "24.0"}]\n',
                        "stderr": "",
                        "returncode": 0,
                        "timed_out": False,
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "pip_args": ["list", "--format=json"],
                        "results": [
                            {
                                "requested": "pip",
                                "normalized": "pip",
                                "installed": True,
                                "name": "pip",
                                "version": "24.0",
                            }
                        ],
                        "all_requested_installed": True,
                        "parse_error": None,
                        "pip_output_log_path": "/path/to/repo/logs/project_pip/project_pip_check_20260405T120000Z_a1b2c3d4.log",
                        "pip_output_log_relative": "logs/project_pip/project_pip_check_20260405T120000Z_a1b2c3d4.log",
                        "pip_logs_directory": "/path/to/repo/logs",
                        "pip_log_write_error": None,
                    },
                },
                "error": {
                    "description": "Validation or environment error",
                    "code": (
                        "VALIDATION_ERROR, INVALID_PARAMS, INVALID_PATH, "
                        "VENV_NOT_FOUND, INTERNAL_ERROR"
                    ),
                    "message": "Human-readable message",
                    "data": "Optional details",
                },
            },
            "best_practices": [
                "Use names as shown by ``project_pip_list`` with ``list_format``: ``json``",
                "Remember normalization: ``Some_Pkg`` and ``some-pkg`` match the same install",
                "Do not use this for PyPI availability; only installed packages are considered",
            ],
        }

    async def execute(
        self: "ProjectPipCheckCommand",
        project_id: str,
        packages: List[str],
        timeout_seconds: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Report which requested distributions are installed in the sandbox."""
        try:
            root_path = BaseMCPCommand._resolve_project_root(project_id)
            pkgs = _strip_packages(packages)
            if not pkgs:
                return ErrorResult(
                    code="INVALID_PARAMS",
                    message="packages must contain at least one non-empty name.",
                )
            pip_args = ["list", "--format=json"]
            try:
                result = await asyncio.to_thread(
                    run_pip_in_project_sandbox,
                    root_path,
                    pip_args,
                    timeout_seconds,
                )
            except ValueError as e:
                return ErrorResult(code="INVALID_PATH", message=str(e))
            except VenvNotFoundError as e:
                return ErrorResult(code="VENV_NOT_FOUND", message=str(e))

            rows, parse_err = _parse_pip_list_json(result.stdout)
            index = _installed_by_normalized_name(rows) if parse_err is None else {}

            results: List[Dict[str, Any]] = []
            for raw in pkgs:
                proj = _project_name_from_requirement_spec(raw)
                norm = _normalize_dist_name(proj) if proj else ""
                row = index.get(norm) if norm else None
                installed = bool(row is not None)
                results.append(
                    {
                        "requested": raw,
                        "normalized": norm,
                        "installed": installed,
                        "name": str(row.get("name")) if row else None,
                        "version": str(row.get("version")) if row else None,
                    }
                )

            all_installed = all(r["installed"] for r in results) if results else True

            data: Dict[str, Any] = {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "timed_out": result.timed_out,
                "project_id": project_id,
                "pip_args": pip_args,
                "results": results,
                "all_requested_installed": all_installed,
                "parse_error": parse_err,
            }
            data.update(
                _merge_pip_log_data(
                    ProjectPipCheckCommand.name,
                    project_id,
                    pip_args,
                    result,
                    kwargs,
                )
            )
            return SuccessResult(data=data)
        except Exception as e:
            from ..core.exceptions import ValidationError

            if isinstance(e, ValidationError):
                return ErrorResult(
                    code="VALIDATION_ERROR",
                    message=e.message,
                    data=getattr(e, "details", {}),
                )
            logger.exception("project_pip_check failed: %s", e)
            return ErrorResult(code="INTERNAL_ERROR", message=str(e))


class ProjectPipSearchCommand(BaseMCPCommand):
    """
    Search or list packages installed in the project venv (no PyPI).

    Uses ``pip list --format=json`` and filters rows in-process only.
    """

    name = "project_pip_search"
    version = "1.0.0"
    descr = "Search or list installed Python packages in the project's venv (in-process filter; no PyPI)"
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["ProjectPipSearchCommand"]) -> Dict[str, Any]:
        """Return the schema for filtering installed project distributions."""
        return {
            "type": "object",
            "description": (
                "Runs ``python -m pip list --format=json`` in the registered project's sandbox, "
                "then optionally filters rows by ``query`` using ``match_mode``. **Only** packages "
                "already installed in that venv are returned—**no PyPI or index search**. "
                "**Required:** ``project_id``."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "**Required.** Registered project UUID. Uses that project's ``.venv``/``venv``."
                    ),
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                "query": {
                    "type": ["string", "null"],
                    "description": (
                        "Optional filter string. When null, empty, or omitted, all installed packages "
                        "are returned (same data as unparsed ``pip list --format=json``, as structured rows). "
                        "When set, ``match_mode`` controls how ``query`` matches each package ``name`` "
                        "(and ``substring`` also matches ``version`` case-insensitively)."
                    ),
                    "examples": ["req", "pip", None, ""],
                },
                "match_mode": {
                    "type": "string",
                    "enum": ["substring", "prefix", "exact"],
                    "default": "substring",
                    "description": (
                        "``substring``: ``query`` contained in name or version; ``prefix``: name starts with "
                        "``query``; ``exact``: normalized name equals normalized ``query``."
                    ),
                    "examples": ["substring", "prefix", "exact"],
                },
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional timeout in seconds for the pip subprocess.",
                    "examples": [30, 60, 120],
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
            "examples": [
                {"project_id": "550e8400-e29b-41d4-a716-446655440000"},
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "query": "yaml",
                    "match_mode": "substring",
                },
            ],
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate search options and require an existing project."""
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    @classmethod
    def metadata(cls: type["ProjectPipSearchCommand"]) -> Dict[str, Any]:
        """Return registration metadata for installed-package searches."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The ``project_pip_search`` command lists or filters **installed** packages in the "
                "project venv. It never calls ``pip search`` (removed upstream) and never queries "
                "PyPI. It runs ``python -m pip list --format=json`` once, parses the JSON, and "
                "applies an optional in-memory filter. This is useful for finding installed packages "
                "by substring (e.g. ``yaml``) without scanning raw stdout in the client.\n\n"
                "Operation flow:\n"
                "1. Resolve project root from ``project_id``\n"
                "2. Run ``pip list --format=json`` in the sandbox\n"
                "3. Parse JSON; if ``query`` is empty, keep all rows\n"
                "4. Else filter by ``match_mode`` (substring / prefix / exact on normalized name; "
                "substring also checks ``version``)\n"
                "5. Return ``matches``, ``match_count``, subprocess fields, and session log paths\n\n"
                "Invalid ``match_mode`` yields ``INVALID_PARAMS``."
            ),
            "parameters": {
                "project_id": {
                    "description": "**Required.** Registered project UUID.",
                    "type": "string",
                    "required": True,
                    "examples": [
                        "550e8400-e29b-41d4-a716-446655440000",
                    ],
                },
                "query": {
                    "description": "Optional filter; omit or empty to return every installed package.",
                    "type": ["string", "null"],
                    "required": False,
                    "examples": ["req", "pip", None],
                },
                "match_mode": {
                    "description": "How ``query`` matches distribution names (and version for substring).",
                    "type": "string",
                    "required": False,
                    "enum": ["substring", "prefix", "exact"],
                    "examples": ["substring", "prefix", "exact"],
                },
                "timeout_seconds": {
                    "description": "Optional subprocess timeout in seconds.",
                    "type": "integer",
                    "required": False,
                    "minimum": 1,
                    "examples": [60, 120],
                },
            },
            "usage_examples": [
                {
                    "description": "List every installed package as structured rows",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    },
                    "explanation": "``query`` omitted; ``matches`` mirrors ``pip list --format=json``.",
                },
                {
                    "description": "Find packages with “test” in the name or version",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "query": "test",
                        "match_mode": "substring",
                    },
                    "explanation": "Case-insensitive substring filter only within installed packages.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "Project not found",
                    "example": "Bad ``project_id``",
                    "solution": "Register the project.",
                },
                "INVALID_PARAMS": {
                    "description": "Unknown ``match_mode``",
                    "example": '``match_mode``: ``"fuzzy"``',
                    "solution": "Use ``substring``, ``prefix``, or ``exact``.",
                },
                "INVALID_PATH": {
                    "description": "Project root invalid",
                    "example": "Missing directory",
                    "solution": "Fix registration.",
                },
                "VENV_NOT_FOUND": {
                    "description": "No project venv",
                    "example": "No ``.venv``/``venv``",
                    "solution": "Create a venv.",
                },
                "INTERNAL_ERROR": {
                    "description": "Unexpected failure",
                    "example": "Unhandled exception",
                    "solution": "Check server logs.",
                },
            },
            "return_value": {
                "success": {
                    "description": "Subprocess completed; structured matches when JSON parsed",
                    "data": {
                        "stdout": "Raw pip JSON stdout",
                        "stderr": "pip stderr",
                        "returncode": "Exit code",
                        "timed_out": "Timeout flag",
                        "project_id": "UUID",
                        "pip_args": "['list', '--format=json']",
                        "query": "Filter used (null if none)",
                        "match_mode": "Normalized mode string",
                        "matches": "List of objects from pip JSON rows",
                        "match_count": "len(matches)",
                        "parse_error": "null or parse failure message",
                        "pip_output_log_path": "Session log path",
                        "pip_output_log_relative": "Relative path",
                        "pip_logs_directory": "log_dir",
                        "pip_log_write_error": "null on success",
                    },
                    "example": {
                        "stdout": '[{"name": "pip", "version": "24.0"}]\n',
                        "stderr": "",
                        "returncode": 0,
                        "timed_out": False,
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "pip_args": ["list", "--format=json"],
                        "query": "pip",
                        "match_mode": "substring",
                        "matches": [{"name": "pip", "version": "24.0"}],
                        "match_count": 1,
                        "parse_error": None,
                        "pip_output_log_path": "/path/to/repo/logs/project_pip/project_pip_search_20260405T120000Z_a1b2c3d4.log",
                        "pip_output_log_relative": "logs/project_pip/project_pip_search_20260405T120000Z_a1b2c3d4.log",
                        "pip_logs_directory": "/path/to/repo/logs",
                        "pip_log_write_error": None,
                    },
                },
                "error": {
                    "description": "Validation or environment error",
                    "code": (
                        "VALIDATION_ERROR, INVALID_PARAMS, INVALID_PATH, "
                        "VENV_NOT_FOUND, INTERNAL_ERROR"
                    ),
                    "message": "Human-readable message",
                    "data": "Optional details",
                },
            },
            "best_practices": [
                "Omit ``query`` when you need the full inventory as structured data",
                "Use ``exact`` when checking one known distribution name",
                "This command does not replace ``project_pip_check`` for yes/no presence over a known list",
            ],
        }

    @staticmethod
    def _filter_rows(
        rows: List[Dict[str, Any]],
        query: str,
        match_mode: str,
    ) -> List[Dict[str, Any]]:
        """Filter pip-list rows by normalized exact, prefix, or substring match."""
        q = (query or "").strip()
        if not q:
            return list(rows)
        qn = _normalize_dist_name(q)
        q_lower = q.lower()
        out: List[Dict[str, Any]] = []
        for row in rows:
            name = str(row.get("name", ""))
            ver = str(row.get("version", ""))
            nn = _normalize_dist_name(name)
            if match_mode == "exact":
                if nn == qn:
                    out.append(row)
            elif match_mode == "prefix":
                if nn.startswith(qn):
                    out.append(row)
            else:
                if q_lower in name.lower() or q_lower in ver.lower():
                    out.append(row)
        return out

    async def execute(
        self: "ProjectPipSearchCommand",
        project_id: str,
        query: Optional[str] = None,
        match_mode: str = "substring",
        timeout_seconds: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """List installed distributions and filter them without querying PyPI."""
        try:
            root_path = BaseMCPCommand._resolve_project_root(project_id)
            fmt = (match_mode or "substring").strip().lower()
            if fmt not in ("substring", "prefix", "exact"):
                return ErrorResult(
                    code="INVALID_PARAMS",
                    message=(
                        f"Invalid match_mode: {match_mode!r}. "
                        "Use substring, prefix, or exact."
                    ),
                )
            pip_args = ["list", "--format=json"]
            try:
                result = await asyncio.to_thread(
                    run_pip_in_project_sandbox,
                    root_path,
                    pip_args,
                    timeout_seconds,
                )
            except ValueError as e:
                return ErrorResult(code="INVALID_PATH", message=str(e))
            except VenvNotFoundError as e:
                return ErrorResult(code="VENV_NOT_FOUND", message=str(e))

            rows, parse_err = _parse_pip_list_json(result.stdout)
            q_raw = query if isinstance(query, str) else ""
            matches = self._filter_rows(rows, q_raw, fmt) if parse_err is None else []

            data: Dict[str, Any] = {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "timed_out": result.timed_out,
                "project_id": project_id,
                "pip_args": pip_args,
                "query": q_raw.strip() if q_raw.strip() else None,
                "match_mode": fmt,
                "matches": matches,
                "match_count": len(matches),
                "parse_error": parse_err,
            }
            data.update(
                _merge_pip_log_data(
                    ProjectPipSearchCommand.name,
                    project_id,
                    pip_args,
                    result,
                    kwargs,
                )
            )
            return SuccessResult(data=data)
        except Exception as e:
            from ..core.exceptions import ValidationError

            if isinstance(e, ValidationError):
                return ErrorResult(
                    code="VALIDATION_ERROR",
                    message=e.message,
                    data=getattr(e, "details", {}),
                )
            logger.exception("project_pip_search failed: %s", e)
            return ErrorResult(code="INTERNAL_ERROR", message=str(e))
