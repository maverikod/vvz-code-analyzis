#!/usr/bin/env python3
"""
CLI interface for code-analysis tool.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import click
import logging
from pathlib import Path

from .code_mapper import CodeMapper

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s"
)
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--root-dir",
    "-r",
    default=".",
    help="Root directory to analyze",
    type=click.Path(
        exists=True, file_okay=False, dir_okay=True, path_type=Path
    ),
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
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output",
)
@click.version_option(version="1.0.2")
def main(
    root_dir: Path, output_dir: Path, max_lines: int, verbose: bool
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
        click.echo()

        # Initialize code mapper
        mapper = CodeMapper(str(root_dir), str(output_dir), max_lines)

        # Analyze directory
        mapper.analyze_directory(str(root_dir))

        # Generate reports
        mapper.generate_reports()

        click.echo()
        click.echo("✅ Analysis completed successfully!")

    except Exception as e:
        logger.error(f"Error during analysis: {e}")
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()


if __name__ == "__main__":
    main()
