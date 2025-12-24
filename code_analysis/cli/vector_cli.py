"""
CLI interface for vectorization operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# mypy: ignore-errors

import click
import json
import logging
from pathlib import Path
from typing import Optional

from ..core.database import CodeDatabase
from ..commands.check_vectors_command import CheckVectorsCommand
from ..commands.vector_commands import RebuildFaissCommand, RevectorizeCommand

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
def vector() -> None:
    """Vectorization operations - check vectors, rebuild FAISS, revectorize."""
    pass


def _load_watch_dirs(path: Path) -> list[str]:
    """Load dynamic watch dirs JSON file."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    watch_dirs = data.get("watch_dirs", [])
    if not isinstance(watch_dirs, list):
        return []
    return [str(p) for p in watch_dirs]


def _save_watch_dirs(path: Path, watch_dirs: list[str]) -> None:
    """Persist dynamic watch dirs JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"watch_dirs": watch_dirs}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


@vector.command(name="add-watch-dir")
@click.option(
    "--root-dir",
    "-r",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Project root directory (dynamic watch file defaults to <root-dir>/data/dynamic_watch_dirs.json)",
)
@click.option(
    "--path",
    "watch_path",
    required=True,
    type=str,
    help="Absolute path to directory to add to watch list",
)
@click.option(
    "--watch-file",
    type=click.Path(path_type=Path),
    default=None,
    help="Override dynamic watch file path (default: <root-dir>/data/dynamic_watch_dirs.json)",
)
def add_watch_dir(root_dir: Path, watch_path: str, watch_file: Optional[Path]) -> None:
    """
    Add a dynamic watch directory for the vectorization worker.

    This mirrors MCP command: add_watch_dir.
    """
    root_dir = root_dir.resolve()
    dynamic_file = watch_file or (root_dir / "data" / "dynamic_watch_dirs.json")

    # Normalize path (keep absolute to avoid ambiguity in workers)
    p = Path(watch_path).expanduser()
    if not p.is_absolute():
        raise click.ClickException("--path must be an absolute path")

    watch_dirs = _load_watch_dirs(dynamic_file)
    if str(p) not in watch_dirs:
        watch_dirs.append(str(p))
        watch_dirs = sorted(set(watch_dirs))
        _save_watch_dirs(dynamic_file, watch_dirs)

    click.echo(f"✅ Added watch dir: {p}")
    click.echo(f"📄 Watch file: {dynamic_file}")
    click.echo(f"📌 Total watch dirs: {len(watch_dirs)}")


@vector.command(name="remove-watch-dir")
@click.option(
    "--root-dir",
    "-r",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Project root directory (dynamic watch file defaults to <root-dir>/data/dynamic_watch_dirs.json)",
)
@click.option(
    "--path",
    "watch_path",
    required=True,
    type=str,
    help="Absolute path to directory to remove from watch list",
)
@click.option(
    "--watch-file",
    type=click.Path(path_type=Path),
    default=None,
    help="Override dynamic watch file path (default: <root-dir>/data/dynamic_watch_dirs.json)",
)
def remove_watch_dir(
    root_dir: Path, watch_path: str, watch_file: Optional[Path]
) -> None:
    """
    Remove a dynamic watch directory for the vectorization worker.

    This mirrors MCP command: remove_watch_dir.
    """
    root_dir = root_dir.resolve()
    dynamic_file = watch_file or (root_dir / "data" / "dynamic_watch_dirs.json")

    p = Path(watch_path).expanduser()
    if not p.is_absolute():
        raise click.ClickException("--path must be an absolute path")

    watch_dirs = _load_watch_dirs(dynamic_file)
    new_watch_dirs = [x for x in watch_dirs if x != str(p)]
    if new_watch_dirs != watch_dirs:
        new_watch_dirs = sorted(set(new_watch_dirs))
        _save_watch_dirs(dynamic_file, new_watch_dirs)

    click.echo(f"✅ Removed watch dir: {p}")
    click.echo(f"📄 Watch file: {dynamic_file}")
    click.echo(f"📌 Total watch dirs: {len(new_watch_dirs)}")


@vector.command()
@click.option(
    "--root-dir",
    "-r",
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
def check(root_dir: Optional[Path], project_id: Optional[str], format: str) -> None:
    """Check vector statistics in database."""
    if not root_dir:
        # Try to find database from current directory
        current_dir = Path.cwd()
        possible_paths = [
            current_dir / "data" / "code_analysis.db",
            current_dir.parent / "data" / "code_analysis.db",
        ]
        for path in possible_paths:
            if path.exists():
                root_dir = path.parent.parent
                break

        if not root_dir:
            click.echo("❌ Error: root_dir required or database not found", err=True)
            raise click.Abort()

    db = _open_database(root_dir)
    try:
        cmd = CheckVectorsCommand()
        import asyncio

        result = asyncio.run(cmd.execute(root_dir=str(root_dir), project_id=project_id))

        payload = result.to_dict()
        if payload.get("success"):
            data = payload.get("data", {})
            if format == "json":
                click.echo(json.dumps(data, indent=2))
                return
            click.echo("✅ Vector Statistics:")
            click.echo(f"   Total chunks: {data.get('total_chunks', 0)}")
            click.echo(f"   Chunks with vector: {data.get('chunks_with_vector', 0)}")
            click.echo(
                f"   Chunks pending: {data.get('chunks_pending_vectorization', 0)}"
            )
            click.echo(f"   Vectorization: {data.get('vectorization_percentage', 0)}%")
            return

        err = payload.get("error", {})
        click.echo(f"❌ Error: {err.get('message', 'Unknown error')}", err=True)
        raise click.Abort()
    finally:
        db.close()


@vector.command()
@click.option(
    "--root-dir",
    "-r",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Project root directory",
)
@click.option("--project-id", type=str, help="Optional project UUID")
@click.option("--force", "-f", is_flag=True, help="Force rebuild even if index exists")
def rebuild_faiss(root_dir: Path, project_id: Optional[str], force: bool) -> None:
    """Rebuild FAISS index from database vectors."""
    db = _open_database(root_dir)
    try:
        proj_id = _get_project_id(db, root_dir, project_id)
        cmd = RebuildFaissCommand()
        import asyncio

        result = asyncio.run(
            cmd.execute(root_dir=str(root_dir), project_id=proj_id, force=force)
        )

        payload = result.to_dict()
        if payload.get("success"):
            data = payload.get("data", {})
            click.echo("✅ FAISS index rebuilt successfully")
            click.echo(
                f"   Vectors: {data.get('vectors', data.get('vectors_count', 0))}"
            )
            return

        err = payload.get("error", {})
        click.echo(f"❌ Error: {err.get('message', 'Unknown error')}", err=True)
        raise click.Abort()
    finally:
        db.close()


@vector.command()
@click.option(
    "--root-dir",
    "-r",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Project root directory",
)
@click.option("--project-id", type=str, help="Optional project UUID")
@click.option(
    "--force", "-f", is_flag=True, help="Force revectorization even if vectors exist"
)
def revectorize(root_dir: Path, project_id: Optional[str], force: bool) -> None:
    """Revectorize code chunks in database."""
    db = _open_database(root_dir)
    try:
        proj_id = _get_project_id(db, root_dir, project_id)
        cmd = RevectorizeCommand()
        import asyncio

        result = asyncio.run(
            cmd.execute(root_dir=str(root_dir), project_id=proj_id, force=force)
        )

        payload = result.to_dict()
        if payload.get("success"):
            data = payload.get("data", {})
            click.echo("✅ Revectorization completed")
            click.echo(
                f"   Processed: {data.get('processed_files', data.get('processed', 0))}"
            )
            click.echo(f"   Errors: {data.get('errors', 0)}")
            return

        err = payload.get("error", {})
        click.echo(f"❌ Error: {err.get('message', 'Unknown error')}", err=True)
        raise click.Abort()
    finally:
        db.close()
