"""
Run project script MCP command.

Runs a Python script from a registered project in a sandbox: only code under
the project root can be executed (cwd and PYTHONPATH restricted to project).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.project_sandbox import run_in_project_sandbox

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
        use_queue: Whether to run in the background queue.
    """

    name = "run_project_script"
    version = "1.0.0"
    descr = (
        "Run a Python script from a registered project in a sandbox (only project code)"
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["RunProjectScriptCommand"]) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "description": "Run a Python script from a registered project. Script runs in a sandbox with cwd and PYTHONPATH set to the project root.",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from projectid or list_projects). Project must be registered.",
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to the Python script relative to project root.",
                    "examples": ["main.py", "scripts/run.py", "tests/test_foo.py"],
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional arguments passed to the script (argv[1:]).",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Optional timeout in seconds. Process is killed if exceeded.",
                    "minimum": 1,
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
                },
            ],
        }

    async def execute(
        self: "RunProjectScriptCommand",
        project_id: str,
        file_path: str,
        args: Optional[List[str]] = None,
        timeout_seconds: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Run the script in the project sandbox.

        Args:
            self: Command instance.
            project_id: Registered project UUID.
            file_path: Script path relative to project root.
            args: Optional list of script arguments.
            timeout_seconds: Optional timeout in seconds.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with stdout, stderr, returncode, timed_out; or ErrorResult.
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
            try:
                result = run_in_project_sandbox(
                    root_path=root_path,
                    script_relative_path=rel,
                    args=args,
                    timeout_seconds=timeout_seconds,
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
            return SuccessResult(
                data={
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                    "timed_out": result.timed_out,
                    "script": rel,
                    "project_id": project_id,
                },
                description="Script execution finished",
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
