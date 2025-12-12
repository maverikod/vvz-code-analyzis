"""
CLI interface for MCP server manager.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import click
import json
import logging
from pathlib import Path
from typing import Optional

from ..server_manager import ServerManager

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


@click.group()
@click.option(
    "--config",
    "-c",
    default="server_config.json",
    help="Path to server configuration file",
    type=click.Path(path_type=Path),
)
@click.pass_context
def server(ctx: click.Context, config: Path) -> None:
    """MCP server management commands."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config
    ctx.obj["manager"] = ServerManager(config)


@server.command()
@click.pass_context
def start(ctx: click.Context) -> None:
    """Start MCP server."""
    manager: ServerManager = ctx.obj["manager"]
    result = manager.start()

    if result["success"]:
        click.echo(f"✅ {result['message']}")
        if "pid" in result:
            click.echo(f"   PID: {result['pid']}")
        if "host" in result and "port" in result:
            click.echo(f"   URL: http://{result['host']}:{result['port']}/mcp")
    else:
        click.echo(f"❌ {result['message']}", err=True)
        raise click.Abort()


@server.command()
@click.pass_context
def stop(ctx: click.Context) -> None:
    """Stop MCP server."""
    manager: ServerManager = ctx.obj["manager"]
    result = manager.stop()

    if result["success"]:
        click.echo(f"✅ {result['message']}")
    else:
        click.echo(f"❌ {result['message']}", err=True)
        if "pid" in result:
            click.echo(f"   PID: {result['pid']}")


@server.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Get server status."""
    manager: ServerManager = ctx.obj["manager"]
    result = manager.status()

    if result["running"]:
        click.echo(f"✅ {result['message']}")
        if "pid" in result:
            click.echo(f"   PID: {result['pid']}")
        if "host" in result and "port" in result:
            click.echo(f"   URL: http://{result['host']}:{result['port']}/mcp")
        if "projects" in result:
            click.echo(f"   Projects: {result['projects']}")
    else:
        click.echo(f"❌ {result['message']}")


@server.command()
@click.option(
    "--host",
    default="0.0.0.0",
    help="Server host (default: 0.0.0.0)",
)
@click.option(
    "--port",
    type=int,
    default=15000,
    help="Server port (default: 15000)",
)
@click.option(
    "--log",
    "-l",
    help="Path to log file (optional)",
)
@click.option(
    "--db-path",
    "-d",
    help="Path to SQLite database (optional)",
)
@click.option(
    "--dir",
    "dirs",
    multiple=True,
    help="Project directory (format: name:path). Can be used multiple times.",
)
@click.option(
    "--json-dirs",
    help='JSON array of directories: [{"name": "...", "path": "..."}]',
)
@click.pass_context
def generate_config(
    ctx: click.Context,
    host: str,
    port: int,
    log: Optional[str],
    db_path: Optional[str],
    dirs: tuple[str, ...],
    json_dirs: Optional[str],
) -> None:
    """Generate server configuration file."""
    manager: ServerManager = ctx.obj["manager"]

    # Parse directories
    dirs_list = []
    if json_dirs:
        try:
            dirs_list = json.loads(json_dirs)
        except json.JSONDecodeError:
            click.echo("❌ Invalid JSON format for --json-dirs", err=True)
            raise click.Abort()
    else:
        for dir_str in dirs:
            if ":" not in dir_str:
                click.echo(
                    f"❌ Invalid directory format: {dir_str}. " "Expected: name:path",
                    err=True,
                )
                raise click.Abort()
            name, path = dir_str.split(":", 1)
            dirs_list.append({"name": name.strip(), "path": path.strip()})

    result = manager.generate_config(host=host, port=port, log=log, dirs=dirs_list)

    if result["success"]:
        click.echo(f"✅ {result['message']}")
        click.echo(f"   Host: {result['config']['host']}")
        click.echo(f"   Port: {result['config']['port']}")
        if result["config"].get("log"):
            click.echo(f"   Log: {result['config']['log']}")
        click.echo(f"   Projects: {len(result['config']['dirs'])}")
    else:
        click.echo(f"❌ {result['message']}", err=True)
        raise click.Abort()


@server.command()
@click.pass_context
def validate(ctx: click.Context) -> None:
    """Validate server configuration file."""
    manager: ServerManager = ctx.obj["manager"]
    result = manager.validate_config()

    if result["valid"]:
        click.echo(f"✅ {result['message']}")
        if "config" in result:
            cfg = result["config"]
            click.echo(f"   Host: {cfg['host']}")
            click.echo(f"   Port: {cfg['port']}")
            if cfg.get("log"):
                click.echo(f"   Log: {cfg['log']}")
            if cfg.get("db_path"):
                click.echo(f"   Database: {cfg['db_path']}")
            click.echo(f"   Projects: {cfg['projects']}")
            if cfg.get("dirs"):
                click.echo("   Directories:")
                for d in cfg["dirs"]:
                    click.echo(f"     - {d['name']}: {d['path']}")
    else:
        click.echo(f"❌ {result['message']}", err=True)
        raise click.Abort()


@server.command()
@click.option(
    "--db-path",
    "-d",
    help="Path to database file (optional, uses config if not provided)",
)
@click.option(
    "--project",
    "-p",
    "project_paths",
    multiple=True,
    help="Project path to initialize in database (can be used multiple times)",
)
@click.pass_context
def create_db(
    ctx: click.Context, db_path: Optional[str], project_paths: tuple[str, ...]
) -> None:
    """Create new database and initialize projects."""
    manager: ServerManager = ctx.obj["manager"]

    projects_list = list(project_paths) if project_paths else None
    result = manager.create_database(db_path=db_path, project_paths=projects_list)

    if result["success"]:
        click.echo(f"✅ {result['message']}")
        if "projects_initialized" in result:
            click.echo(f"   Projects initialized: {result['projects_initialized']}")
            if result.get("projects"):
                click.echo("   Projects:")
                for p in result["projects"]:
                    click.echo(f"     - {p['name']}: {p['id']}")
    else:
        click.echo(f"❌ {result['message']}", err=True)
        raise click.Abort()


if __name__ == "__main__":
    server()
