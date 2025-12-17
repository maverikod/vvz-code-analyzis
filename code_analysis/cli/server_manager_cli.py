"""
CLI interface for MCP server manager (systemd-style).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import click
import logging
import os
from pathlib import Path
from typing import Optional

from ..core.server_control import ServerControl

# Use logger from adapter (configured by adapter)
logger = logging.getLogger(__name__)


@click.group()
@click.option(
    "--config",
    "-c",
    default=None,
    help="Path to server configuration file (default: /etc/code_analysis/config.json, ./config.json, or ~/.code_analysis/config.json)",
    type=click.Path(path_type=Path),
)
@click.pass_context
def server(ctx: click.Context, config: Optional[Path]) -> None:
    """MCP server management commands (systemd-style)."""
    ctx.ensure_object(dict)
    
    # Find config file if not specified
    if config is None:
        default_paths = [
            Path("/etc/code_analysis/config.json"),  # System-wide config
            Path.cwd() / "config.json",  # Local config
            Path.home() / ".code_analysis" / "config.json",  # User config
        ]
        for path in default_paths:
            if path.exists():
                config = path
                break
        
        if config is None:
            # Use system-wide as default if creating new config
            config = Path("/etc/code_analysis/config.json")
    
    ctx.obj["config_path"] = config
    ctx.obj["control"] = ServerControl(config)


@server.command()
@click.pass_context
def start(ctx: click.Context) -> None:
    """Start MCP server."""
    control: ServerControl = ctx.obj["control"]
    result = control.start()

    if result["success"]:
        click.echo(f"✅ {result['message']}")
        if "pid" in result:
            click.echo(f"   PID: {result['pid']}")
        if "log_file" in result:
            click.echo(f"   Log: {result['log_file']}")
    else:
        click.echo(f"❌ {result['message']}", err=True)
        if "pid" in result:
            click.echo(f"   PID: {result['pid']}")
        raise click.Abort()


@server.command()
@click.pass_context
def stop(ctx: click.Context) -> None:
    """Stop MCP server."""
    control: ServerControl = ctx.obj["control"]
    result = control.stop()

    if result["success"]:
        click.echo(f"✅ {result['message']}")
        if "pid" in result:
            click.echo(f"   PID: {result['pid']}")
    else:
        click.echo(f"❌ {result['message']}", err=True)
        if "pid" in result:
            click.echo(f"   PID: {result['pid']}")


@server.command()
@click.pass_context
def restart(ctx: click.Context) -> None:
    """Restart MCP server."""
    control: ServerControl = ctx.obj["control"]
    result = control.restart()

    if result["success"]:
        click.echo(f"✅ {result['message']}")
        if "pid" in result:
            click.echo(f"   PID: {result['pid']}")
        if "log_file" in result:
            click.echo(f"   Log: {result['log_file']}")
    else:
        click.echo(f"❌ {result['message']}", err=True)
        raise click.Abort()


@server.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Get server status."""
    control: ServerControl = ctx.obj["control"]
    result = control.status()

    if result["running"]:
        click.echo(f"✅ {result['message']}")
        if "pid" in result:
            click.echo(f"   PID: {result['pid']}")
        if "log_file" in result:
            click.echo(f"   Log: {result['log_file']}")
        if "config_file" in result:
            click.echo(f"   Config: {result['config_file']}")
    else:
        click.echo(f"❌ {result['message']}")
        if "pid" in result:
            click.echo(f"   Stale PID: {result['pid']}")


@server.command()
@click.pass_context
def reload(ctx: click.Context) -> None:
    """Reload server configuration (restarts server)."""
    control: ServerControl = ctx.obj["control"]
    result = control.reload()

    if result["success"]:
        click.echo(f"✅ {result['message']}")
        if "pid" in result:
            click.echo(f"   PID: {result['pid']}")
    else:
        click.echo(f"❌ {result['message']}", err=True)
        raise click.Abort()


@server.command()
@click.pass_context
def validate(ctx: click.Context) -> None:
    """Validate server configuration file (adapter config)."""
    config_path: Path = ctx.obj["config_path"]
    
    try:
        from mcp_proxy_adapter.core.config.simple_config import SimpleConfig
        simple_config = SimpleConfig(str(config_path))
        model = simple_config.load()
        
        click.echo(f"✅ Configuration is valid: {config_path}")
        click.echo(f"   Host: {model.server.host}")
        click.echo(f"   Port: {model.server.port}")
        if hasattr(model.server, "log_dir") and model.server.log_dir:
            click.echo(f"   Log dir: {model.server.log_dir}")
        click.echo("\n   Note: Use 'python -m code_analysis.cli.config_cli generate' to generate adapter config")
    except Exception as e:
        click.echo(f"❌ Configuration validation failed: {str(e)}", err=True)
        raise click.Abort()




if __name__ == "__main__":
    server()
