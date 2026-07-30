"""
Unit tests: load-generator suites sort last in the full sweep (bug 2aaac911).

``realsrv_test.suites._discover_suites`` sorts suites by ``(category_rank,
module_name)`` instead of plain module name so a suite tagged
``SUITE_CATEGORY = "load_generator"`` (currently only "loop" /
``s09_loop_liveness``, K=32 concurrent search against the shared heavy
project) always runs AFTER every ordinary suite in a full sweep -- fixing
the interference case confirmed on the real deployed server, where
``lifecycle_read_throughput.py`` ("throughput" / s11) measured a corrupted
0.646s/call immediately in "loop"'s wake. These tests pin: "loop" sorts
after "throughput" and "stability" even though its filename (``s09_...``)
alphabetically precedes both, every suite is still present exactly once, and
explicit single-suite selection by name is unaffected.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIVETESTS_DIR = Path(__file__).resolve().parents[1] / "livetests"
if str(_LIVETESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_LIVETESTS_DIR))

from realsrv_test.suites import collect_runners, list_suites  # noqa: E402
from realsrv_test.suites import s09_loop_liveness  # noqa: E402


def test_load_generator_suite_declares_its_category() -> None:
    """Regression pin: "loop" must stay tagged, or the ordering fix silently reverts."""
    assert s09_loop_liveness.SUITE_CATEGORY == "load_generator"


def test_loop_sorts_after_throughput_and_stability_in_the_full_suite_list() -> None:
    names_in_order = [name for name, _runners in list_suites()]
    assert "loop" in names_in_order
    assert "throughput" in names_in_order
    assert "stability" in names_in_order

    loop_index = names_in_order.index("loop")
    throughput_index = names_in_order.index("throughput")
    stability_index = names_in_order.index("stability")

    assert loop_index > throughput_index, names_in_order
    assert loop_index > stability_index, names_in_order


def test_loop_is_the_very_last_suite_in_the_full_list() -> None:
    """No load-generator-tagged suite exists after "loop" today, so it must be last."""
    names_in_order = [name for name, _runners in list_suites()]
    assert names_in_order[-1] == "loop", names_in_order


def test_every_suite_still_appears_exactly_once() -> None:
    names_in_order = [name for name, _runners in list_suites()]
    assert len(names_in_order) == len(set(names_in_order))


def test_explicit_single_suite_selection_by_name_is_unaffected() -> None:
    """Standalone-by-name selection still works exactly as before the ordering change."""
    runners = collect_runners(["loop"])
    assert len(runners) == 1
    assert runners[0].__name__ == "run_loop_liveness_check"

    runners = collect_runners(["throughput"])
    assert len(runners) == 1
    assert runners[0].__name__ == "run_read_throughput_check"
