"""
Disposable-project teardown for the live-server all-commands verifier.

Closes the sweep-wide session and purges the disposable project created by
``_verify_client_all_commands_fixtures.seed_fixtures``, or — per the
operator's ``--keep-project`` flag — leaves it in place for manual inspection.
Trash purge always aborts loudly rather than guessing a trash folder name (see
the design note above ``teardown_fixtures``); the abort message is enriched
with the real trash folder name via a read-only ``list_trashed_projects``
lookup, which is always safe to call.

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

    Applies the same project_id-in-schema scoping gate to both
    ``project_set_mark_del`` and ``permanently_delete_from_trash`` before
    calling them; aborts loudly instead of guessing if either fails the gate.
    ``project_set_mark_del`` itself is idempotent to an "already absent"
    rejection (see module docstring) — that case is logged and treated as
    success, not an abort.

    Args:
        client: Connected async client.
        fixtures: Fixture context produced by ``seed_fixtures`` (its
            ``project_id`` reflects ``change_project_id`` if that command ran
            and succeeded during the sweep).
        keep_project: If True, skip project purge and print the project id
            for manual operator cleanup.

    Returns:
        True if teardown completed cleanly (or was explicitly skipped via
        ``keep_project``); False if any step failed or a safety gate aborted
        the purge.
    """
    ok = True

    if fixtures.session_id:
        try:
            resp = await client.call_validated(
                "session_delete", {"session_id": fixtures.session_id}
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

    # NOTE (design judgment call): the live permanently_delete_from_trash schema
    # takes `trash_folder_name` (a direct child of trash_dir), not `project_id`.
    # The gate below therefore fails by construction against the current live
    # schema. Per the teardown contract this must abort loudly rather than
    # fabricate a trash folder name — the disposable project is left in trash
    # for the operator (or clear_trash / a manual permanently_delete_from_trash
    # call) to purge. This is expected, not a bug in this verifier.
    try:
        purge_schema = await client.get_command_schema("permanently_delete_from_trash")
    except Exception as exc:
        print(
            "TEARDOWN ABORTED after mark-del: could not fetch schema for "
            f"permanently_delete_from_trash: {exc!r}. project_id={fixtures.project_id} "
            f"({fixtures.project_name}) is now in trash; purge it manually."
        )
        return False
    if not schema_has_project_id(purge_schema):
        trash_folder_name = await _lookup_trash_folder_name(client, fixtures)
        folder_hint = (
            f"trash_folder_name={trash_folder_name!r}"
            if trash_folder_name
            else "trash_folder_name could not be resolved via list_trashed_projects"
        )
        print(
            "TEARDOWN ABORTED after mark-del: permanently_delete_from_trash schema has "
            "no project_id property (it takes trash_folder_name instead) — refusing to "
            f"guess. project_id={fixtures.project_id} ({fixtures.project_name}) is now "
            f"in trash; {folder_hint}. Purge manually via "
            "permanently_delete_from_trash(trash_folder_name=...)."
        )
        return False

    try:
        purge_resp = await client.call_validated(
            "permanently_delete_from_trash", {"project_id": fixtures.project_id}
        )
    except Exception as exc:
        print(f"TEARDOWN ABORTED: permanently_delete_from_trash raised: {exc!r}")
        return False
    if not purge_resp.get("success"):
        print(
            "TEARDOWN ABORTED: permanently_delete_from_trash returned failure: "
            f"{purge_resp.get('error')!r}"
        )
        return False

    return ok
