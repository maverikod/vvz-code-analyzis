"""
Main CLI entry point for code analysis tool.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# mypy: ignore-errors

import click

from .main_cli import main as analyze_main
from .search_cli import search as search_group
from .refactor_cli import refactor as refactor_group
from .server_manager_cli import server as server_group
from .ast_cli import ast as ast_group
from .analysis_cli import analysis as analysis_group
from .vector_cli import vector as vector_group
from .system_cli import system as system_group
from .config_cli import config as config_group


@click.group()
def cli() -> None:
    """Code analysis tool - analyze, search, and refactor Python code."""
    pass


# Add subcommands
cli.add_command(analyze_main, name="analyze")
cli.add_command(search_group, name="search")
cli.add_command(refactor_group, name="refactor")
cli.add_command(server_group, name="server")
cli.add_command(ast_group, name="ast")
cli.add_command(analysis_group, name="analysis")
cli.add_command(vector_group, name="vector")
cli.add_command(system_group, name="system")
cli.add_command(config_group, name="config")


if __name__ == "__main__":
    cli()
