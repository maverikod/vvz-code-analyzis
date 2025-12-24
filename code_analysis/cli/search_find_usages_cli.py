"""
Search CLI command: find-usages.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# mypy: ignore-errors

import json
from pathlib import Path
from typing import Optional

import click

from ..core.database import CodeDatabase
from ..commands import SearchCommand


@click.command(name="find-usages")
@click.option(
    "--root-dir",
    "-r",
    required=True,
    help="Root directory of the project",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
@click.option(
    "--db-path",
    "-d",
    help="Path to SQLite database (default: root_dir/code_analysis/code_analysis.db)",
    type=click.Path(path_type=Path),
)
@click.argument("name")
@click.option(
    "--type",
    "-t",
    type=click.Choice(["method", "property", "function"]),
    help="Filter by target type",
)
@click.option(
    "--class",
    "-c",
    "class_name",
    help="Filter by class name",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
def find_usages(
    root_dir: Path,
    db_path: Optional[Path],
    name: str,
    type: Optional[str],
    class_name: Optional[str],
    format: str,
) -> None:
    """Find all usages of a method/property/function."""
    root_dir = root_dir.resolve()
    if not db_path:
        db_path = root_dir / "code_analysis" / "code_analysis.db"

    db = CodeDatabase(db_path)
    try:
        project_id = db.get_or_create_project(str(root_dir), name=root_dir.name)
        search_cmd = SearchCommand(db, project_id)
        usages = search_cmd.find_usages(name, target_type=type, target_class=class_name)

        if format == "json":
            click.echo(json.dumps(usages, indent=2, default=str))
            return

        if not usages:
            click.echo(f"No usages found for '{name}'")
            return

        click.echo(f"Found {len(usages)} usage(s) of '{name}':\n")
        for usage in usages:
            click.echo(f"  {usage['file_path']}:{usage['line']}")
            if usage.get("target_class"):
                click.echo(f"    Class: {usage['target_class']}")
            if usage.get("context"):
                click.echo(f"    Context: {usage['context']}")
            click.echo()
    finally:
        db.close()
