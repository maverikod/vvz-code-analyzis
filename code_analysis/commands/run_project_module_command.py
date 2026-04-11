"""
Run project module MCP command.

Runs a Python module in a registered project as `python -m <module> [args]`
in the project sandbox (cwd and venv). Use this to verify or start the
project application without using the console.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.project_sandbox import run_module_in_project_sandbox, VenvNotFoundError

logger = logging.getLogger(__name__)


class RunProjectModuleCommand(BaseMCPCommand):
    """Run a Python module in the context of a registered project (python -m module [args]).

    Uses the same sandbox as run_project_script: cwd and PYTHONPATH set to
    project root, project's .venv/venv used. Use for verifying or starting
    the project app (e.g. python -m ai_admin --help) without console.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: False — sandbox runs on the asyncio handler with asyncio.to_thread (not
            the bounded job queue). Queued jobs apply a max runtime and kill the worker,
            which would terminate long-lived server processes (e.g. python -m app).
    """

    name = "run_project_module"
    version = "1.0.0"
    descr = (
        "Run a Python module in a registered project as python -m <module> [args] "
        "(sandbox; inline, not queued — unlike run_project_script)"
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(
        cls: type["RunProjectModuleCommand"],
    ) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        This schema is used by MCP Proxy for request validation.
        Keep it strict and deterministic.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": (
                "Run a Python module in a registered project as python -m <module> [args] "
                "inside the project sandbox. Uses project root as cwd and project's venv "
                "( .venv or venv ). Use to verify or start the project application without "
                "using the console, in line with test_data rules (all interaction via server). "
                "Runs inline (use_queue=False): not the default queued path used by "
                "run_project_script, because the job queue may enforce a max runtime and kill "
                "long-lived python -m processes."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "Project UUID (from projectid file or list_projects). "
                        "Project must be registered in the database. "
                        "Root path is resolved from the projects table."
                    ),
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                "module": {
                    "type": "string",
                    "description": (
                        "Module name to run (e.g. 'ai_admin' for python -m ai_admin). "
                        "Must be non-empty; leading/trailing whitespace is stripped."
                    ),
                    "examples": ["ai_admin", "pytest", "pip"],
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional list of arguments passed to the module as argv[1:]. "
                        "If omitted, the module receives no additional arguments."
                    ),
                    "default": None,
                    "examples": [["--help"], ["--version"], ["-v", "--tb=short"]],
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": (
                        "Optional timeout in seconds. If the module runs longer, "
                        "the process is killed and the result has timed_out=True and returncode=None."
                    ),
                    "minimum": 1,
                    "examples": [30, 60, 300],
                },
            },
            "required": ["project_id", "module"],
            "additionalProperties": False,
            "examples": [
                {
                    "project_id": "c86dded6-6f93-4fb0-be54-b6d7b739eeb9",
                    "module": "ai_admin",
                    "args": ["--help"],
                },
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "module": "pytest",
                    "args": ["-v", "tests/"],
                    "timeout_seconds": 120,
                },
            ],
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate params and reject unknown project_id before execution."""
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    @classmethod
    def metadata(cls: type["RunProjectModuleCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The run_project_module command runs a Python module in a registered project "
                "as python -m <module> [args] inside the same sandbox used by run_project_script: "
                "working directory and PYTHONPATH are set to the project root, and the project's "
                "virtual environment (.venv or venv) is used for the interpreter.\n\n"
                "Operation flow:\n"
                "1. Resolves project root from database by project_id (project must be registered)\n"
                "2. Validates module is non-empty (after stripping whitespace)\n"
                "3. Requires project venv: .venv or venv under project root (fails with VENV_NOT_FOUND if missing)\n"
                "4. Runs python -m <module> [args] in a subprocess with cwd=project root, PYTHONPATH=project root, and project venv\n"
                "5. Optionally enforces timeout_seconds (process killed if exceeded)\n"
                "6. Returns stdout, stderr, returncode, and timed_out flag\n\n"
                "Execution mode:\n"
                "- Inline (use_queue=False), not the job queue: no queue_get_job_status. "
                "run_project_script is queued by default; this command stays inline because "
                "queued jobs can enforce a max runtime and kill the worker, which would "
                "terminate long-lived python -m runs (e.g. servers).\n\n"
                "Sandbox behavior (same as run_project_script):\n"
                "- cwd: Set to the project root directory\n"
                "- PYTHONPATH: Set only to the project root\n"
                "- Interpreter: Project's .venv/bin/python or venv/bin/python\n"
                "- Imports: Only modules under the project root and the standard library are available\n\n"
                "Use cases:\n"
                "- Verify that a project application loads (e.g. python -m ai_admin --help) without using the console\n"
                "- Start or test the project's main module (e.g. python -m ai_admin) in isolation\n"
                "- Run pytest or other tools as a module in the project context (e.g. python -m pytest tests/)\n"
                "- Comply with test_data rules: all interaction with test_data projects via server commands only\n\n"
                "Important notes:\n"
                "- Project must have .venv or venv in its root; otherwise VENV_NOT_FOUND is returned\n"
                "- Project must be registered (use list_projects or create_project)\n"
                "- module is the module name only (e.g. 'ai_admin'), not a file path\n"
                "- On timeout, returncode is None and timed_out is True; stdout/stderr contain output before kill\n"
                "- Process runs in a separate subprocess; it cannot access the server process or other projects"
            ),
            "parameters": {
                "project_id": {
                    "description": (
                        "Project UUID. Must be a registered project (from projectid file or list_projects). "
                        "The project root path is resolved from the database; if the project is not found "
                        "or the root path does not exist, the command fails with VALIDATION_ERROR."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "550e8400-e29b-41d4-a716-446655440000",
                        "c86dded6-6f93-4fb0-be54-b6d7b739eeb9",
                    ],
                },
                "module": {
                    "description": (
                        "Module name to run as python -m <module>. Must be non-empty. "
                        "Leading and trailing whitespace is stripped. "
                        "Examples: 'ai_admin' (python -m ai_admin), 'pytest', 'pip'."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": ["ai_admin", "pytest", "pip", "http.server"],
                },
                "args": {
                    "description": (
                        "Optional list of command-line arguments passed to the module (argv[1:]). "
                        "If omitted or empty, the module receives no extra arguments."
                    ),
                    "type": "array",
                    "required": False,
                    "items": {"type": "string"},
                    "examples": [
                        ["--help"],
                        ["--version"],
                        ["-v", "tests/"],
                        ["--tb=short", "-x"],
                    ],
                },
                "timeout_seconds": {
                    "description": (
                        "Optional timeout in seconds. If the module runs longer than this, "
                        "the process is killed. On timeout, returncode is None and timed_out is True; "
                        "stdout and stderr contain output captured before the kill. "
                        "If omitted, no timeout is applied."
                    ),
                    "type": "integer",
                    "required": False,
                    "minimum": 1,
                    "examples": [30, 60, 120, 300],
                },
            },
            "usage_examples": [
                {
                    "description": "Verify project application loads (e.g. vast_srv)",
                    "command": {
                        "project_id": "c86dded6-6f93-4fb0-be54-b6d7b739eeb9",
                        "module": "ai_admin",
                        "args": ["--help"],
                    },
                    "explanation": (
                        "Runs python -m ai_admin --help in the project sandbox. "
                        "Use to verify imports and CLI without using the console."
                    ),
                },
                {
                    "description": "Run pytest as module with timeout",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "module": "pytest",
                        "args": ["-v", "tests/"],
                        "timeout_seconds": 120,
                    },
                    "explanation": (
                        "Runs python -m pytest -v tests/ with a 120-second timeout. "
                        "If tests hang, the process is killed and timed_out is True."
                    ),
                },
                {
                    "description": "Run module with no arguments",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "module": "mymodule",
                    },
                    "explanation": ("Runs python -m mymodule with no extra arguments."),
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "Project not found or project root path does not exist",
                    "example": "project_id not in database or root_path missing on disk",
                    "solution": (
                        "Ensure the project is registered (list_projects) and the root path exists."
                    ),
                },
                "INVALID_MODULE": {
                    "description": "module is empty or only whitespace",
                    "example": "module='' or module='   '",
                    "solution": "Provide a non-empty module name (e.g. 'ai_admin', 'pytest').",
                },
                "INVALID_PATH": {
                    "description": "Project root is not a directory",
                    "example": "Resolved project root path is not a directory",
                    "solution": "Ensure the project root exists and is a directory.",
                },
                "VENV_NOT_FOUND": {
                    "description": "Project virtual environment (.venv or venv) not found",
                    "example": "Neither .venv/bin/python nor venv/bin/python exists under project root",
                    "solution": (
                        "Create a venv in the project root: python -m venv .venv "
                        "(or venv). The command requires project venv to run the module."
                    ),
                },
                "INTERNAL_ERROR": {
                    "description": "Unexpected error during execution",
                    "example": "Exception in sandbox or subprocess handling",
                    "solution": "Check server logs for details.",
                },
            },
            "return_value": {
                "success": {
                    "description": "Module execution finished (or was killed by timeout)",
                    "data": {
                        "stdout": "Standard output of the process",
                        "stderr": "Standard error of the process",
                        "returncode": "Process exit code (None if timed out)",
                        "timed_out": "True if process was killed due to timeout",
                        "module": "Module name that was run",
                        "project_id": "Project UUID used",
                    },
                    "example": {
                        "stdout": "usage: ai_admin [--help] ...\n",
                        "stderr": "",
                        "returncode": 0,
                        "timed_out": False,
                        "module": "ai_admin",
                        "project_id": "c86dded6-6f93-4fb0-be54-b6d7b739eeb9",
                    },
                },
                "error": {
                    "description": "Command failed (validation, venv not found, or internal error)",
                    "code": (
                        "Error code: VALIDATION_ERROR, INVALID_MODULE, INVALID_PATH, "
                        "VENV_NOT_FOUND, INTERNAL_ERROR"
                    ),
                    "message": "Human-readable error message",
                    "data": "Optional details (e.g. from ValidationError)",
                },
            },
            "best_practices": [
                "Use only for registered projects; ensure project_id is from list_projects or projectid",
                "Use run_project_module (not console) to verify or run test_data project apps; complies with test_data rules",
                "Set timeout_seconds for long-running modules (e.g. pytest, server startup) to avoid hanging",
                "Check returncode and timed_out in the response to detect failures and timeouts",
                "For running a script file instead of a module, use run_project_script with file_path",
                "For default queued execution of a script file, use run_project_script and poll queue status",
            ],
        }

    async def execute(
        self: "RunProjectModuleCommand",
        project_id: str,
        module: str,
        args: Optional[List[str]] = None,
        timeout_seconds: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Run the module in the project sandbox.

        Args:
            project_id: Registered project UUID.
            module: Module name (e.g. ai_admin).
            args: Optional list of arguments (e.g. ["--help"]).
            timeout_seconds: Optional timeout in seconds.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with stdout, stderr, returncode, timed_out; or ErrorResult.
        """
        try:
            root_path = BaseMCPCommand._resolve_project_root(project_id)
            module_clean = (module or "").strip()
            if not module_clean:
                return ErrorResult(
                    code="INVALID_MODULE",
                    message="module must be a non-empty string",
                )
            try:
                result = await asyncio.to_thread(
                    run_module_in_project_sandbox,
                    root_path,
                    module_clean,
                    args,
                    timeout_seconds,
                )
            except ValueError as e:
                return ErrorResult(
                    code="INVALID_PATH",
                    message=str(e),
                )
            except VenvNotFoundError as e:
                return ErrorResult(
                    code="VENV_NOT_FOUND",
                    message=str(e),
                )
            return SuccessResult(
                data={
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                    "timed_out": result.timed_out,
                    "module": module_clean,
                    "project_id": project_id,
                },
            )
        except Exception as e:
            from ..core.exceptions import ValidationError

            if isinstance(e, ValidationError):
                return ErrorResult(
                    code="VALIDATION_ERROR",
                    message=e.message,
                    data=getattr(e, "details", {}),
                )
            logger.exception("run_project_module failed: %s", e)
            return ErrorResult(
                code="INTERNAL_ERROR",
                message=str(e),
            )
