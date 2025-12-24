"""
Refactor CLI command: extract-superclass.

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


@click.command(name="extract-superclass")
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
    help="JSON configuration file for superclass extraction",
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
def extract_superclass(
    root_dir: Path, file: Path, config: Path, db_path: Path | None, dry_run: bool
) -> None:
    """Extract common functionality into a base class."""
    try:
        with open(config, "r", encoding="utf-8") as f:
            extract_config = json.load(f)

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
                from ..core.refactorer import SuperclassExtractor

                extractor = SuperclassExtractor(file)
                extractor.load_file()

                is_valid, errors = extractor.validate_config(extract_config)
                if not is_valid:
                    raise click.ClickException(
                        "Configuration validation failed:\n"
                        + "\n".join(f"- {e}" for e in errors)
                    )

                base_class = extract_config.get("base_class")
                child_classes = extract_config.get("child_classes", [])
                is_safe, conflict_error = (
                    extractor.check_multiple_inheritance_conflicts(
                        child_classes, base_class
                    )
                )
                if not is_safe:
                    raise click.ClickException(
                        f"Multiple inheritance conflict: {conflict_error}"
                    )

                click.echo("✅ Configuration is valid")
                click.echo("✅ No multiple inheritance conflicts detected")
                return

            result = asyncio.run(
                refactor_cmd.extract_superclass(
                    str(root_dir), str(file), extract_config
                )
            )

            if result["success"]:
                click.echo("✅ Superclass extraction completed successfully!")
                click.echo(f"   {result['message']}")
            else:
                raise click.ClickException(result.get("message", "Extraction failed"))
        finally:
            db.close()
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error("Invalid config or file: %s", e)
        raise click.ClickException(str(e))
    except Exception as e:
        logger.exception("Error during extract-superclass: %s", e)
        raise click.ClickException(str(e))
