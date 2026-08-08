"""
Locks must not outlive the session that took them (TODO d75d5e9a).

Reported via ai-editor bug 3d1dd9ab (2026-07-23): an ai-editor container restart
orphaned its Code Analysis session, and the exclusive file lock that session held
survived indefinitely. Every later open of that path from a new session failed,
and no client could fix it — clients cannot identify a lock's holder, cannot
release another session's lock, and the FILE_LOCKED error said nothing beyond
"locked". The only cure was a manual session_delete.

``client_sessions.last_active_at`` already recorded liveness; nothing acted on it.
These tests pin the two halves that now do: a sweep that releases what a dead
session still holds, and a conflict response that names the holder and its idle
time so a client can tell a live peer from a corpse.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

import pytest

from code_analysis.core.constants import (
    CLIENT_SESSION_SWEEP_INTERVAL_SECONDS_MAX,
    CLIENT_SESSION_SWEEP_INTERVAL_SECONDS_MIN,
    CLIENT_SESSION_TTL_SECONDS_MAX,
    CLIENT_SESSION_TTL_SECONDS_MIN,
    DEFAULT_CLIENT_SESSION_TTL_SECONDS,
)
from code_analysis.core.session_lock_reaper import (
    SECONDS_PER_DAY,
    describe_lock_holder,
    load_session_reaper_policy,
    sweep_dead_sessions,
)

_NOW_JULIAN = 2_460_100.0


class _StubDatabase:
    """A database whose client_sessions rows and delete behaviour are scripted."""

    def __init__(self, sessions: list[dict[str, Any]]) -> None:
        """Store the session rows this stub will serve."""
        self.sessions = {str(row["session_id"]): dict(row) for row in sessions}
        self.deleted: list[tuple[str, bool]] = []
        self.delete_failures: set[str] = set()
        self.lock_counts: dict[str, int] = {}

    # -- the surface the reaper actually touches ---------------------------

    def execute(self, sql: str, params: tuple = ()) -> dict[str, Any]:
        """Serve the handful of statements the reaper path issues."""
        lowered = " ".join(sql.split()).lower()
        if "julianday('now') as now_julian" in lowered:
            return {"data": [{"now_julian": _NOW_JULIAN}]}
        if "from client_sessions" in lowered and "julianday('now') -" in lowered:
            threshold_days = float(params[0])
            rows = [
                dict(row)
                for row in self.sessions.values()
                if _NOW_JULIAN - float(row["last_active_at"]) > threshold_days
            ]
            rows.sort(key=lambda row: row["last_active_at"])
            return {"data": rows}
        if "from client_sessions" in lowered and "where session_id" in lowered:
            row = self.sessions.get(str(params[0]))
            return {"data": [dict(row)] if row else []}
        if "from client_sessions" in lowered:
            return {"data": [dict(row) for row in self.sessions.values()]}
        if "count(*)" in lowered and "session_file_locks" in lowered:
            return {"data": [{"cnt": self.lock_counts.get(str(params[0]), 0)}]}
        return {"data": []}


def _session(session_id: str, *, idle_seconds: float, comment: str = "") -> dict:
    """Build a client_sessions row that has been idle for a given time."""
    return {
        "session_id": session_id,
        "comment": comment,
        "created_at": _NOW_JULIAN - 1.0,
        "last_active_at": _NOW_JULIAN - (idle_seconds / SECONDS_PER_DAY),
    }


@pytest.fixture()
def scripted_delete(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, bool]]:
    """Record delete_client_session calls and fake their outcome."""
    calls: list[tuple[str, bool]] = []

    def _fake_delete(database: Any, session_id: str, force: bool = False) -> dict:
        calls.append((session_id, force))
        if session_id in getattr(database, "delete_failures", set()):
            raise RuntimeError("row is wedged")
        return {
            "session_id": session_id,
            "deleted": True,
            "released_lock_count": database.lock_counts.get(session_id, 0),
            "released_subordinate_count": 0,
            "released_advisory_lease_count": database.lock_counts.get(session_id, 0),
        }

    monkeypatch.setattr(
        "code_analysis.core.client_sessions.delete_client_session", _fake_delete
    )
    return calls


def test_a_session_idle_past_the_ttl_gives_up_its_locks(
    scripted_delete: list[tuple[str, bool]],
) -> None:
    """The reported failure: a dead client's lock is finally released."""
    database = _StubDatabase([_session("dead", idle_seconds=7200, comment="ai-editor")])
    database.lock_counts["dead"] = 2

    result = sweep_dead_sessions(database, ttl_seconds=3600)

    assert [item.session_id for item in result.reaped] == ["dead"]
    assert result.released_lock_total == 2
    assert scripted_delete == [("dead", True)], "must force-release, not just ask"
    assert result.reaped[0].idle_seconds == pytest.approx(7200, abs=1)


