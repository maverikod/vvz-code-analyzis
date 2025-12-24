"""
CLI interface for system operations (help, health).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# mypy: ignore-errors

import click
import json
import logging
from typing import Optional

from ..commands.help_command import HelpCommand

logger = logging.getLogger(__name__)


@click.group()
def system() -> None:
    """System operations - help, health."""
    pass


@system.command()
@click.option(
    "--command",
    "-c",
    type=str,
    help="Optional command name to get detailed help for",
)
@click.option(
    "--format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format",
)
def help(command: Optional[str], format: str) -> None:
    """
    Get help information about the server and its commands.

    Example:
        code_analysis system help
        code_analysis system help --command analyze_project
    """
    try:
        # Ensure code_analysis MCP commands are visible in registry for CLI help output.
        # (In the server they are registered via hooks; CLI runs outside that lifecycle.)
        try:
            # Suppress mcp_proxy_adapter logging during registration to avoid BrokenPipeError
            # when users pipe output (e.g., `| head`).
            mcp_logger = logging.getLogger("mcp_proxy_adapter")
            prev_disabled = mcp_logger.disabled
            mcp_logger.disabled = True
            from mcp_proxy_adapter.commands.command_registry import (
                registry as _registry,
            )
            from ..hooks import register_code_analysis_commands

            try:
                register_code_analysis_commands(_registry)
            finally:
                mcp_logger.disabled = prev_disabled
        except Exception:
            # Best-effort only; help still works for builtin commands.
            pass

        cmd = HelpCommand()
        import asyncio

        result = asyncio.run(cmd.execute(command=command))

        payload = result.to_dict()
        if payload.get("success"):
            data = payload.get("data", {})
            if format == "json":
                click.echo(json.dumps(data, indent=2))
                return

            help_text = data.get("help", "")
            click.echo(help_text)
            if not command:
                commands = data.get("commands", [])
                if commands:
                    click.echo(f"\nAvailable commands ({len(commands)}):")
                    for cmd_name in sorted(commands):
                        click.echo(f"  - {cmd_name}")
            return

        err = payload.get("error", {})
        click.echo(f"❌ Error: {err.get('message', 'Unknown error')}", err=True)
        details = err.get("data", {})
        if isinstance(details, dict) and "available_commands" in details:
            click.echo("\nAvailable commands:")
            for cmd_name in sorted(details["available_commands"]):
                click.echo(f"  - {cmd_name}")
        raise click.Abort()
    except Exception as e:
        logger.exception(f"Error executing help command: {e}")
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()


@system.command()
@click.option(
    "--server-url",
    type=str,
    help="Server URL (default: from config or http://localhost:15000)",
)
@click.option(
    "--format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format",
)
def health(server_url: Optional[str], format: str) -> None:
    """
    Check server health status.

    Example:
        code_analysis system health
        code_analysis system health --server-url https://localhost:15000
    """
    try:
        # Try to get server URL from config
        if not server_url:
            from mcp_proxy_adapter.config import get_config as get_adapter_config

            adapter_config = get_adapter_config()
            if adapter_config and hasattr(adapter_config, "config_data"):
                config_data = adapter_config.config_data
                server_config = config_data.get("server", {})
                host = server_config.get("host", "localhost")
                port = server_config.get("port", 15000)
                protocol = (
                    "https"
                    if config_data.get("transport", {}).get("protocol") == "mtls"
                    else "http"
                )
                server_url = f"{protocol}://{host}:{port}"
            else:
                server_url = "http://localhost:15000"

        # Call health endpoint
        import httpx
        import ssl

        # Create SSL context if using HTTPS
        ssl_context = None
        if server_url.startswith("https"):
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        with httpx.Client(verify=ssl_context, timeout=10.0) as client:
            response = client.get(f"{server_url}/health")

            if response.status_code == 200:
                health_data = response.json()

                if format == "json":
                    click.echo(json.dumps(health_data, indent=2))
                else:
                    click.echo("✅ Server is healthy")
                    if "components" in health_data:
                        components = health_data["components"]
                        if "commands" in components:
                            cmd_info = components["commands"]
                            click.echo(
                                f"   Commands registered: {cmd_info.get('registered_count', 'N/A')}"
                            )
                        if "queue_manager" in components:
                            queue_info = components["queue_manager"]
                            click.echo(
                                f"   Queue manager: {queue_info.get('status', 'N/A')}"
                            )
            else:
                click.echo(
                    f"❌ Health check failed: HTTP {response.status_code}", err=True
                )
                raise click.Abort()

    except httpx.RequestError as e:
        click.echo(f"❌ Connection error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        logger.exception(f"Error checking health: {e}")
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()
