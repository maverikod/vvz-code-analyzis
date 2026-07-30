"""
Auto-discovery for realsrv_test suites — the single source of execution truth.

A suite module is any Python module in this package that defines:
    SUITE_NAME: str          — unique, stable, CLI-addressable name
    LIFECYCLE_RUNNERS: tuple — one or more async ``(client, fixtures) ->
                               Dict[str, CommandOutcome]`` lifecycle callables

A suite module MAY also define:
    SUITE_CATEGORY: str — ``"load_generator"`` marks a suite that
                           deliberately fires heavy concurrent load against a
                           shared project (currently only
                           ``s09_loop_liveness``, K=32 concurrent search).
                           Omitted (the default) means "ordinary" for
                           ordering purposes.

Modules are discovered via ``pkgutil.iter_modules`` over this package and
sorted primarily by category — ``load_generator`` suites always sort AFTER
every ordinary suite — and secondarily by module name, which is what
previously defined the whole stable execution order (hence the ``sNN_``
filename prefix convention; still the tie-breaker within a category).  This
ordering exists to fix bug 2aaac911's suite-interference case: a timing-
sensitive suite (e.g. ``s11_read_throughput``, ``s15_measurement_stability``)
must not run in the immediate wake of a load-generator suite's storm against
the same shared project, or its verdict reflects that neighbouring load
instead of the code under test — confirmed on the real deployed server (see
``realsrv_test.core.lifecycle_read_throughput`` module docstring). Pushing
load generators to run last in the full sweep, rather than adding a cooldown
sleep, is the least intrusive fix: it costs no extra wall-clock time and
every suite still runs exactly once, in a stable order.  A suite selected by
explicit name (``pipeline_live_verifier <suite> ...``) is unaffected — this
ordering only decides RELATIVE position, never whether a suite runs.

The runner list the pipeline executes is built ONLY from this discovery —
there is no other registry.  Adding a new suite = dropping a new module in
this directory, zero changes elsewhere.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any, List, Sequence, Tuple

from realsrv_test.core.sweep import LifecycleRunner

# The only recognized non-default category. Anything else (including the
# absent attribute) sorts as "ordinary" — see module docstring.
_LOAD_GENERATOR_CATEGORY = "load_generator"


def _category_rank(mod: Any) -> int:
    """Return the sort rank for a suite module's ``SUITE_CATEGORY``.

    Args:
        mod: An imported suite module.

    Returns:
        1 if the module declares ``SUITE_CATEGORY = "load_generator"``
        (sorts last); 0 otherwise (ordinary, sorts first).
    """
    return 1 if getattr(mod, "SUITE_CATEGORY", "") == _LOAD_GENERATOR_CATEGORY else 0


def _discover_suites() -> List[Any]:
    """Return every suite module in stable (category, name) sorted order.

    Returns:
        List of imported suite modules: ordinary suites first (sorted by
        module name), then ``load_generator`` suites (also sorted by module
        name among themselves) — see module docstring for why.
    """
    pkg_path = str(Path(__file__).parent)
    modules = []
    for _finder, modname, _ispkg in pkgutil.iter_modules([pkg_path]):
        full_name = f"realsrv_test.suites.{modname}"
        mod = importlib.import_module(full_name)
        if hasattr(mod, "SUITE_NAME") and hasattr(mod, "LIFECYCLE_RUNNERS"):
            modules.append(mod)
    modules.sort(key=lambda m: (_category_rank(m), m.__name__))
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
