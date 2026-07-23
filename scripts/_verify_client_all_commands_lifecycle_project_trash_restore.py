"""
Live pipeline check: project trash + restore round trip (bug c8ad0c21).

Exercises the exact end-to-end path that used to raise ``PermissionError``:
a project moved into trash and then restored via ``restore_project_from_trash``
must land back at its original **absolute** ``root_path`` (the fix routes the
lookup through the ``get_project`` domain function instead of feeding the raw,
watch-relative ``projects.root_path`` segment straight to ``shutil.move``).

Uses its own disposable project (created/destroyed entirely within this
check) rather than the shared sweep-wide :class:`FixtureContext` project,
since ``project_set_mark_del`` is destructive and the shared fixture must
survive for the rest of the command sweep (see
``_verify_client_all_commands_catalog.BUCKET_B_REASONS['project_set_mark_del']``).
Only ``fixtures.watch_dir_id`` is reused (already resolved once via
``list_watch_dirs`` during sweep-wide fixture setup).

Flow: create_project -> seed one file via a session upload ->
project_set_mark_del(delete_from_disk=True) (soft-delete: trash + DB rows
kept) -> list_trashed_projects (capture folder_name by matching
original_name) -> restore_project_from_trash -> assert success, the project
reappears in list_projects, and the seeded file reappears in
list_project_files (the workstation running this verifier never has direct
filesystem access to the server-side project root, so "file on disk" is
confirmed through the API instead of a local stat). Always attempts a final
purge (mark-del full clear + permanently_delete_from_trash) in a ``finally``
block so a failed assertion never leaves the disposable project behind.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status, truncate
from _verify_client_all_commands_fixtures import FixtureContext

CHECK_NAME = "project_trash_restore_roundtrip"

_FIXTURE_FILE_RELPATH = "restore_check.py"
_FIXTURE_FILE_CONTENT = (
    '"""Fixture file for the project_trash_restore_roundtrip check."""\n'
)


def _outcome(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map every lifecycle returns.

    Args:
        status: Outcome status for this check.
        reason: Human-readable explanation.

    Returns:
        ``{CHECK_NAME: CommandOutcome(...)}``.
    """
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}


