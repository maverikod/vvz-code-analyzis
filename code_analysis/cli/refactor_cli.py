"""
CLI interface for code refactoring commands.

This module is intentionally small and delegates command implementations to
dedicated modules to keep files within the 400-line limit.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# mypy: ignore-errors

import click

from .refactor_extract_superclass_cli import extract_superclass
from .refactor_merge_classes_cli import merge_classes
from .refactor_split_class_cli import split_class
from .refactor_split_file_to_package_cli import split_file_to_package


@click.group()
def refactor() -> None:
    """Code refactoring commands."""


refactor.add_command(split_class)
refactor.add_command(extract_superclass)
refactor.add_command(merge_classes)
refactor.add_command(split_file_to_package)
