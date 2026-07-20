"""
Driver-leaf regression: code_analysis.core.database.projects.get_project falls
back to an unscoped global-by-id lookup when the server_instance_id-scoped
lookup misses.

This is the leaf function bound onto ``CodeDatabase`` (shared by both the
SQLite and Postgres drivers - see ``core/database/__init__.py``'s
``_add_functions_as_methods``), so fixing it here keeps both backends
consistent per the project's driver-chain invariant. Mirrors
``DatabaseClient.get_project``'s ``_project_row_by_id_global`` fallback
(client_api_projects.py) - see tests/test_insert_project_row_global_id.py.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

from code_analysis.core.database import projects as projects_mod

_SID = "server-current"


class _FakeDriverSelf:
    """Minimal ``self`` stand-in for the ``CodeDatabase``-bound leaf function."""

    def __init__(self, rows_by_sql_marker: Dict[str, Optional[Dict[str, Any]]]) -> None:
        """Store canned rows keyed by a substring marker found in the SQL."""
        self._rows_by_sql_marker = rows_by_sql_marker
        self.fetchone_calls: List[Tuple[str, Tuple[Any, ...]]] = []

    def _fetchone(self, sql: str, params: Tuple[Any, ...]) -> Optional[Dict[str, Any]]:
        """Return the canned row whose marker matches, else None."""
        self.fetchone_calls.append((sql, params))
        for marker, row in self._rows_by_sql_marker.items():
            if marker in sql:
                return row
        return None


@patch(
    "code_analysis.core.database.projects.sql_projects_server_instance_filter",
    return_value=("p.server_instance_id = ?", (_SID,)),
)
@patch(
    "code_analysis.core.database.projects.enrich_project_dict_resolve_root_path",
    side_effect=lambda row, _self: dict(row),
)
def test_get_project_scoped_hit_never_touches_global_fallback(
    _enrich_mock: Any, _filter_mock: Any
) -> None:
    """Scoped lookup hits -> returned directly, no second (global) query issued."""
    scoped_row = {"id": "pid-1", "server_instance_id": _SID, "root_path": "proj1"}
    fake_self = _FakeDriverSelf(
        {"WHERE p.server_instance_id = ? AND p.id = ?": scoped_row}
    )

    result = projects_mod.get_project(fake_self, "pid-1")

    assert result is not None
    assert result["id"] == "pid-1"
    assert len(fake_self.fetchone_calls) == 1


@patch(
    "code_analysis.core.database.projects.sql_projects_server_instance_filter",
    return_value=("p.server_instance_id = ?", (_SID,)),
)
@patch(
    "code_analysis.core.database.projects.enrich_project_dict_resolve_root_path",
    side_effect=lambda row, _self: dict(row),
)
def test_get_project_scoped_miss_falls_back_to_unscoped_global_lookup(
    _enrich_mock: Any, _filter_mock: Any
) -> None:
    """Scoped select misses (row under a different/orphan sid) -> global fallback finds it."""
    global_row = {
        "id": "pid-orphan",
        "server_instance_id": "server-other-orphan",
        "root_path": "orphan_proj",
    }
    fake_self = _FakeDriverSelf(
        {
            "WHERE p.server_instance_id = ? AND p.id = ?": None,
            "WHERE p.id = ?": global_row,
        }
    )

    result = projects_mod.get_project(fake_self, "pid-orphan")

    assert result is not None
    assert result["id"] == "pid-orphan"
    assert result["server_instance_id"] == "server-other-orphan"
    # scoped attempt, then the unscoped global-by-id fallback
    assert len(fake_self.fetchone_calls) == 2
    assert fake_self.fetchone_calls[1][1] == ("pid-orphan",)


@patch(
    "code_analysis.core.database.projects.sql_projects_server_instance_filter",
    return_value=("p.server_instance_id = ?", (_SID,)),
)
def test_get_project_neither_scoped_nor_global_returns_none(
    _filter_mock: Any,
) -> None:
    """Genuinely nonexistent project_id -> None after both lookups miss."""
    fake_self = _FakeDriverSelf({})

    result = projects_mod.get_project(fake_self, "does-not-exist")

    assert result is None
    assert len(fake_self.fetchone_calls) == 2