def _unwrap(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Unwrap a successful ``{"success": True, "data": {...}}`` envelope.

    Args:
        resp: Raw JSON-RPC command response.

    Returns:
        The ``data`` payload.

    Raises:
        RuntimeError: If ``resp`` does not report success.
    """
    if resp.get("success") is not True:
        raise RuntimeError(resp.get("error") or resp)
    data = resp.get("data")
    return data if isinstance(data, dict) else resp


async def _find_trash_folder_name(
    client: CodeAnalysisAsyncClient, project_name: str
) -> Optional[str]:
    """Look up the trash folder name whose parsed ``original_name`` matches.

    Args:
        client: Connected async client.
        project_name: Directory/display name of the disposable project.

    Returns:
        The trash folder name, or ``None`` if no matching entry was found.
    """
    resp = await client.call_validated("list_trashed_projects", {})
    data = _unwrap(resp)
    for item in data.get("items") or []:
        if isinstance(item, dict) and item.get("original_name") == project_name:
            folder_name = item.get("folder_name")
            return str(folder_name) if folder_name else None
    return None


async def _cleanup(
    client: CodeAnalysisAsyncClient, project_id: str, project_name: str
) -> None:
    """Best-effort final purge of the disposable project this check created.

    Runs a full mark-del (``delete_from_disk=False`` -> trash + DB clear),
    then resolves and permanently deletes the trash folder. Never raises --
    logs a WARN on any failure, mirroring
    ``_verify_client_all_commands_teardown.teardown_fixtures``.

    Args:
        client: Connected async client.
        project_id: UUID4 of the disposable project to purge.
        project_name: Directory/display name of the disposable project.
    """
    try:
        await client.call_validated(
            "project_set_mark_del",
            {"project_id": project_id, "delete_from_disk": False},
        )
    except Exception as exc:  # noqa: BLE001 - best-effort cleanup
        print(
            "WARN  project_trash_restore_roundtrip cleanup: "
            f"project_set_mark_del raised: {exc!r}"
        )
        return

    try:
        folder_name = await _find_trash_folder_name(client, project_name)
        if not folder_name:
            print(
                "WARN  project_trash_restore_roundtrip cleanup: could not "
                f"resolve trash_folder_name for {project_name!r}; project "
                "remains in trash (safe holding area)."
            )
            return
        purge_resp = await client.call_validated(
            "permanently_delete_from_trash", {"trash_folder_name": folder_name}
        )
        if not purge_resp.get("success"):
            print(
                "WARN  project_trash_restore_roundtrip cleanup: "
                f"permanently_delete_from_trash failed: {purge_resp.get('error')!r}"
            )
    except Exception as exc:  # noqa: BLE001 - best-effort cleanup
        print(
            f"WARN  project_trash_restore_roundtrip cleanup: purge raised: {exc!r}"
        )


async def run_project_trash_restore_roundtrip_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Trash and restore a disposable project; assert the round trip lands absolute.

    Args:
        client: Connected async client.
        fixtures: The sweep-wide fixture context (only ``watch_dir_id`` reused).

    Returns:
        ``{CHECK_NAME: outcome}``, merged into the lifecycle-precomputed
        outcomes table like every other lifecycle module returns.
    """
    project_name = f"verify_trashrestore_{uuid.uuid4().hex[:8]}"
    project_id: Optional[str] = None
    try:
        create_resp = await client.call_validated(
            "create_project",
            {
                "watch_dir_id": fixtures.watch_dir_id,
                "project_name": project_name,
                "description": (
                    "Disposable fixture for project_trash_restore_roundtrip check"
                ),
                "create_venv": False,
                "apply_template": False,
            },
        )
        create_data = _unwrap(create_resp)
        project_id = create_data.get("project_id")
        if not project_id:
            return _outcome(
                Status.FAILED,
                truncate(f"create_project missing project_id: {create_data!r}"),
            )

        session_resp = await client.call_validated(
            "session_create",
            {"comment": "project_trash_restore_roundtrip check"},
        )
        session_data = _unwrap(session_resp)
        session_id = str(session_data["session_id"])
        await client.file_sessions.upload_new(
            session_id,
            _FIXTURE_FILE_CONTENT.encode("utf-8"),
            project_id,
            _FIXTURE_FILE_RELPATH,
        )
        try:
            await client.call_validated(
                "session_delete", {"session_id": session_id, "force": True}
            )
        except Exception:  # noqa: BLE001 - not the point of this check
            pass

        mark_resp = await client.call_validated(
            "project_set_mark_del",
            {"project_id": project_id, "delete_from_disk": True},
        )
        _unwrap(mark_resp)

        folder_name = await _find_trash_folder_name(client, project_name)
        if not folder_name:
            return _outcome(
                Status.FAILED,
                truncate(
                    f"list_trashed_projects has no entry for {project_name!r} "
                    f"after project_set_mark_del (project_id={project_id})"
                ),
            )

        restore_resp = await client.call_validated(
            "restore_project_from_trash", {"trash_folder_name": folder_name}
        )
        if not restore_resp.get("success"):
            return _outcome(
                Status.FAILED,
                truncate(
                    f"restore_project_from_trash failed: {restore_resp.get('error')!r}"
                ),
            )
        restore_data = restore_resp.get("data") or {}
        restored_root = restore_data.get("root_path")
        if not restored_root or not str(restored_root).startswith("/"):
            return _outcome(
                Status.FAILED,
                truncate(
                    "restore_project_from_trash returned a non-absolute "
                    f"root_path: {restored_root!r} -- the exact regression "
                    "bug c8ad0c21 fixed"
                ),
            )

        projects_data = _unwrap(
            await client.call_validated(
                "list_projects", {"include_deleted": False}
            )
        )
        listed_ids = {
            str(p.get("id"))
            for p in (projects_data.get("items") or projects_data.get("projects") or [])
            if isinstance(p, dict)
        }
        if project_id not in listed_ids:
            return _outcome(
                Status.FAILED,
                truncate(
                    f"restored project {project_id} not present in "
                    f"list_projects (root_path={restored_root!r})"
                ),
            )

        files_data = _unwrap(
            await client.call_validated(
                "list_project_files", {"project_id": project_id}
            )
        )
        relpaths = {
            f.get("relative_path")
            for f in (files_data.get("items") or files_data.get("files") or [])
            if isinstance(f, dict)
        }
        if _FIXTURE_FILE_RELPATH not in relpaths:
            return _outcome(
                Status.FAILED,
                truncate(
                    f"seeded file {_FIXTURE_FILE_RELPATH!r} not present after "
                    f"restore (project_id={project_id}, files={relpaths!r})"
                ),
            )

        return _outcome(
            Status.EXECUTED_OK,
            f"project {project_id} ({project_name}) trashed and restored to "
            f"absolute root_path={restored_root!r}; project and file listings "
            "both confirm the round trip",
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return _outcome(Status.FAILED, truncate(repr(exc)))
    finally:
        if project_id:
            await _cleanup(client, project_id, project_name)
