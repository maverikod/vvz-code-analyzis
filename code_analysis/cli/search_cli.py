"""
CLI commands for searching code.

This module is intentionally small and delegates command implementations to
dedicated modules to keep files within the 400-line limit.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# mypy: ignore-errors

import click

from .search_class_methods_cli import class_methods
from .search_find_classes_cli import find_classes
from .search_find_usages_cli import find_usages
from .search_fulltext_cli import fulltext
from .search_semantic_cli import semantic


@click.group()
def search() -> None:
    """Search commands for code analysis."""


search.add_command(find_usages)
search.add_command(fulltext)
search.add_command(class_methods)
search.add_command(find_classes)
search.add_command(semantic)
