"""
Refactor CLI command: split-class.

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


@click.command(name="split-class")
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
    help="Python file to refactor (relative to root-dir or absolute)",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--config",
    "-c",
    required=True,
    help="JSON configuration file for class splitting",
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
def split_class(
    root_dir: Path, file: Path, config: Path, db_path: Path | None, dry_run: bool
) -> None:
    """Split a class into multiple smaller classes."""
    try:
        with open(config, "r", encoding="utf-8") as f:
            split_config = json.load(f)

        click.echo(f"📄 File: {file.absolute()}")
        click.echo(f"⚙️  Config: {config.absolute()}")
        click.echo()

        root_dir = root_dir.resolve()
        if not db_path:
            db_path = root_dir / "code_analysis" / "code_analysis.db"

        db = CodeDatabase(db_path)
        try:
            project_id = db.get_or_create_project(str(root_dir), name=root_dir.name)
            refactor_cmd = RefactorCommand(project_id)

            if dry_run:
                click.echo("🔍 Dry run mode - no changes will be made")
                click.echo()
                from ..core.refactorer import ClassSplitter

                splitter = ClassSplitter(file)
                splitter.load_file()
                src_class_name = split_config.get("src_class")
                if not src_class_name:
                    raise click.ClickException(
                        "Source class name not specified (expected key 'src_class')"
                    )
                src_class = splitter.find_class(src_class_name)
                if not src_class:
                    raise click.ClickException(f"Class not found: {src_class_name}")

                is_valid, errors = splitter.validate_split_config(
                    src_class, split_config
                )
                if not is_valid:
                    raise click.ClickException(
                        "Configuration validation failed:\n"
                        + "\n".join(f"- {e}" for e in errors)
                    )

                click.echo("✅ Configuration is valid")
                click.echo("✅ All properties and methods are accounted for")
                return

            result = asyncio.run(
                refactor_cmd.split_class(str(root_dir), str(file), split_config)
            )

            if result["success"]:
                click.echo("✅ Split completed successfully!")
                click.echo(f"   {result['message']}")
            else:
                raise click.ClickException(result.get("message", "Split failed"))
        finally:
            db.close()
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error("Invalid config or file: %s", e)
        raise click.ClickException(str(e))
    except Exception as e:
        logger.exception("Error during split-class: %s", e)
        raise click.ClickException(str(e))
