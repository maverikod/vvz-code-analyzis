"""
Install MCP command gate when configuration is invalid.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations


def install_config_command_gate() -> None:
    """Block MCP commands except help/health while config is invalid."""
    from mcp_proxy_adapter.commands.base import Command
    from mcp_proxy_adapter.commands.result import ErrorResult

    if getattr(Command.execute, "_config_gate_installed", False):
        return

    original_execute = Command.execute

    async def gated_execute(self, **kwargs):  # type: ignore[no-untyped-def]
        from code_analysis.core.config_state import (
            config_blocks_command,
            config_invalid_command_message,
        )

        command_name = getattr(self, "name", None)
        if config_blocks_command(command_name):
            return ErrorResult(
                message=config_invalid_command_message(),
                code="CONFIG_INVALID",
            )
        return await original_execute(self, **kwargs)

    gated_execute._config_gate_installed = True  # type: ignore[attr-defined]
    Command.execute = gated_execute  # type: ignore[method-assign, assignment]
