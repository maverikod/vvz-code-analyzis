#!/usr/bin/env python3
"""
CLI interface for code-analysis tool.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import click
import logging
from pathlib import Path

from ..core.database import CodeDatabase
from ..commands import AnalyzeCommand

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
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
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Process all files regardless of modification time. "
    "By default, files are only processed if they are newer than stored AST trees.",
)
@click.version_option(version="1.0.3")
def main(
    root_dir: Path,
    output_dir: Path,
    max_lines: int,
    comment: str | None,
    verbose: bool,
    use_sqlite: bool,
    force: bool,
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
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        click.echo(f"🔍 Analyzing code in: {root_dir.absolute()}")
        click.echo(f"📁 Output directory: {output_dir.absolute()}")
        click.echo(f"📏 Max lines per file: {max_lines}")
        if comment:
            click.echo(f"💬 Project comment: {comment}")
        click.echo()

        root_dir = root_dir.resolve()

        if use_sqlite:
            # Use commands layer
            db_path = output_dir / "code_analysis.db"
            db = CodeDatabase(db_path)
            try:
                project_id = db.get_or_create_project(
                    str(root_dir), name=root_dir.name, comment=comment
                )
                analyze_cmd = AnalyzeCommand(
                    db, project_id, str(root_dir), max_lines, force=force
                )
                import asyncio

                result = asyncio.run(analyze_cmd.execute())

                click.echo()
                click.echo("✅ Analysis completed successfully!")
                click.echo(f"   Files analyzed: {result['files_analyzed']}")
                click.echo(f"   Classes: {result['classes']}")
                click.echo(f"   Functions: {result['functions']}")
                click.echo(f"   Issues: {result['issues']}")
                click.echo(f"   Project ID: {result['project_id']}")
            finally:
                db.close()
        else:
            # Legacy YAML mode (if needed)
            from ..code_mapper import CodeMapper

            mapper = CodeMapper(
                str(root_dir), str(output_dir), max_lines, use_sqlite=False
            )
            mapper.analyze_directory(str(root_dir))
            mapper.generate_reports()

            click.echo()
            click.echo("✅ Analysis completed successfully!")

    except Exception as e:
        logger.error(f"Error during analysis: {e}")
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()


if __name__ == "__main__":
    main()
