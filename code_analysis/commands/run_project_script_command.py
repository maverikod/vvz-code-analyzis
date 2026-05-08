"""
Run project script MCP command.

Runs a Python script from a registered project in a sandbox: only code under
the project root can be executed (cwd and PYTHONPATH restricted to project).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.project_sandbox import run_in_project_sandbox, VenvNotFoundError

logger = logging.getLogger(__name__)


class RunProjectScriptCommand(BaseMCPCommand):
    """Run a Python script in the context of a registered project only.

    The script must be inside the project root. Execution is sandboxed:
    cwd and PYTHONPATH are set to the project root so only project code
    (and the standard library) can be used.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: True — runs via the job queue by default so the HTTP handler stays
            responsive; subprocess work uses asyncio.to_thread. Success payload includes
            stdout and stderr for the model.
    """

    name = "run_project_script"
    version = "1.1.0"
    descr = (
        "Run a Python script from a registered project in a sandbox (only project code)"
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @classmethod
    def get_schema(
        cls: type["RunProjectScriptCommand"],
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
                "Run a Python script from a registered project in a sandbox. "
                "Only code under the project root can be executed: cwd and PYTHONPATH "
                "are set to the project root so imports are limited to the project and the standard library. "
                "The script path must be relative to the project root and must not escape it (e.g. no '..')."
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
                "file_path": {
                    "type": "string",
                    "description": (
                        "Path to the Python script relative to project root. "
                        "Must not be empty. Leading slashes and backslashes are normalized. "
                        "Resolved path must lie strictly inside the project root (path traversal is rejected)."
                    ),
                    "examples": ["main.py", "scripts/run.py", "tests/test_foo.py"],
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional list of arguments passed to the script as argv[1:]. "
                        "If omitted, the script receives no additional arguments."
                    ),
                    "default": None,
                    "examples": [["--verbose"], ["--config", "dev.json"]],
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": (
                        "Optional timeout in seconds. If the script runs longer, "
                        "the subprocess is interrupted (POSIX: process group SIGKILL) and "
                        "the result has timed_out=True and returncode=None. stdout/stderr "
                        "contain output captured before termination."
                    ),
                    "minimum": 1,
                    "examples": [30, 60, 300],
                },
                "post_run_delay_seconds": {
                    "type": "integer",
                    "description": (
                        "Optional seconds to wait after the subprocess exits (after stdout/stderr "
                        "are captured). Use to allow services or filesystem state to settle without "
                        "a separate sleep script. Must be non-negative. Omitted means no extra delay."
                    ),
                    "minimum": 0,
                    "examples": [0, 2, 5],
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
            "examples": [
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "file_path": "main.py",
                },
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "file_path": "scripts/run.py",
                    "args": ["--verbose"],
                    "timeout_seconds": 30,
                    "post_run_delay_seconds": 2,
                },
            ],
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate params (no DB access: job queue runs sync without event loop)."""
        params = super().validate_params(params)
        pid = params.get("project_id")
        if isinstance(pid, str):
            params["project_id"] = pid.strip()
        return params

    @classmethod
    def metadata(cls: type["RunProjectScriptCommand"]) -> Dict[str, Any]:
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
                "The run_project_script command runs a Python script from a registered project "
                "inside a sandbox. Only code that belongs to that project (and the standard library) "
                "can be executed: the working directory and PYTHONPATH are set to the project root, "
                "so imports are restricted to the project tree.\n\n"
                "Operation flow:\n"
                "1. Resolves project root from database by project_id (project must be registered)\n"
                "2. Normalizes file_path (relative to project root, no leading slash)\n"
                "3. Validates that the resolved script path lies strictly inside the project root\n"
                "4. Requires project venv: .venv or venv under project root (fails with VENV_NOT_FOUND if missing)\n"
                "5. Runs the script in a subprocess with cwd=project root, PYTHONPATH=project root, and project venv\n"
                "6. Optionally enforces timeout_seconds (subprocess interrupted if exceeded)\n"
                "7. Optionally waits post_run_delay_seconds after the subprocess exits (captured I/O unchanged)\n"
                "8. Returns stdout, stderr, returncode, timed_out, and post_run_delay_seconds_applied\n\n"
                "Sandbox behavior:\n"
                "- cwd: Set to the project root directory\n"
                "- PYTHONPATH: Set only to the project root (no parent paths or system paths)\n"
                "- Imports: Only modules under the project root and the standard library are available\n"
                "- Path: Script path must be inside the project root; path traversal (e.g. '..') is rejected\n\n"
                "Use cases:\n"
                "- Run tests or scripts for a specific registered project\n"
                "- Execute project entry points (e.g. main.py, scripts/run.py) in isolation\n"
                "- Validate that code runs without depending on external packages outside the project\n"
                "- Run one-off scripts with a timeout for safety\n\n"
                "Important notes:\n"
                "- Project must have .venv or venv in its root; otherwise VENV_NOT_FOUND is returned\n"
                "- Project must be registered (use list_projects or create_project)\n"
                "- file_path is always relative to the project root; absolute paths are not accepted for the script\n"
                "- On timeout, returncode is None and timed_out is True; stdout/stderr contain output before kill\n"
                "- By default the command runs via the job queue (use_queue=True); poll queue_get_job_status for completion\n"
                "- Script runs in a separate process; it cannot access the server process or other projects"
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
                        "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                    ],
                },
                "file_path": {
                    "description": (
                        "Path to the Python script relative to the project root. "
                        "Must be non-empty. Leading slashes and backslashes are stripped/normalized. "
                        "The resolved path must be inside the project root (path traversal is rejected). "
                        "File must exist and be a regular file."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "main.py",
                        "scripts/run.py",
                        "tests/test_foo.py",
                        "src/cli.py",
                    ],
                },
                "args": {
                    "description": (
                        "Optional list of command-line arguments passed to the script (argv[1:]). "
                        "If omitted or empty, the script receives no extra arguments."
                    ),
                    "type": "array",
                    "required": False,
                    "items": {"type": "string"},
                    "examples": [
                        ["--verbose"],
                        ["--config", "dev.json", "--dry-run"],
                    ],
                },
                "timeout_seconds": {
                    "description": (
                        "Optional timeout in seconds. If the script runs longer than this, "
                        "the subprocess is interrupted. On timeout, returncode is None and timed_out is True; "
                        "stdout and stderr contain output captured before termination. "
                        "If omitted, no timeout is applied."
                    ),
                    "type": "integer",
                    "required": False,
                    "minimum": 1,
                    "examples": [30, 60, 300],
                },
                "post_run_delay_seconds": {
                    "description": (
                        "Optional non-negative delay in seconds after the subprocess exits, "
                        "before returning the result. Does not change captured stdout/stderr. "
                        "Useful when a short settle period is needed after the script finishes."
                    ),
                    "type": "integer",
                    "required": False,
                    "minimum": 0,
                    "examples": [0, 2, 5],
                },
            },
            "usage_examples": [
                {
                    "description": "Run main entry point",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "main.py",
                    },
                    "explanation": (
                        "Runs main.py from the project root. No arguments and no timeout."
                    ),
                },
                {
                    "description": "Run script with arguments and timeout",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "scripts/run.py",
                        "args": ["--verbose"],
                        "timeout_seconds": 30,
                    },
                    "explanation": (
                        "Runs scripts/run.py with one argument and a 30-second timeout. "
                        "If the script exceeds 30 seconds, it is killed and timed_out is True."
                    ),
                },
                {
                    "description": "Run test module",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "tests/test_foo.py",
                    },
                    "explanation": (
                        "Runs a test file. Imports are limited to the project and stdlib."
                    ),
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
                "INVALID_FILE_PATH": {
                    "description": "file_path is empty after normalization",
                    "example": "file_path='' or file_path='/''",
                    "solution": "Provide a non-empty path relative to the project root.",
                },
                "INVALID_PATH": {
                    "description": "Resolved script path is outside the project root",
                    "example": "file_path='../../../etc/passwd' or path escapes root",
                    "solution": (
                        "Use a path relative to the project root that does not leave it."
                    ),
                },
                "FILE_NOT_FOUND": {
                    "description": "Script file does not exist or is not a file",
                    "example": "file_path='missing.py' or path points to a directory",
                    "solution": "Verify the file exists under the project root and is a regular file.",
                },
                "VENV_NOT_FOUND": {
                    "description": "Project virtual environment (.venv or venv) not found",
                    "example": "Neither .venv/bin/python nor venv/bin/python exists under project root",
                    "solution": (
                        "Create a venv in the project root: python -m venv .venv "
                        "(or venv). The command requires project venv to run scripts."
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
                    "description": "Script execution finished (or was killed by timeout)",
                    "data": {
                        "stdout": "Standard output of the script",
                        "stderr": "Standard error of the script",
                        "returncode": "Process exit code (None if timed out)",
                        "timed_out": "True if process was killed due to timeout",
                        "post_run_delay_seconds_applied": (
                            "Seconds waited after subprocess exit (from post_run_delay_seconds)"
                        ),
                        "script": "Normalized script path relative to project root",
                        "project_id": "Project UUID used",
                    },
                    "example": {
                        "stdout": "Hello from script\n",
                        "stderr": "",
                        "returncode": 0,
                        "timed_out": False,
                        "post_run_delay_seconds_applied": 0,
                        "script": "main.py",
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    },
                },
                "error": {
                    "description": "Command failed (validation, file not found, or internal error)",
                    "code": (
                        "Error code: VALIDATION_ERROR, INVALID_FILE_PATH, INVALID_PATH, "
                        "FILE_NOT_FOUND, VENV_NOT_FOUND, INTERNAL_ERROR"
                    ),
                    "message": "Human-readable error message",
                    "data": "Optional details (e.g. from ValidationError)",
                },
            },
            "best_practices": [
                "Use only for registered projects; ensure project_id is from list_projects or projectid",
                "Use relative file_path (e.g. main.py, scripts/run.py) without leading slash",
                "Set timeout_seconds for long-running or untrusted scripts to avoid hanging",
                "Check returncode and timed_out in the response to detect failures and timeouts",
                "Script cannot access other projects or server state; use for isolated execution only",
            ],
        }

    async def execute(
        self: "RunProjectScriptCommand",
        project_id: str,
        file_path: str,
        args: Optional[List[str]] = None,
        timeout_seconds: Optional[int] = None,
        post_run_delay_seconds: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Run the script in the project sandbox.

        Args:
            self: Command instance.
            project_id: Registered project UUID.
            file_path: Script path relative to project root.
            args: Optional list of script arguments.
            timeout_seconds: Optional timeout in seconds.
            post_run_delay_seconds: Optional seconds to sleep after subprocess exits.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with stdout, stderr, returncode, timed_out,
            post_run_delay_seconds_applied; or ErrorResult.
        """
        try:
            root_path = BaseMCPCommand._resolve_project_root(project_id)
            # Normalize: treat as relative to project root, no leading slash
            rel = file_path.lstrip("/").replace("\\", "/")
            if not rel:
                return ErrorResult(
                    code="INVALID_FILE_PATH",
                    message="file_path must be a non-empty path relative to project root",
                )
            if post_run_delay_seconds is not None and post_run_delay_seconds < 0:
                return ErrorResult(
                    code="VALIDATION_ERROR",
                    message="post_run_delay_seconds must be non-negative",
                )
            try:
                result = await asyncio.to_thread(
                    run_in_project_sandbox,
                    root_path,
                    rel,
                    args,
                    timeout_seconds,
                    (
                        float(post_run_delay_seconds)
                        if post_run_delay_seconds is not None
                        else None
                    ),
                )
            except ValueError as e:
                return ErrorResult(
                    code="INVALID_PATH",
                    message=str(e),
                )
            except FileNotFoundError as e:
                return ErrorResult(
                    code="FILE_NOT_FOUND",
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
                    "post_run_delay_seconds_applied": result.post_run_delay_seconds_applied,
                    "script": rel,
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
            logger.exception("run_project_script failed: %s", e)
            return ErrorResult(
                code="INTERNAL_ERROR",
                message=str(e),
            )