def test_a_live_session_is_left_alone(scripted_delete: list[tuple[str, bool]]) -> None:
    """Releasing a live editor's lock would be worse than the bug being fixed."""
    database = _StubDatabase([_session("live", idle_seconds=30)])
    database.lock_counts["live"] = 1

    result = sweep_dead_sessions(database, ttl_seconds=3600)

    assert result.reaped == ()
    assert scripted_delete == []


def test_one_wedged_session_does_not_abort_the_sweep(
    scripted_delete: list[tuple[str, bool]],
) -> None:
    """The whole point of the sweep is to unstick the others."""
    database = _StubDatabase(
        [
            _session("wedged", idle_seconds=9000),
            _session("also-dead", idle_seconds=8000),
        ]
    )
    database.delete_failures.add("wedged")
    database.lock_counts["also-dead"] = 1

    result = sweep_dead_sessions(database, ttl_seconds=3600)

    assert [item.session_id for item in result.reaped] == ["also-dead"]
    assert [sid for sid, _err in result.failed] == ["wedged"]
    assert "row is wedged" in result.failed[0][1]


def test_scoping_the_sweep_spares_every_other_dead_session(
    scripted_delete: list[tuple[str, bool]],
) -> None:
    """An operator releasing one known-dead session must not sweep the server."""
    database = _StubDatabase(
        [
            _session("target", idle_seconds=9000),
            _session("someone-elses", idle_seconds=9000),
        ]
    )

    result = sweep_dead_sessions(
        database, ttl_seconds=3600, only_session_ids=["target"]
    )

    assert [item.session_id for item in result.reaped] == ["target"]
    assert scripted_delete == [("target", True)]


def test_scoping_still_respects_the_idle_test(
    scripted_delete: list[tuple[str, bool]],
) -> None:
    """Naming a session asks for it IF dead; it never forces a live one open."""
    database = _StubDatabase([_session("named-but-live", idle_seconds=5)])

    result = sweep_dead_sessions(
        database, ttl_seconds=3600, only_session_ids=["named-but-live"]
    )

    assert result.reaped == ()
    assert scripted_delete == []


def test_a_non_positive_ttl_is_refused() -> None:
    """A zero TTL would reap every session, including the caller's."""
    database = _StubDatabase([])

    with pytest.raises(ValueError, match="ttl_seconds must be positive"):
        sweep_dead_sessions(database, ttl_seconds=0)


def test_the_sweep_report_is_serialisable() -> None:
    """The command returns this verbatim; it must survive JSON."""
    import json

    database = _StubDatabase([])
    result = sweep_dead_sessions(database, ttl_seconds=3600)

    payload = json.dumps(result.as_dict())

    assert '"reaped_session_count": 0' in payload
    assert '"ttl_seconds": 3600' in payload


# --- the conflict payload ---------------------------------------------------


