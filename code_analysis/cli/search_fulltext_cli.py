"""
Search CLI command: fulltext.

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


@click.command(name="fulltext")
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
@click.argument("query")
@click.option(
    "--type",
    "-t",
    type=click.Choice(["class", "method", "function"]),
    help="Filter by entity type",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=20,
    help="Maximum number of results",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
def fulltext(
    root_dir: Path,
    db_path: Optional[Path],
    query: str,
    type: Optional[str],
    limit: int,
    format: str,
) -> None:
    """Perform full-text search in code content and docstrings."""
    root_dir = root_dir.resolve()
    if not db_path:
        db_path = root_dir / "code_analysis" / "code_analysis.db"

    db = CodeDatabase(db_path)
    try:
        project_id = db.get_or_create_project(str(root_dir), name=root_dir.name)
        search_cmd = SearchCommand(db, project_id)
        results = search_cmd.full_text_search(query, entity_type=type, limit=limit)

        if format == "json":
            click.echo(json.dumps(results, indent=2, default=str))
            return

        if not results:
            click.echo(f"No results found for query: '{query}'")
            return

        click.echo(f"Found {len(results)} result(s) for '{query}':\n")
        for result in results:
            click.echo(f"  {result['entity_type']}: {result['entity_name']}")
            click.echo(f"  File: {result['file_path']}")
            if result.get("docstring"):
                doc_preview = result["docstring"][:100].replace("\n", " ")
                click.echo(f"  Docstring: {doc_preview}...")
            click.echo()
    finally:
        db.close()
