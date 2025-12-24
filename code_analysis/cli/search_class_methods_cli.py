"""
Search CLI command: class-methods.

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


@click.command(name="class-methods")
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
@click.argument("class_name")
@click.option(
    "--format",
    "-f",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
def class_methods(
    root_dir: Path, db_path: Optional[Path], class_name: str, format: str
) -> None:
    """List all methods of a class."""
    root_dir = root_dir.resolve()
    if not db_path:
        db_path = root_dir / "code_analysis" / "code_analysis.db"

    db = CodeDatabase(db_path)
    try:
        project_id = db.get_or_create_project(str(root_dir), name=root_dir.name)
        search_cmd = SearchCommand(db, project_id)
        methods = search_cmd.search_methods(None)
        methods = [m for m in methods if m.get("class_name") == class_name]

        if format == "json":
            click.echo(json.dumps(methods, indent=2, default=str))
            return

        if not methods:
            click.echo(f"No methods found for class '{class_name}'")
            return

        click.echo(f"Methods in class '{class_name}':\n")
        for method in methods:
            click.echo(f"  {method['name']}")
            click.echo(f"    File: {method['file_path']}:{method['line']}")
            if method.get("docstring"):
                doc_preview = method["docstring"][:80].replace("\n", " ")
                click.echo(f"    Docstring: {doc_preview}...")
            click.echo()
    finally:
        db.close()