def test_the_conflict_payload_names_the_holder_and_its_idle_time() -> None:
    """Clients could see neither who held the lock nor whether it was alive."""
    database = _StubDatabase([_session("holder", idle_seconds=120, comment="peer")])

    details = describe_lock_holder(database, "holder", ttl_seconds=3600)

    assert details["holder_session_id"] == "holder"
    assert details["holder_exists"] is True
    assert details["holder_comment"] == "peer"
    assert details["holder_idle_seconds"] == pytest.approx(120, abs=1)
    assert details["holder_expired"] is False
    assert details["ttl_seconds"] == 3600


def test_the_conflict_payload_flags_an_already_expired_holder() -> None:
    """ "Wait" and "this will clear itself" are different answers for a client."""
    database = _StubDatabase([_session("corpse", idle_seconds=9000)])

    details = describe_lock_holder(database, "corpse", ttl_seconds=3600)

    assert details["holder_expired"] is True


def test_a_vanished_holder_is_reported_not_invented() -> None:
    """The lock row can outlive its session row; say so rather than guessing."""
    database = _StubDatabase([])

    details = describe_lock_holder(database, "gone", ttl_seconds=3600)

    assert details["holder_exists"] is False
    assert details["holder_idle_seconds"] is None


def test_a_broken_diagnostic_never_breaks_the_conflict_response() -> None:
    """The caller still needs its FILE_LOCKED answer even if lookup fails."""

    class _BrokenDatabase:
        def execute(self, sql: str, params: tuple = ()) -> dict:
            raise RuntimeError("connection gone")

    details = describe_lock_holder(_BrokenDatabase(), "holder", ttl_seconds=3600)

    assert details["holder_session_id"] == "holder"
    assert details["holder_exists"] is False


# --- policy loading ---------------------------------------------------------


def test_the_policy_defaults_are_used_without_configuration() -> None:
    """A server that configures nothing still reaps dead sessions."""
    policy = load_session_reaper_policy({})

    assert policy.ttl_seconds == DEFAULT_CLIENT_SESSION_TTL_SECONDS
    assert policy.enabled is True


def test_configured_values_are_honoured() -> None:
    """Operators can tune both the threshold and the cadence."""
    policy = load_session_reaper_policy(
        {"code_analysis": {"client_session": {"ttl_seconds": 900, "poll_interval": 60}}}
    )

    assert policy.ttl_seconds == 900
    assert policy.sweep_interval_seconds == 60


def test_out_of_range_values_are_clamped_not_rejected() -> None:
    """A typo must not stop the server or silently disable lock recovery."""
    policy = load_session_reaper_policy(
        {
            "code_analysis": {
                "client_session": {"ttl_seconds": 1, "poll_interval": 999_999}
            }
        }
    )

    assert policy.ttl_seconds == CLIENT_SESSION_TTL_SECONDS_MIN
    assert policy.sweep_interval_seconds == CLIENT_SESSION_SWEEP_INTERVAL_SECONDS_MAX


def test_unparsable_values_fall_back_to_the_defaults() -> None:
    """Garbage in configuration is not a reason to stop reaping."""
    policy = load_session_reaper_policy(
        {"code_analysis": {"client_session": {"ttl_seconds": "soon"}}}
    )

    assert policy.ttl_seconds == DEFAULT_CLIENT_SESSION_TTL_SECONDS
    assert CLIENT_SESSION_TTL_SECONDS_MIN <= policy.ttl_seconds
    assert policy.ttl_seconds <= CLIENT_SESSION_TTL_SECONDS_MAX


def test_the_reaper_can_be_turned_off_explicitly() -> None:
    """Disabling is a flag, not a TTL nobody will ever reach."""
    policy = load_session_reaper_policy(
        {"code_analysis": {"client_session": {"reap_dead_sessions": False}}}
    )

    assert policy.enabled is False
    assert CLIENT_SESSION_SWEEP_INTERVAL_SECONDS_MIN <= policy.sweep_interval_seconds
