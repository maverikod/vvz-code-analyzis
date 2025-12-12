"""
CLI commands for searching code.

Provides commands for finding usages and full-text search.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import click
import json
from pathlib import Path
from typing import Optional

from ..core.database import CodeDatabase
from ..commands import SearchCommand


@click.group()
def search() -> None:
    """Search commands for code analysis."""
    pass


@search.command()
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
    """
    Find all usages of a method or property.

    Example:
        code_search find-usages --root-dir /path/to/project method_name
        code_search find-usages --root-dir /path/to/project property_name \
            --type property
        code_search find-usages --root-dir /path/to/project method_name \
            --class ClassName
    """
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
        else:
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


@search.command()
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
    """
    Perform full-text search in code content and docstrings.

    Example:
        code_search fulltext --root-dir /path/to/project "async def"
        code_search fulltext --root-dir /path/to/project "database connection" \
            --type method
        code_search fulltext --root-dir /path/to/project "error handling" \
            --limit 10
    """
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
        else:
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


@search.command()
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
    """
    List all methods of a class.

    Example:
        code_search class-methods --root-dir /path/to/project ClassName
    """
    root_dir = root_dir.resolve()
    if not db_path:
        db_path = root_dir / "code_analysis" / "code_analysis.db"

    db = CodeDatabase(db_path)
    try:
        project_id = db.get_or_create_project(str(root_dir), name=root_dir.name)
        search_cmd = SearchCommand(db, project_id)
        # Search for methods - get all methods in project, then filter by class
        methods = search_cmd.search_methods(None)
        # Filter by class name
        methods = [m for m in methods if m.get("class_name") == class_name]

        if format == "json":
            click.echo(json.dumps(methods, indent=2, default=str))
        else:
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


@search.command()
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
    """
    Find classes by name pattern.

    Example:
        code_search find-classes --root-dir /path/to/project "Handler"
        code_search find-classes --root-dir /path/to/project "Service"
    """
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
        else:
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


if __name__ == "__main__":
    search()
