"""
Search CLI command: find-classes.

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


@click.command(name="find-classes")
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
@click.argument("pattern")
@click.option(
    "--format",
    "-f",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
def find_classes(
    root_dir: Path, db_path: Optional[Path], pattern: str, format: str
) -> None:
    """Find classes by name pattern."""
    root_dir = root_dir.resolve()
    if not db_path:
        db_path = root_dir / "code_analysis" / "code_analysis.db"

    db = CodeDatabase(db_path)
    try:
        project_id = db.get_or_create_project(str(root_dir), name=root_dir.name)
        search_cmd = SearchCommand(db, project_id)
        classes = search_cmd.search_classes(pattern)

        if format == "json":
            click.echo(json.dumps(classes, indent=2, default=str))
            return

        if not classes:
            click.echo(f"No classes found matching '{pattern}'")
            return

        click.echo(f"Found {len(classes)} class(es) matching '{pattern}':\n")
        for cls in classes:
            click.echo(f"  {cls['name']}")
            click.echo(f"    File: {cls['file_path']}:{cls['line']}")
            if cls.get("docstring"):
                doc_preview = cls["docstring"][:80].replace("\n", " ")
                click.echo(f"    Docstring: {doc_preview}...")
            click.echo()
    finally:
        db.close()
