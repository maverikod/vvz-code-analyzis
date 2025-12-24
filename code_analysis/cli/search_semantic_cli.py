"""
Search CLI command: semantic.

This mirrors MCP command: semantic_search.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# mypy: ignore-errors

import asyncio
import json
from pathlib import Path
from typing import Optional

import click

from ..core.database import CodeDatabase


@click.command(name="semantic")
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
    help="Path to SQLite database (default: root_dir/data/code_analysis.db)",
    type=click.Path(path_type=Path),
)
@click.argument("query")
@click.option("--k", "-k", type=int, default=10, help="Number of results to return")
@click.option(
    "--max-distance", type=float, default=None, help="Optional distance threshold"
)
@click.option(
    "--source-type",
    type=str,
    default=None,
    help="Filter by source type (docstring, file_docstring, comment)",
)
@click.option(
    "--file-path-substring",
    type=str,
    default=None,
    help="Substring to filter file paths",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format",
)
def semantic(
    root_dir: Path,
    db_path: Optional[Path],
    query: str,
    k: int,
    max_distance: Optional[float],
    source_type: Optional[str],
    file_path_substring: Optional[str],
    format: str,
) -> None:
    """Perform semantic search over code/docstrings using embeddings and FAISS."""
    root_dir = root_dir.resolve()
    if not db_path:
        db_path = root_dir / "data" / "code_analysis.db"

    if not db_path.exists():
        raise click.ClickException(f"Database not found: {db_path}")

    db = CodeDatabase(db_path)
    try:
        project_id = db.get_or_create_project(str(root_dir), name=root_dir.name)

        async def run() -> list[dict]:
            from mcp_proxy_adapter.config import get_config as get_adapter_config

            from ..commands.semantic_search import SemanticSearchCommand
            from ..core.config import ServerConfig
            from ..core.faiss_manager import FaissIndexManager
            from ..core.svo_client_manager import SVOClientManager

            adapter_cfg = get_adapter_config()
            cfg_data = getattr(adapter_cfg, "config_data", {}) if adapter_cfg else {}
            ca_cfg = cfg_data.get("code_analysis", {})
            server_cfg = ServerConfig(**ca_cfg) if ca_cfg else ServerConfig()

            if not server_cfg.vector_dim:
                raise click.ClickException(
                    "vector_dim is not configured (required for semantic search)"
                )

            faiss_path = (
                Path(server_cfg.faiss_index_path)
                if server_cfg.faiss_index_path
                else root_dir / "data" / "faiss_index"
            )
            faiss_path.parent.mkdir(parents=True, exist_ok=True)
            faiss_manager = FaissIndexManager(str(faiss_path), server_cfg.vector_dim)

            svo_client_manager = SVOClientManager(server_cfg)
            await svo_client_manager.initialize()
            try:
                search_cmd = SemanticSearchCommand(
                    db, project_id, faiss_manager, svo_client_manager
                )
                return await search_cmd.search(
                    query=query,
                    k=k,
                    max_distance=max_distance,
                    source_type=source_type,
                    file_path_substring=file_path_substring,
                )
            finally:
                await svo_client_manager.close()

        results = asyncio.run(run())
        if format == "json":
            click.echo(json.dumps(results, indent=2, default=str))
            return

        if not results:
            click.echo(f"No results found for query: '{query}'")
            return

        click.echo(f"Found {len(results)} result(s) for '{query}':\n")
        for result in results:
            click.echo(f"  File: {result.get('file_path', 'N/A')}")
            click.echo(f"  Line: {result.get('line', 'N/A')}")
            click.echo(f"  Distance: {result.get('distance', 'N/A')}")
            if result.get("chunk_text"):
                chunk_preview = str(result["chunk_text"])[:100].replace("\n", " ")
                click.echo(f"  Chunk: {chunk_preview}...")
            click.echo()
    finally:
        db.close()
