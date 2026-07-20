"""
Disposable-project teardown for the live-server all-commands verifier.

Closes the sweep-wide session and purges the disposable project created by
``_verify_client_all_commands_fixtures.seed_fixtures``, or — per the
operator's ``--keep-project`` flag — leaves it in place for manual inspection.
Trash purge resolves the disposable project's trash folder name via a
read-only ``list_trashed_projects`` lookup (always safe to call) and passes it
straight to ``permanently_delete_from_trash``, which takes ``trash_folder_name``
(a direct child of ``trash_dir``), not ``project_id``. A purge failure, or a
folder name that fails to resolve, is logged as a WARN rather than an abort:
by that point ``project_set_mark_del`` has already succeeded, so the project
is out of the DB either way, and trash is a safe holding area for manual (or
``clear_trash``) cleanup later.

``project_set_mark_del`` teardown is idempotent: if the project is already
absent (a "not found in database" rejection, see ``_ALREADY_ABSENT_MARKER``),
that is logged and treated as a successful delete rather than an abort — this
is the sole caller of ``project_set_mark_del`` in the whole verifier (see
``_verify_client_all_commands_catalog.BUCKET_B_REASONS``), so an "already
absent" outcome only happens on a re-run against a stale fixture or a
teardown retry, never mid-sweep. Any other failure still aborts loudly.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Optional

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import schema_has_project_id
from _verify_client_all_commands_fixtures import FixtureContext

# Same marker _verify_client_all_commands_fixtures_registration.py polls for:
# the server's rejection text when a project_id no longer has a DB row. Used
# here to make project_set_mark_del teardown idempotent — if some earlier
# step already deleted the disposable project, teardown must not abort.
_ALREADY_ABSENT_MARKER = "not found in database"


async def _lookup_trash_folder_name(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Optional[str]:
    """Best-effort, read-only lookup of the disposable project's trash folder name.

    Calls ``list_trashed_projects`` (safe: read-only, no purge) and returns the
    ``folder_name`` of the entry whose parsed ``original_name`` matches the
    disposable project's directory name, for a more actionable teardown
    message. Never raises — returns ``None`` on any failure.

    Args:
        client: Connected async client.
        fixtures: Fixture context identifying the disposable project by name.

    Returns:
        The trash folder name, or ``None`` if it could not be resolved.
    """
    try:
        resp = await client.call_validated("list_trashed_projects", {})
    except Exception:  # noqa: BLE001 - purely cosmetic lookup for the abort message
        return None
    if not resp.get("success"):
        return None
    data = resp.get("data") or {}
    for item in data.get("items") or []:
        if (
            isinstance(item, dict)
            and item.get("original_name") == fixtures.project_name
        ):
            folder_name = item.get("folder_name")
            return str(folder_name) if folder_name else None
    return None


async def teardown_fixtures(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext, *, keep_project: bool
) -> bool:
    """Close the session and purge the disposable project (unless kept).

    Applies the project_id-in-schema scoping gate to ``project_set_mark_del``
    before calling it, and aborts loudly instead of guessing if it fails the
    gate. ``project_set_mark_del`` itself is idempotent to an "already
    absent" rejection (see module docstring) — that case is logged and
    treated as success, not an abort. ``permanently_delete_from_trash`` is
    scoped by ``trash_folder_name`` (resolved via ``list_trashed_projects``,
    not a project_id-schema gate); its failure, or an unresolved folder name,
    is a WARN, not an abort — the project is already out of the DB by then.

    Args:
        client: Connected async client.
        fixtures: Fixture context produced by ``seed_fixtures`` (its
            ``project_id`` reflects ``change_project_id`` if that command ran
            and succeeded during the sweep).
        keep_project: If True, skip project purge and print the project id
            for manual operator cleanup.

    Returns:
        True if teardown completed cleanly (or was explicitly skipped via
        ``keep_project``), including when ``project_set_mark_del`` succeeded
        (or was already-absent) but the trash purge only WARNed; False if
        ``session_delete`` failed or ``project_set_mark_del`` failed/aborted.
    """
    ok = True

    if fixtures.session_id:
        try:
            # force=true: fixtures.session_id is used generically across the
            # sweep (e.g. as the session_id fixture value for whichever
            # command's coverage exercises session_open_file), so a file lock
            # legitimately outliving that coverage is expected here, not a
            # teardown defect — session_delete must not reject on it.
            resp = await client.call_validated(
                "session_delete", {"session_id": fixtures.session_id, "force": True}
            )
            if not resp.get("success"):
                print(f"WARN  teardown: session_delete failed: {resp.get('error')!r}")
                ok = False
        except Exception as exc:
            print(f"WARN  teardown: session_delete raised: {exc!r}")
            ok = False

    if keep_project:
        print(
            f"KEEP  project_id={fixtures.project_id} project_name={fixtures.project_name} "
            f"project_root={fixtures.project_root} — not purged (--keep-project)"
        )
        return ok

    try:
        mark_del_schema = await client.get_command_schema("project_set_mark_del")
    except Exception as exc:
        print(
            "TEARDOWN ABORTED: could not fetch schema for project_set_mark_del: "
            f"{exc!r}. project_id={fixtures.project_id} was never purged."
        )
        return False
    if not schema_has_project_id(mark_del_schema):
        print(
            "TEARDOWN ABORTED: project_set_mark_del schema has no project_id — "
            f"refusing to guess. project_id={fixtures.project_id} was never purged."
        )
        return False

    try:
        mark_resp = await client.call_validated(
            "project_set_mark_del", {"project_id": fixtures.project_id}
        )
    except Exception as exc:
        if _ALREADY_ABSENT_MARKER in str(exc).lower():
            print(
                "OK    teardown: project_set_mark_del found project "
                f"{fixtures.project_id} already-deleted: {exc!r}"
            )
        else:
            print(f"TEARDOWN ABORTED: project_set_mark_del raised: {exc!r}")
            return False
    else:
        if not mark_resp.get("success"):
            error_text = str(mark_resp.get("error"))
            if _ALREADY_ABSENT_MARKER in error_text.lower():
                print(
                    "OK    teardown: project_set_mark_del found project "
                    f"{fixtures.project_id} already-deleted: {error_text}"
                )
            else:
                print(
                    "TEARDOWN ABORTED: project_set_mark_del returned failure: "
                    f"{mark_resp.get('error')!r}"
                )
                return False

    # The live permanently_delete_from_trash schema takes `trash_folder_name`
    # (a direct child of trash_dir), not `project_id`. The name is already
    # knowable via the same read-only list_trashed_projects lookup used above
    # for the (now-removed) abort message, so purge proactively instead of
    # refusing: by this point project_set_mark_del already succeeded (or the
    # project was already absent), so a purge failure only leaves the project
    # sitting in trash — a safe holding area, not a DB-consistency problem —
    # and is therefore a WARN, never an abort.
    trash_folder_name = await _lookup_trash_folder_name(client, fixtures)
    if not trash_folder_name:
        print(
            "WARN  teardown: could not resolve trash_folder_name via "
            f"list_trashed_projects for project_id={fixtures.project_id} "
            f"({fixtures.project_name}); trash purge skipped, project remains in "
            "trash (safe holding area) for manual/clear_trash cleanup."
        )
        return ok

    try:
        purge_resp = await client.call_validated(
            "permanently_delete_from_trash", {"trash_folder_name": trash_folder_name}
        )
    except Exception as exc:
        print(
            "WARN  teardown: permanently_delete_from_trash raised: "
            f"{exc!r}. project_id={fixtures.project_id} ({fixtures.project_name}) "
            f"remains in trash (trash_folder_name={trash_folder_name!r})."
        )
        return ok
    if not purge_resp.get("success"):
        print(
            "WARN  teardown: permanently_delete_from_trash returned failure: "
            f"{purge_resp.get('error')!r}. project_id={fixtures.project_id} "
            f"({fixtures.project_name}) remains in trash "
            f"(trash_folder_name={trash_folder_name!r})."
        )
        return ok

    print(
        f"OK    teardown: permanently_delete_from_trash purged "
        f"trash_folder_name={trash_folder_name!r} "
        f"(project_id={fixtures.project_id}, {fixtures.project_name})"
    )
    return ok
