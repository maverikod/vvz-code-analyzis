#!/usr/bin/env python3
"""
CLI interface for code-analysis tool.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# mypy: ignore-errors

import click
import logging
from pathlib import Path

from ..core.database import CodeDatabase
from ..commands import AnalyzeCommand

# Setup logging
# Use logger from adapter (configured by adapter)
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--root-dir",
    "-r",
    required=True,
    help="Root directory of the project to analyze",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
@click.option(
    "--output-dir",
    "-o",
    default="code_analysis",
    help="Output directory for reports",
    type=click.Path(path_type=Path),
)
@click.option(
    "--max-lines",
    "-m",
    type=int,
    default=400,
    help="Maximum lines per file",
)
@click.option(
    "--comment",
    "-c",
    help="Human-readable comment/identifier for project",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output",
)
@click.option(
    "--use-sqlite/--no-sqlite",
    default=True,
    help="Use SQLite database (default: True)",
)
@click.option(
    "--config",
    "-C",
    "config_path",
    default=None,
    help="Path to config.json (default: <root-dir>/config.json)",
    type=click.Path(exists=False, dir_okay=False, path_type=Path),
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Process all files regardless of modification time. "
    "By default, files are only processed if they are newer than stored AST trees.",
)
@click.option(
    "--file-path",
    "-p",
    default=None,
    help="Optional path to a single Python file to analyze (absolute or relative to --root-dir)",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
)
@click.version_option(version="1.0.3")
def main(
    root_dir: Path,
    output_dir: Path,
    max_lines: int,
    comment: str | None,
    verbose: bool,
    use_sqlite: bool,
    config_path: Path | None,
    force: bool,
    file_path: Path | None,
) -> None:
    """
    Analyze Python codebase and generate comprehensive reports.

    This tool analyzes Python code and generates:
    - Code map with classes, functions, and dependencies
    - Issue reports with code quality problems
    - Method index for easy navigation

    Example:
        code_mapper --root-dir ./src --output-dir ./reports --max-lines 500
    """
    if verbose:
        # Set debug level for this logger only
        logger.setLevel(logging.DEBUG)

    try:
        click.echo(f"🔍 Analyzing code in: {root_dir.absolute()}")
        click.echo(f"📁 Output directory: {output_dir.absolute()}")
        click.echo(f"📏 Max lines per file: {max_lines}")
        if comment:
            click.echo(f"💬 Project comment: {comment}")
        click.echo()

        root_dir = root_dir.resolve()

        if not use_sqlite:
            # Legacy YAML mode (if needed)
            from ..code_mapper import CodeMapper

            mapper = CodeMapper(
                str(root_dir), str(output_dir), max_lines, use_sqlite=False
            )
            mapper.analyze_directory(str(root_dir))
            mapper.generate_reports()

            click.echo()
            click.echo("✅ Analysis completed successfully!")
            return

        # Use SQLite + SVO clients
        data_dir = root_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = data_dir / "code_analysis.db"

        # Load code_analysis config (for chunker/embedding)
        config_file = config_path or (root_dir / "config.json")
        if not config_file.exists():
            raise click.ClickException(f"Config file not found: {config_file}")

        try:
            import json
            from ..core.config import ServerConfig
            from ..core.svo_client_manager import SVOClientManager
        except Exception as e:
            raise click.ClickException(f"Failed to import config/client modules: {e}")

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                raw_cfg = json.load(f)
            ca_cfg = raw_cfg.get("code_analysis") or raw_cfg
            server_cfg = ServerConfig(**ca_cfg)
        except Exception as e:
            raise click.ClickException(f"Failed to load config '{config_file}': {e}")

        db = CodeDatabase(db_path)
        try:
            project_id = db.get_or_create_project(
                str(root_dir), name=root_dir.name, comment=comment
            )

            # Init SVO client manager
            svo_client_manager = SVOClientManager(server_cfg)

            async def run_analysis():
                await svo_client_manager.initialize()
                analyze_cmd = AnalyzeCommand(
                    db,
                    project_id,
                    str(root_dir),
                    max_lines,
                    force=force,
                    svo_client_manager=svo_client_manager,
                )
                if file_path:
                    return await analyze_cmd.analyze_file(file_path, force=force)
                return await analyze_cmd.execute()

            import asyncio

            result = asyncio.run(run_analysis())

            click.echo()
            if file_path:
                if result.get("success"):
                    click.echo("✅ File analysis completed successfully!")
                    click.echo(f"   File: {result.get('file_path')}")
                    click.echo(f"   Classes: {result.get('classes', 0)}")
                    click.echo(f"   Functions: {result.get('functions', 0)}")
                    click.echo(f"   Methods: {result.get('methods', 0)}")
                    click.echo(f"   Issues: {result.get('issues', 0)}")
                    click.echo(f"   Project ID: {result.get('project_id')}")
                else:
                    raise click.ClickException(
                        result.get("error", "File analysis failed")
                    )
            else:
                click.echo("✅ Analysis completed successfully!")
                click.echo(f"   Files analyzed: {result['files_analyzed']}")
                click.echo(f"   Classes: {result['classes']}")
                click.echo(f"   Functions: {result['functions']}")
                click.echo(f"   Issues: {result['issues']}")
                click.echo(f"   Project ID: {result['project_id']}")
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error during analysis: {e}")
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()


if __name__ == "__main__":
    main()
