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
                details=getattr(e, "details", {}),
            )
        logger.exception("run_project_script failed: %s", e)
        return ErrorResult(
            code="INTERNAL_ERROR",
            message=str(e),
        )
