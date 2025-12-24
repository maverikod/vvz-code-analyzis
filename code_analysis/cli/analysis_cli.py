"""
CLI interface for analysis operations (dependencies, imports, hierarchy, usages).

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
    GetImportsCommand,
    FindDependenciesCommand,
    GetClassHierarchyCommand,
    FindUsagesCommand,
    ExportGraphCommand,
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
def analysis() -> None:
    """Analysis operations - dependencies, imports, hierarchy, usages."""
    pass


@analysis.command()
@click.option(
    "--root-dir",
    "-r",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Project root directory",
)
@click.option("--file-path", "-f", type=str, help="Optional file path to filter by")
@click.option("--project-id", type=str, help="Optional project UUID")
@click.option(
    "--format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format",
)
def get_imports(
    root_dir: Path, file_path: Optional[str], project_id: Optional[str], format: str
) -> None:
    """Get imports for a file or project."""
    db = _open_database(root_dir)
    try:
        proj_id = _get_project_id(db, root_dir, project_id)
        cmd = GetImportsCommand(db, proj_id, file_path=file_path)
        import asyncio

        result = asyncio.run(cmd.execute())

        if result.get("success"):
            if format == "json":
                click.echo(json.dumps(result, indent=2))
            else:
                imports = result.get("imports", [])
                click.echo(f"✅ Found {len(imports)} imports")
                for imp in imports[:20]:  # Show first 20
                    click.echo(
                        f"   {imp.get('name', 'N/A')} from {imp.get('module', 'N/A')} ({imp.get('import_type', 'N/A')})"
                    )
        else:
            click.echo(f"❌ Error: {result.get('message', 'Unknown error')}", err=True)
            raise click.Abort()
    finally:
        db.close()


@analysis.command()
@click.option(
    "--root-dir",
    "-r",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Project root directory",
)
@click.option("--file-path", "-f", type=str, help="Optional file path to analyze")
@click.option("--project-id", type=str, help="Optional project UUID")
@click.option(
    "--format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format",
)
def find_dependencies(
    root_dir: Path, file_path: Optional[str], project_id: Optional[str], format: str
) -> None:
    """Find dependencies for a file or project."""
    db = _open_database(root_dir)
    try:
        proj_id = _get_project_id(db, root_dir, project_id)
        cmd = FindDependenciesCommand(db, proj_id, file_path=file_path)
        import asyncio

        result = asyncio.run(cmd.execute())

        if result.get("success"):
            if format == "json":
                click.echo(json.dumps(result, indent=2))
            else:
                deps = result.get("dependencies", [])
                click.echo(f"✅ Found {len(deps)} dependencies")
                for dep in deps[:20]:  # Show first 20
                    click.echo(
                        f"   {dep.get('source', 'N/A')} -> {dep.get('target', 'N/A')} ({dep.get('type', 'N/A')})"
                    )
        else:
            click.echo(f"❌ Error: {result.get('message', 'Unknown error')}", err=True)
            raise click.Abort()
    finally:
        db.close()


@analysis.command()
@click.option(
    "--root-dir",
    "-r",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Project root directory",
)
@click.option(
    "--class-name", "-c", type=str, help="Optional class name to get hierarchy for"
)
@click.option("--project-id", type=str, help="Optional project UUID")
@click.option(
    "--format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format",
)
def class_hierarchy(
    root_dir: Path, class_name: Optional[str], project_id: Optional[str], format: str
) -> None:
    """Get class hierarchy for the project."""
    db = _open_database(root_dir)
    try:
        proj_id = _get_project_id(db, root_dir, project_id)
        cmd = GetClassHierarchyCommand(db, proj_id, class_name=class_name)
        import asyncio

        result = asyncio.run(cmd.execute())

        if result.get("success"):
            if format == "json":
                click.echo(json.dumps(result, indent=2))
            else:
                hierarchy = result.get("hierarchy", [])
                click.echo(f"✅ Found {len(hierarchy)} classes in hierarchy")
                for cls in hierarchy[:20]:  # Show first 20
                    bases = ", ".join(cls.get("bases", []))
                    click.echo(
                        f"   {cls.get('name', 'N/A')} ({bases if bases else 'no bases'})"
                    )
        else:
            click.echo(f"❌ Error: {result.get('message', 'Unknown error')}", err=True)
            raise click.Abort()
    finally:
        db.close()


@analysis.command()
@click.option(
    "--root-dir",
    "-r",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Project root directory",
)
@click.option(
    "--name", "-n", required=True, type=str, help="Target name to find usages for"
)
@click.option(
    "--target-type", "-t", type=str, help="Target type (method, property, class, etc.)"
)
@click.option(
    "--target-class",
    "-c",
    type=str,
    help="Target class name (if target is method/property)",
)
@click.option("--project-id", type=str, help="Optional project UUID")
@click.option(
    "--format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format",
)
def find_usages(
    root_dir: Path,
    name: str,
    target_type: Optional[str],
    target_class: Optional[str],
    project_id: Optional[str],
    format: str,
) -> None:
    """Find usages of a method, property, or class."""
    db = _open_database(root_dir)
    try:
        proj_id = _get_project_id(db, root_dir, project_id)
        cmd = FindUsagesCommand(
            db, proj_id, name, target_type=target_type, target_class=target_class
        )
        import asyncio

        result = asyncio.run(cmd.execute())

        if result.get("success"):
            if format == "json":
                click.echo(json.dumps(result, indent=2))
            else:
                usages = result.get("usages", [])
                click.echo(f"✅ Found {len(usages)} usages of {name}")
                for usage in usages[:20]:  # Show first 20
                    click.echo(
                        f"   {usage.get('file_path', 'N/A')}:{usage.get('line', 'N/A')} - {usage.get('context', 'N/A')}"
                    )
        else:
            click.echo(f"❌ Error: {result.get('message', 'Unknown error')}", err=True)
            raise click.Abort()
    finally:
        db.close()


@analysis.command()
@click.option(
    "--root-dir",
    "-r",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Project root directory",
)
@click.option(
    "--output", "-o", type=click.Path(path_type=Path), help="Output file path"
)
@click.option(
    "--format", type=click.Choice(["dot", "json"]), default="dot", help="Graph format"
)
@click.option(
    "--graph-type",
    type=click.Choice(["dependencies", "hierarchy", "usages"]),
    default="dependencies",
    help="Graph type",
)
@click.option("--project-id", type=str, help="Optional project UUID")
def export_graph(
    root_dir: Path,
    output: Optional[Path],
    format: str,
    graph_type: str,
    project_id: Optional[str],
) -> None:
    """Export code structure graph (dependencies, hierarchy, or usages)."""
    db = _open_database(root_dir)
    try:
        proj_id = _get_project_id(db, root_dir, project_id)
        cmd = ExportGraphCommand(db, proj_id, graph_type=graph_type, format=format)
        import asyncio

        result = asyncio.run(cmd.execute())

        if result.get("success"):
            graph_data = result.get("graph", "")
            if output:
                output.write_text(graph_data)
                click.echo(f"✅ Graph exported to {output}")
            else:
                click.echo(graph_data)
        else:
            click.echo(f"❌ Error: {result.get('message', 'Unknown error')}", err=True)
            raise click.Abort()
    finally:
        db.close()
