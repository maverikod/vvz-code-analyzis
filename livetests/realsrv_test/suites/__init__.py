"""
Auto-discovery for realsrv_test suites.

A suite module is any Python module in this package that defines:
    SUITE_NAME: str          — unique, stable, CLI-addressable name
    LIFECYCLE_RUNNERS: tuple — zero or more async ``(client, fixtures) ->
                               Dict[str, CommandOutcome]`` lifecycle callables

Modules are discovered via ``pkgutil.iter_modules`` over this package and
loaded in sorted order of their module names (which also defines the stable
CLI subset order).  Adding a new suite = dropping a new module in this
directory, zero changes elsewhere.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any, Sequence


def _discover_suites() -> list[Any]:
    """Return every suite module in stable sorted order.

    Returns:
        List of imported suite modules, sorted by module name.
    """
    pkg_path = str(Path(__file__).parent)
    modules = []
    for finder, modname, _ispkg in pkgutil.iter_modules([pkg_path]):
        full_name = f"realsrv_test.suites.{modname}"
        mod = importlib.import_module(full_name)
        if hasattr(mod, "SUITE_NAME") and hasattr(mod, "LIFECYCLE_RUNNERS"):
            modules.append(mod)
    modules.sort(key=lambda m: m.__name__)
    return modules


def list_suites() -> list[tuple[str, Sequence[Any]]]:
    """Return ``(suite_name, lifecycle_runners)`` for every discovered suite.

    Returns:
        Stable-sorted list of ``(SUITE_NAME, LIFECYCLE_RUNNERS)`` pairs.
    """
    return [(m.SUITE_NAME, m.LIFECYCLE_RUNNERS) for m in _discover_suites()]


def get_suite(name: str) -> tuple[str, Sequence[Any]] | None:
    """Look up one suite by its ``SUITE_NAME``.

    Args:
        name: Suite name to search for (case-sensitive).

    Returns:
        ``(SUITE_NAME, LIFECYCLE_RUNNERS)`` or ``None`` if not found.
    """
    for suite_name, runners in list_suites():
        if suite_name == name:
            return suite_name, runners
    return None
