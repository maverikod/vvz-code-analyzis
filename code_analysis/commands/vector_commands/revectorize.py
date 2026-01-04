"""
MCP command: revectorize.

This command is kept for backward compatibility with older hook registrations.
At the moment, vectorization is handled by the vectorization worker
(`start_worker` / worker configuration).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult

from ..base_mcp_command import BaseMCPCommand


class RevectorizeCommand(BaseMCPCommand):
    """
    Compatibility command for triggering vectorization.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Description.
        category: Category.
        author: Author name.
        email: Author email.
        use_queue: Whether the command is executed via queue.
    """

    name = "revectorize"
    version = "1.0.0"
    descr = (
        "Compatibility command: use vectorization worker to vectorize missing chunks"
    )
    category = "vector"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["RevectorizeCommand"]) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema describing command parameters.
        """

        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "description": "Compatibility vectorization trigger. Use start_worker (vectorization) instead.",
            "properties": {**base_props},
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self: "RevectorizeCommand",
        root_dir: str,
        project_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult:
        """
        Execute compatibility response.

        Args:
            self: Command instance.
            root_dir: Project root directory.
            project_id: Optional project id (ignored).
            **kwargs: Extra args (ignored).

        Returns:
            SuccessResult with guidance.
        """

        _ = project_id
        _ = kwargs
        return SuccessResult(
            data={
                "root_dir": root_dir,
                "message": "Use start_worker with worker_type='vectorization' to process non-vectorized chunks.",
                "hint": {
                    "command": "start_worker",
                    "params": {"worker_type": "vectorization", "root_dir": root_dir},
                },
            }
        )
