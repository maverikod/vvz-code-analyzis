"""
CLI interface for MCP server manager.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import click
import logging
from pathlib import Path
from typing import Optional

from ..core.server_control import ServerControl

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


@click.group()
@click.option(
    "--config",
    "-c",
    default="config.json",
    help="Path to server configuration file",
    type=click.Path(path_type=Path),
)
@click.pass_context
def server(ctx: click.Context, config: Path) -> None:
    """MCP server management commands."""
    ctx.ensure_object(dict)
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
        raise click.Abort()


@server.command()
@click.pass_context
def stop(ctx: click.Context) -> None:
    """Stop MCP server."""
    control: ServerControl = ctx.obj["control"]
    result = control.stop()

    if result["success"]:
        click.echo(f"✅ {result['message']}")
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
        if "log_file" in result:
            click.echo(f"   Log: {result['log_file']}")
    else:
        click.echo(f"❌ {result['message']}", err=True)
        raise click.Abort()


if __name__ == "__main__":
    server()

