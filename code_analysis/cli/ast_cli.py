"""
CLI interface for AST operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import click
import json
import logging
from pathlib import Path
from typing import Optional

from ..core.database import CodeDatabase
from ..commands import (
    GetASTCommand,
    SearchASTNodesCommand,
    ASTStatisticsCommand,
    ListProjectFilesCommand,
    GetCodeEntityInfoCommand,
    ListCodeEntitiesCommand,
)

logger = logging.getLogger(__name__)


def _open_database(root_dir: Path) -> CodeDatabase:
    """Open database connection."""
    data_dir = root_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "code_analysis.db"
    return CodeDatabase(db_path)


def _get_project_id(
    db: CodeDatabase, root_dir: Path, project_id: Optional[str] = None
) -> str:
    """Get or create project ID."""
    if project_id:
        project = db.get_project(project_id)
        if project:
            return project_id
    return db.get_or_create_project(str(root_dir), name=root_dir.name)


@click.group()
def ast() -> None:
    """AST operations - work with Abstract Syntax Trees."""
    pass


@ast.command()
@click.option(
    "--root-dir",
    "-r",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Project root directory",
)
@click.option(
    "--file-path",
    "-f",
    required=True,
    type=str,
    help="Path to Python file (absolute or relative)",
)
@click.option(
    "--include-json/--no-json", default=True, help="Include full AST JSON in output"
)
@click.option("--project-id", type=str, help="Optional project UUID")
@click.option(
    "--format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format",
)
def get_ast(
    root_dir: Path,
    file_path: str,
    include_json: bool,
    project_id: Optional[str],
    format: str,
) -> None:
    """Get AST for a Python file from the analysis database."""
    db = _open_database(root_dir)
    try:
        proj_id = _get_project_id(db, root_dir, project_id)
        cmd = GetASTCommand(db, proj_id, file_path, include_json=include_json)
        import asyncio

        result = asyncio.run(cmd.execute())

        if result.get("success"):
            if format == "json":
                click.echo(json.dumps(result, indent=2))
            else:
                click.echo(f"✅ AST retrieved for {file_path}")
                if include_json and "ast_json" in result:
                    click.echo(f"   AST hash: {result.get('ast_hash', 'N/A')}")
        else:
            click.echo(f"❌ Error: {result.get('message', 'Unknown error')}", err=True)
            raise click.Abort()
    finally:
        db.close()


@ast.command()
@click.option(
    "--root-dir",
    "-r",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Project root directory",
)
@click.option(
    "--node-type",
    "-n",
    required=True,
    type=str,
    help="AST node type (e.g., ClassDef, FunctionDef)",
)
@click.option("--file-path", "-f", type=str, help="Optional file path to limit search")
@click.option("--limit", "-l", type=int, default=100, help="Maximum results")
@click.option("--project-id", type=str, help="Optional project UUID")
@click.option(
    "--format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format",
)
def search_nodes(
    root_dir: Path,
    node_type: str,
    file_path: Optional[str],
    limit: int,
    project_id: Optional[str],
    format: str,
) -> None:
    """Search AST nodes by type in project files."""
    db = _open_database(root_dir)
    try:
        proj_id = _get_project_id(db, root_dir, project_id)
        cmd = SearchASTNodesCommand(
            db, proj_id, node_type, file_path=file_path, limit=limit
        )
        import asyncio

        result = asyncio.run(cmd.execute())

        if result.get("success"):
            if format == "json":
                click.echo(json.dumps(result, indent=2))
            else:
                nodes = result.get("nodes", [])
                click.echo(f"✅ Found {len(nodes)} nodes of type {node_type}")
                for node in nodes[:10]:  # Show first 10
                    click.echo(
                        f"   {node.get('file_path', 'N/A')}:{node.get('line', 'N/A')} - {node.get('name', 'N/A')}"
                    )
        else:
            click.echo(f"❌ Error: {result.get('message', 'Unknown error')}", err=True)
            raise click.Abort()
    finally:
        db.close()


@ast.command()
@click.option(
    "--root-dir",
    "-r",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Project root directory",
)
@click.option("--project-id", type=str, help="Optional project UUID")
@click.option(
    "--format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format",
)
def statistics(root_dir: Path, project_id: Optional[str], format: str) -> None:
    """Get AST statistics for the project."""
    db = _open_database(root_dir)
    try:
        proj_id = _get_project_id(db, root_dir, project_id)
        cmd = ASTStatisticsCommand(db, proj_id)
        import asyncio

        result = asyncio.run(cmd.execute())

        if result.get("success"):
            if format == "json":
                click.echo(json.dumps(result, indent=2))
            else:
                stats = result.get("statistics", {})
                click.echo("✅ AST Statistics:")
                click.echo(f"   Total files: {stats.get('total_files', 0)}")
                click.echo(f"   Files with AST: {stats.get('files_with_ast', 0)}")
                click.echo(f"   Total classes: {stats.get('total_classes', 0)}")
                click.echo(f"   Total functions: {stats.get('total_functions', 0)}")
        else:
            click.echo(f"❌ Error: {result.get('message', 'Unknown error')}", err=True)
            raise click.Abort()
    finally:
        db.close()


@ast.command()
@click.option(
    "--root-dir",
    "-r",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Project root directory",
)
@click.option("--project-id", type=str, help="Optional project UUID")
@click.option(
    "--format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format",
)
def list_files(root_dir: Path, project_id: Optional[str], format: str) -> None:
    """List all files in the project."""
    db = _open_database(root_dir)
    try:
        proj_id = _get_project_id(db, root_dir, project_id)
        cmd = ListProjectFilesCommand(db, proj_id)
        import asyncio

        result = asyncio.run(cmd.execute())

        if result.get("success"):
            if format == "json":
                click.echo(json.dumps(result, indent=2))
            else:
                files = result.get("files", [])
                click.echo(f"✅ Found {len(files)} files in project")
                for file_info in files[:20]:  # Show first 20
                    click.echo(
                        f"   {file_info.get('path', 'N/A')} ({file_info.get('lines', 0)} lines)"
                    )
        else:
            click.echo(f"❌ Error: {result.get('message', 'Unknown error')}", err=True)
            raise click.Abort()
    finally:
        db.close()


@ast.command()
@click.option(
    "--root-dir",
    "-r",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Project root directory",
)
@click.option(
    "--entity-type",
    "-t",
    required=True,
    type=click.Choice(["class", "function", "method"]),
    help="Entity type",
)
@click.option("--entity-name", "-n", required=True, type=str, help="Entity name")
@click.option("--file-path", "-f", type=str, help="Optional file path")
@click.option("--line", "-l", type=int, help="Optional line number")
@click.option("--project-id", type=str, help="Optional project UUID")
@click.option(
    "--format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format",
)
def get_entity_info(
    root_dir: Path,
    entity_type: str,
    entity_name: str,
    file_path: Optional[str],
    line: Optional[int],
    project_id: Optional[str],
    format: str,
) -> None:
    """Get detailed information about a code entity."""
    db = _open_database(root_dir)
    try:
        proj_id = _get_project_id(db, root_dir, project_id)
        cmd = GetCodeEntityInfoCommand(
            db, proj_id, entity_type, entity_name, file_path=file_path, line=line
        )
        import asyncio

        result = asyncio.run(cmd.execute())

        if result.get("success"):
            if format == "json":
                click.echo(json.dumps(result, indent=2))
            else:
                entity = result.get("entity")
                if entity:
                    click.echo(f"✅ Found {entity_type}: {entity_name}")
                    click.echo(f"   File: {entity.get('file_path', 'N/A')}")
                    click.echo(f"   Line: {entity.get('line', 'N/A')}")
                    if entity.get("docstring"):
                        click.echo(
                            f"   Docstring: {entity.get('docstring', '')[:100]}..."
                        )
                else:
                    click.echo(f"❌ Entity not found: {entity_type} {entity_name}")
        else:
            click.echo(f"❌ Error: {result.get('message', 'Unknown error')}", err=True)
            raise click.Abort()
    finally:
        db.close()


@ast.command()
@click.option(
    "--root-dir",
    "-r",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Project root directory",
)
@click.option(
    "--entity-type",
    "-t",
    type=click.Choice(["class", "function", "method"]),
    help="Filter by entity type",
)
@click.option("--file-path", "-f", type=str, help="Optional file path to filter by")
@click.option("--limit", "-l", type=int, help="Maximum results")
@click.option("--offset", "-o", type=int, default=0, help="Offset for pagination")
@click.option("--project-id", type=str, help="Optional project UUID")
@click.option(
    "--format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format",
)
def list_entities(
    root_dir: Path,
    entity_type: Optional[str],
    file_path: Optional[str],
    limit: Optional[int],
    offset: int,
    project_id: Optional[str],
    format: str,
) -> None:
    """List code entities (classes, functions, methods) in a file or project."""
    db = _open_database(root_dir)
    try:
        proj_id = _get_project_id(db, root_dir, project_id)
        cmd = ListCodeEntitiesCommand(
            db,
            proj_id,
            entity_type=entity_type,
            file_path=file_path,
            limit=limit,
            offset=offset,
        )
        import asyncio

        result = asyncio.run(cmd.execute())

        if result.get("success"):
            if format == "json":
                click.echo(json.dumps(result, indent=2))
            else:
                entities = result.get("entities", [])
                click.echo(f"✅ Found {len(entities)} entities")
                for entity in entities[:20]:  # Show first 20
                    click.echo(
                        f"   {entity.get('type', 'N/A')}: {entity.get('name', 'N/A')} at {entity.get('file_path', 'N/A')}:{entity.get('line', 'N/A')}"
                    )
        else:
            click.echo(f"❌ Error: {result.get('message', 'Unknown error')}", err=True)
            raise click.Abort()
    finally:
        db.close()
