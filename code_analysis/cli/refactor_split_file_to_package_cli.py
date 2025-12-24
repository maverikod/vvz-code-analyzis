"""
Refactor CLI command: split-file-to-package.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import json
import logging
from pathlib import Path

import click

from ..core.database import CodeDatabase
from ..commands import RefactorCommand

logger = logging.getLogger(__name__)


@click.command(name="split-file-to-package")
@click.option(
    "--root-dir",
    "-r",
    required=True,
    help="Root directory of the project",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
@click.option(
    "--file",
    "-f",
    required=True,
    help="Python file to split (relative to root-dir or absolute)",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--config",
    "-c",
    required=True,
    help="JSON configuration file for file-to-package splitting",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--db-path",
    "-d",
    help="Path to SQLite database (default: root_dir/code_analysis/code_analysis.db)",
    type=click.Path(path_type=Path),
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without making changes",
)
def split_file_to_package(
    root_dir: Path, file: Path, config: Path, db_path: Path | None, dry_run: bool
) -> None:
    """
    Split a large Python file into a package with multiple modules.

    This mirrors MCP command: split_file_to_package.
    """
    try:
        with open(config, "r", encoding="utf-8") as f:
            split_config = json.load(f)

        click.echo(f"📄 File: {file.absolute()}")
        click.echo(f"⚙️  Config: {config.absolute()}")
        click.echo()

        if dry_run:
            pkg = split_config.get("package_name")
            modules = split_config.get("modules", {})
            if not pkg or not isinstance(modules, dict) or not modules:
                raise click.ClickException(
                    "Invalid config: expected keys 'package_name' and non-empty dict 'modules'"
                )
            click.echo("🔍 Dry run mode - no changes will be made")
            click.echo(f"   Package: {pkg}")
            click.echo(f"   Modules: {', '.join(sorted(modules.keys()))}")
            return

        root_dir = root_dir.resolve()
        if not db_path:
            db_path = root_dir / "code_analysis" / "code_analysis.db"

        db = CodeDatabase(db_path)
        try:
            project_id = db.get_or_create_project(str(root_dir), name=root_dir.name)
            refactor_cmd = RefactorCommand(project_id)

            result = asyncio.run(
                refactor_cmd.split_file_to_package(
                    str(root_dir), str(file), split_config
                )
            )

            if result["success"]:
                click.echo("✅ File split to package completed successfully!")
                click.echo(f"   {result['message']}")
            else:
                raise click.ClickException(result.get("message", "Split failed"))
        finally:
            db.close()
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error("Invalid config or file: %s", e)
        raise click.ClickException(str(e))
    except Exception as e:
        logger.exception("Error during split-file-to-package: %s", e)
        raise click.ClickException(str(e))
