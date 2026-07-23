"""
Regression tests for ``resolve_project_root_absolute_str`` with multiple
registered watch directories and ``require_exists=False`` (bug c8ad0c21,
iteration 3: restored-from-trash project invisible in ``list_projects``).

Live diagnosis on a throwaway project (2026-07-23) showed
``restore_project_from_trash`` moving the folder to the WRONG watch
directory when more than one ``watch_dir_paths`` row is registered for the
current ``server_instance_id``: the project was created under
``watch_dir_id=a0561298-...`` but restored under
``watch_dir_id=550e8400-...`` -- the lexicographically-first row from
``fetch_all_watch_dir_absolute_paths`` (``ORDER BY watch_dir_id``).

Root cause: inside ``resolve_project_root_absolute_str``, the ``primary``
candidate is computed correctly straight from the caller-supplied, trusted
``watch_dir_id`` (via ``resolve_projects_root_path_row_to_absolute_str``),
but was still gated behind ``_projectid_matches(Path(primary), project_id)``
even when ``require_exists=False``. Since the restore target does not exist
on disk yet at resolution time, ``_projectid_matches`` always returns False
(nothing to read), so the correct ``primary`` was discarded every time in
favor of the ambiguous multi-watch-dir folder-name fallback loop -- which
does not filter by ``watch_dir_id`` at all and, once none of its candidates
pass the (impossible-to-satisfy) projectid check either, falls back to
``unique[0]``: an arbitrary DB-order pick, not necessarily the project's
real watch directory.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from code_analysis.core.project_root_path import resolve_project_root_absolute_str


def _fake_driver_multi_watch_dir(rows: list[tuple[str, str]]) -> MagicMock:
    """Return a fake driver answering ``watch_dir_paths`` lookups for ``rows``.

    ``rows`` is a list of ``(watch_dir_id, absolute_path)`` pairs, as if
    multiple watch directories were registered for the current
    ``server_instance_id`` -- the exact shape ``fetch_watch_dir_absolute_path``
    (single-row ``LIMIT 1`` lookup) and ``fetch_all_watch_dir_absolute_paths``
    (full-table scan, ``ORDER BY watch_dir_id``) read from live.
    """

    def _execute(sql: str, params: tuple = (), **_kwargs: object) -> Dict[str, Any]:
        text = " ".join(sql.split())
        if "FROM watch_dir_paths" in text and "LIMIT 1" in text:
            wid = str(params[1]) if params and len(params) >= 2 else None
            for row_wid, row_path in rows:
                if row_wid == wid:
                    return {"data": [{"absolute_path": row_path}]}
            return {"data": []}
        if "FROM watch_dir_paths" in text:
            ordered = sorted(rows, key=lambda r: r[0])
            return {
                "data": [
                    {"watch_dir_id": wid, "absolute_path": path}
                    for wid, path in ordered
                ]
            }
        return {"data": []}

    db = MagicMock()
    db.execute = MagicMock(side_effect=_execute)
    # See test_restore_project_from_trash_absolute_destination.py: a bare
    # MagicMock auto-vivifies _fetchone/_fetchall as truthy non-dict-returning
    # callables that would short-circuit resolution before `execute` runs.
    db._fetchone = None
    db._fetchall = None
    return db


@pytest.mark.asyncio
async def test_resolve_picks_correct_watch_dir_when_multiple_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """require_exists=False must resolve under the project's OWN watch_dir_id,
    not an arbitrary lexicographically-first registered watch directory.

    Reproduces the live restore-from-trash symptom directly: two watch dirs
    are registered ("550e8400-..." sorts before "a0561298-..."), the
    project's real home is the SECOND one, and the target folder does not
    exist on disk yet (pre-move resolution, same as restore_project_from_trash
    calls it). Before the fix this returned the "550e8400-..." destination
    (``unique[0]`` from the ambiguous fallback) instead of the project's
    actual watch directory.
    """
    monkeypatch.setenv("CODE_ANALYSIS_SERVER_INSTANCE_ID", "test-instance")

    watch_a = tmp_path / "watch_550e8400"
    watch_b = tmp_path / "watch_a0561298"
    watch_a.mkdir()
    watch_b.mkdir()

    project_id = "bd125963-0865-4aa4-bd90-b97f5fde12d9"
    project_name = "c8ad0c21_throwaway"
    correct_watch_dir_id = "a0561298-53a9-41da-bb9c-bd1cd98b1ddf"

    db = _fake_driver_multi_watch_dir(
        [
            ("550e8400-e29b-41d4-a716-446655440001", str(watch_a)),
            (correct_watch_dir_id, str(watch_b)),
        ]
    )

    # Target folder does not exist on disk yet -- exactly the state at
    # restore-resolution time, before shutil.move() runs.
    resolved = resolve_project_root_absolute_str(
        project_id=project_id,
        root_path_stored=project_name,
        watch_dir_id=correct_watch_dir_id,
        project_name=project_name,
        database=db,
        require_exists=False,
    )

    expected = str((watch_b / project_name).resolve())
    assert resolved == expected, (
        f"resolved to {resolved!r}, expected the project's own watch_dir "
        f"({correct_watch_dir_id}) destination {expected!r} -- got the "
        "ambiguous ORDER-BY-watch_dir_id first candidate instead"
    )


@pytest.mark.asyncio
async def test_resolve_still_validates_projectid_when_primary_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """require_exists=False must NOT blindly trust a primary path that
    already exists on disk but belongs to a different project (defensive:
    the projectid-match guard still applies once there is something on disk
    to check against)."""
    monkeypatch.setenv("CODE_ANALYSIS_SERVER_INSTANCE_ID", "test-instance")

    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    occupied = watch_dir / "taken"
    occupied.mkdir()
    (occupied / "projectid").write_text(
        '{"id": "11111111-1111-4111-8111-111111111111", "description": "other"}'
    )

    watch_dir_id = "550e8400-e29b-41d4-a716-446655440001"
    db = _fake_driver_multi_watch_dir([(watch_dir_id, str(watch_dir))])

    resolved = resolve_project_root_absolute_str(
        project_id="22222222-2222-4222-8222-222222222222",
        root_path_stored="taken",
        watch_dir_id=watch_dir_id,
        project_name="taken",
        database=db,
        require_exists=False,
    )

    # primary ("taken") exists but its projectid belongs to a different
    # project -> must not be trusted as-is; no other candidate matches
    # either, so resolution fails (empty string), never a silent collision.
    assert resolved == ""
