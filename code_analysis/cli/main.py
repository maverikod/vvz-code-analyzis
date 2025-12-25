"""
Main CLI entry point for code analysis tool.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# mypy: ignore-errors

import click
import importlib
from typing import Dict

_COMMANDS: Dict[str, str] = {
    "analyze": "code_analysis.cli.main_cli:main",
    "search": "code_analysis.cli.search_cli:search",
    "refactor": "code_analysis.cli.refactor_cli:refactor",
    # IMPORTANT: keep server stack imports lazy; do NOT import hypercorn/uvicorn unless used.
    "server": "code_analysis.cli.server_manager_cli:server",
    "ast": "code_analysis.cli.ast_cli:ast",
    "analysis": "code_analysis.cli.analysis_cli:analysis",
    "vector": "code_analysis.cli.vector_cli:vector",
    "system": "code_analysis.cli.system_cli:system",
    "config": "code_analysis.cli.config_cli:config",
}


def _load_click_command(import_path: str) -> click.Command:
    module_path, obj_name = import_path.split(":", 1)
    mod = importlib.import_module(module_path)
    return getattr(mod, obj_name)


class LazyGroup(click.Group):
    """
    Click group that lazy-loads subcommands on demand.

    This prevents importing server engines (hypercorn/uvicorn) when users only run
    console utilities like `code_analysis analyze/search/...`.
    """

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted(_COMMANDS.keys())

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        target = _COMMANDS.get(cmd_name)
        if not target:
            return None
        return _load_click_command(target)


@click.group(cls=LazyGroup)
def cli() -> None:
    """Code analysis tool - analyze, search, and refactor Python code."""
    pass


if __name__ == "__main__":
    cli()
