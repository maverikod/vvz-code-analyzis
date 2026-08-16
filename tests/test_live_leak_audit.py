"""
Unit tests: the ``pipeline live-leak-audit`` classifier (bug d5835fbf).

``classify_leak_audit`` is a pure function over synthetic live-project-name /
trash-item inventories -- no server, no client stub needed. Pins: (1) a live
fixture-prefix project is always RED regardless of age; (2) a trash entry
younger than the grace window is tolerated (GREEN); (3) the same entry once
older than the grace window flips to RED; (4) the always-excluded
``verify_editor_*`` prefix (another project's own fixtures) is never
flagged even though it would otherwise match the generic ``verify_``
fallback bucket; (5) names/entries matching no fixture prefix at all
(e.g. a human's own project) are silently ignored; (6) an unparsable
``deleted_at`` is treated as "age unknown", never as "old" (no false RED).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from code_analysis.live_leak_audit import classify_leak_audit

_NOW = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)


def _trash_item(original_name: str, hours_ago: float, folder_suffix: str = "") -> dict:
    deleted_at_dt = _NOW - timedelta(hours=hours_ago)
    deleted_at = deleted_at_dt.strftime("%Y-%m-%dT%H-%M-%SZ")
    folder_name = f"{original_name}_{deleted_at}{folder_suffix}"
    return {
        "folder_name": folder_name,
        "original_name": original_name,
        "deleted_at": deleted_at,
        "path": f"/trash/{folder_name}",
    }


def test_green_when_nothing_matches_any_fixture_prefix() -> None:
    result = classify_leak_audit(
        ["my_own_project", "workmgr-prod"],
        [_trash_item("someone_elses_backup", hours_ago=100)],
        now=_NOW,
    )
    assert result.status == "GREEN"
    assert result.live_stray_names == ()
    assert result.aged_trash_folder_names == ()


def test_red_on_any_live_fixture_prefix_project_regardless_of_age() -> None:
    result = classify_leak_audit(
        ["pipeline_live_8ad3bce6", "unrelated_project"],
        [],
        now=_NOW,
    )
    assert result.status == "RED"
    assert result.live_stray_names == ("pipeline_live_8ad3bce6",)
    assert "1 live stray" in result.reason
    assert "pipeline_live_" in result.reason


def test_red_on_verify_vecbatchcap_live_stray() -> None:
    """Regression pin for the exact live strays the researcher observed."""
    result = classify_leak_audit(
        ["verify_vecbatchcap_adf7483f"],
        [],
        now=_NOW,
    )
    assert result.status == "RED"
    assert result.live_stray_names == ("verify_vecbatchcap_adf7483f",)


def test_green_when_trash_entry_is_within_grace_window() -> None:
    """A fixture-prefix trash entry younger than 2h is tolerated (run still in flight)."""
    result = classify_leak_audit(
        [],
        [_trash_item("verify_lock_original_deadbeef", hours_ago=0.5)],
        now=_NOW,
    )
    assert result.status == "GREEN"


def test_red_when_same_trash_entry_ages_past_the_grace_window() -> None:
    """The identical entry, now older than 2h, flips to RED."""
    result = classify_leak_audit(
        [],
        [_trash_item("verify_lock_original_deadbeef", hours_ago=3)],
        now=_NOW,
    )
    assert result.status == "RED"
    assert len(result.aged_trash_folder_names) == 1
    assert "verify_lock_" in result.reason


def test_red_boundary_uses_strictly_greater_than_max_age() -> None:
    result_at_boundary = classify_leak_audit(
        [], [_trash_item("verify_probe", hours_ago=2.0)], now=_NOW
    )
    result_just_past = classify_leak_audit(
        [], [_trash_item("verify_probe", hours_ago=2.0001)], now=_NOW
    )
    assert result_at_boundary.status == "GREEN"
    assert result_just_past.status == "RED"


def test_verify_editor_prefix_is_always_excluded_even_though_it_matches_generic_verify() -> None:
    """ai_editor's own live fixtures must never be flagged (another project's data)."""
    result = classify_leak_audit(
        ["verify_editor_some_fixture"],
        [_trash_item("verify_editor_another_fixture", hours_ago=100)],
        now=_NOW,
    )
    assert result.status == "GREEN"
    assert result.live_stray_names == ()
    assert result.aged_trash_folder_names == ()


def test_unparsable_deleted_at_is_treated_as_unknown_age_not_old() -> None:
    """A parse failure must never manufacture a false RED."""
    item = {
        "folder_name": "verify_probe_garbage",
        "original_name": "verify_probe",
        "deleted_at": "not-a-timestamp",
    }
    result = classify_leak_audit([], [item], now=_NOW)
    assert result.status == "GREEN"


def test_missing_deleted_at_is_treated_as_unknown_age_not_old() -> None:
    item = {"folder_name": "verify_probe_x", "original_name": "verify_probe"}
    result = classify_leak_audit([], [item], now=_NOW)
    assert result.status == "GREEN"


def test_reason_reports_per_bucket_counts_for_multiple_matches() -> None:
    result = classify_leak_audit(
        ["pipeline_live_aaa", "pipeline_live_bbb", "verify_worker_activity_ccc"],
        [
            _trash_item("verify_lock_original_1", hours_ago=5),
            _trash_item("verify_lock_original_2", hours_ago=6),
            _trash_item("verify_trashrestore_3", hours_ago=10),
        ],
        now=_NOW,
    )
    assert result.status == "RED"
    assert len(result.live_stray_names) == 3
    assert len(result.aged_trash_folder_names) == 3
    assert "3 live stray" in result.reason
    assert "3 fixture trash entries" in result.reason


def test_generic_verify_prefix_catches_suites_without_a_dedicated_bucket() -> None:
    """A fixture prefix not explicitly enumerated still falls into the generic bucket."""
    result = classify_leak_audit(["verify_live_9f9f9f9f"], [], now=_NOW)
    assert result.status == "RED"
    assert result.live_stray_names == ("verify_live_9f9f9f9f",)
