"""
Help command for mcp-proxy-adapter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# mypy: ignore-errors

import logging
from typing import Dict, Any, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult
from mcp_proxy_adapter.commands.command_registry import registry

logger = logging.getLogger(__name__)


class HelpCommand(Command):
    """Command for getting help information about the server and its commands."""

    name = "help"
    version = "1.0.0"
    descr = "Get help information about the server and its commands"
    category = "system"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False  # Help command is fast, no need for queue

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        schema = {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Optional command name to get detailed help for. If None, returns general server information.",
                },
            },
            "required": [],
            "additionalProperties": False,
        }
        return schema

    async def execute(
        self,
        command: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        """
        Execute help command.

        Args:
            command: Optional command name to get detailed help for.
                    If None, returns general server information.

        Returns:
            SuccessResult with help information
        """
        try:
            if command:
                # Get help for specific command
                cmd_class = registry.get_command(command)
                if not cmd_class:
                    # Get available commands
                    available_commands = self._get_command_names()

                    return ErrorResult(
                        message=f"Unknown command: {command}",
                        code="UNKNOWN_COMMAND",
                        details={
                            "available_commands": available_commands,
                        },
                    )

                # Build help text for specific command
                help_text = self._build_command_help(cmd_class)
                return SuccessResult(
                    data={
                        "command": command,
                        "help": help_text,
                    }
                )
            else:
                # Get general server help
                help_text = self._build_general_help()
                return SuccessResult(
                    data={
                        "help": help_text,
                        "commands": self._get_command_names(),
                    }
                )

        except Exception as e:
            logger.exception(f"Error during help command execution: {e}")
            return ErrorResult(
                message=f"Help command failed: {str(e)}",
                code="HELP_ERROR",
                details={"error": str(e)},
            )

    def _build_command_help(self, cmd_class: type) -> str:
        """Build help text for a specific command."""
        lines = []

        # Command name and description
        lines.append(
            f"{cmd_class.name.upper()} - {cmd_class.descr or 'No description'}"
        )
        lines.append("")

        # Metadata
        if hasattr(cmd_class, "version"):
            lines.append(f"Version: {cmd_class.version}")
        if hasattr(cmd_class, "category"):
            lines.append(f"Category: {cmd_class.category}")
        if hasattr(cmd_class, "author"):
            lines.append(f"Author: {cmd_class.author}")
        lines.append("")

        # Schema information
        if hasattr(cmd_class, "get_schema"):
            schema = cmd_class.get_schema()
            properties = schema.get("properties", {})
            required = schema.get("required", [])

            if properties:
                lines.append("PARAMETERS:")
                for param_name, param_info in properties.items():
                    param_type = param_info.get("type", "unknown")
                    param_desc = param_info.get("description", "No description")
                    default = param_info.get("default")
                    is_required = param_name in required

                    req_marker = "(required)" if is_required else "(optional)"
                    default_marker = (
                        f" (default: {default})" if default is not None else ""
                    )
                    lines.append(
                        f"  {param_name} ({param_type}) {req_marker}{default_marker}"
                    )
                    lines.append(f"    {param_desc}")
                lines.append("")

        # Queue usage
        if hasattr(cmd_class, "use_queue") and cmd_class.use_queue:
            lines.append(
                "NOTE: This command uses the queue system for asynchronous execution."
            )
            lines.append(
                "      It will return a job_id immediately, and you can check status using queue_get_job_status."
            )
            lines.append("")

        # Docstring
        if cmd_class.__doc__:
            lines.append("DESCRIPTION:")
            lines.append(cmd_class.__doc__.strip())
            lines.append("")

        return "\n".join(lines)

    def _get_command_names(self) -> list:
        """Get list of registered command names."""
        try:
            commands = registry.get_all_commands()
            if isinstance(commands, dict):
                return [cmd.name for cmd in commands.values()]
            return [cmd.name for cmd in commands]
        except Exception:
            return []

    def _build_general_help(self) -> str:
        """Build general server help text."""
        lines = []

        lines.append("CODE ANALYSIS SERVER")
        lines.append("")
        lines.append("OVERVIEW:")
        lines.append(
            "    The Code Analysis Server provides comprehensive code analysis capabilities"
        )
        lines.append(
            "    for Python projects. It offers static code analysis, code search, usage tracking,"
        )
        lines.append("    issue detection, and automated refactoring tools.")
        lines.append("")
        lines.append("CAPABILITIES:")
        lines.append("    1. Project Analysis")
        lines.append("       - Scan Python projects and extract code structure")
        lines.append("       - Identify classes, methods, functions, and dependencies")
        lines.append("       - Detect code quality issues")
        lines.append("")
        lines.append("    2. Code Search")
        lines.append("       - Search by class/method names with pattern matching")
        lines.append("       - Full-text search in code content and docstrings")
        lines.append("       - Find usages of specific methods/functions")
        lines.append("       - Semantic search using vector embeddings")
        lines.append("")
        lines.append("    3. Code Quality")
        lines.append("       - Detect missing docstrings")
        lines.append("       - Identify large files")
        lines.append("       - Find methods with incomplete implementations")
        lines.append("")
        lines.append("    4. Refactoring")
        lines.append("       - Split large classes into smaller ones")
        lines.append("       - Extract common functionality into base classes")
        lines.append("       - Merge related classes")
        lines.append("")
        lines.append("AVAILABLE COMMANDS:")

        # List all registered commands
        try:
            commands = registry.get_all_commands()
            if isinstance(commands, dict):
                commands = list(commands.values())
            if commands:
                for cmd in commands:
                    descr = getattr(cmd, "descr", "No description")
                    use_queue = getattr(cmd, "use_queue", False)
                    queue_marker = " [queue]" if use_queue else ""
                    lines.append(f"  - {cmd.name}: {descr}{queue_marker}")
            else:
                lines.append("  (No commands registered)")
        except Exception as e:
            logger.warning(f"Failed to list commands: {e}")
            lines.append("  (Unable to list commands)")

        lines.append("")
        lines.append("USAGE:")
        lines.append(
            '    Use help(command="command_name") to get detailed help for a specific command.'
        )
        lines.append("")
        lines.append("    Example:")
        lines.append("      help()  # Get general help")
        lines.append(
            '      help(command="analyze_project")  # Get help for analyze_project command'
        )
        lines.append("")
        lines.append(
            'For detailed help on a specific command, use: help(command="command_name")'
        )

        return "\n".join(lines)
