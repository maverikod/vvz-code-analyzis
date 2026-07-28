"""
Auto-discovery for realsrv_test suites — the single source of execution truth.

A suite module is any Python module in this package that defines:
    SUITE_NAME: str          — unique, stable, CLI-addressable name
    LIFECYCLE_RUNNERS: tuple — one or more async ``(client, fixtures) ->
                               Dict[str, CommandOutcome]`` lifecycle callables

Modules are discovered via ``pkgutil.iter_modules`` over this package and
loaded in sorted order of their module names, which defines the stable
execution order (hence the ``sNN_`` filename prefix convention).  The runner
list the pipeline executes is built ONLY from this discovery — there is no
other registry.  Adding a new suite = dropping a new module in this
directory, zero changes elsewhere.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any, List, Sequence, Tuple

from realsrv_test.core.sweep import LifecycleRunner


def _discover_suites() -> List[Any]:
    """Return every suite module in stable sorted order.

    Returns:
        List of imported suite modules, sorted by module name.
    """
    pkg_path = str(Path(__file__).parent)
    modules = []
    for _finder, modname, _ispkg in pkgutil.iter_modules([pkg_path]):
        full_name = f"realsrv_test.suites.{modname}"
        mod = importlib.import_module(full_name)
        if hasattr(mod, "SUITE_NAME") and hasattr(mod, "LIFECYCLE_RUNNERS"):
            modules.append(mod)
    modules.sort(key=lambda m: m.__name__)
    return modules


def list_suites() -> List[Tuple[str, Sequence[LifecycleRunner]]]:
    """Return ``(suite_name, lifecycle_runners)`` for every discovered suite.

    Returns:
        Stable-sorted list of ``(SUITE_NAME, LIFECYCLE_RUNNERS)`` pairs.
    """
    return [(m.SUITE_NAME, m.LIFECYCLE_RUNNERS) for m in _discover_suites()]


def collect_runners(
    names: Sequence[str] | None = None,
) -> List[LifecycleRunner]:
    """Build the ordered runner list for the given suite names.

    This is the ONLY producer of the runner list the pipeline executes.

    Args:
        names: Suite names to include; ``None`` or empty means all suites.

    Returns:
        Flat ordered list of lifecycle runners across the selected suites.

    Raises:
        KeyError: If any name in ``names`` is not a discovered suite; the
            exception message lists the unknown and the available names.
    """
    suites = list_suites()
    available = [suite_name for suite_name, _ in suites]
    if names:
        unknown = sorted(set(names) - set(available))
        if unknown:
            raise KeyError(
                f"unknown suite(s): {unknown}; available: {available}"
            )
        selected = [
            (suite_name, runners)
            for suite_name, runners in suites
            if suite_name in set(names)
        ]
    else:
        selected = suites
    return [runner for _suite_name, runners in selected for runner in runners]
