"""
Main CLI entry point for code analysis tool.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import click

from .main_cli import main as analyze_main
from .search_cli import search as search_group
from .refactor_cli import refactor as refactor_group
from .server_manager_cli import server as server_group


@click.group()
def cli() -> None:
    """Code analysis tool - analyze, search, and refactor Python code."""
    pass


# Add subcommands
cli.add_command(analyze_main, name="analyze")
cli.add_command(search_group, name="search")
cli.add_command(refactor_group, name="refactor")
cli.add_command(server_group, name="server")


if __name__ == "__main__":
    cli()
