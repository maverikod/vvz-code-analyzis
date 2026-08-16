"""
Shared disposable-project purge helper (bug d5835fbf; feeds 93d45b21).

Every livetest that creates its own throwaway project (as opposed to reusing
the sweep-wide :class:`~realsrv_test.core.fixtures.FixtureContext` project)
needs the exact same end-of-check cleanup: soft-delete the project (trash +
DB clear), then permanently purge the resulting trash folder. Before this
module, five call sites reimplemented that idiom independently and four of
them leaked:

* ``realsrv_test.core.teardown._lookup_trash_folder_name`` matched a trash
  entry's parsed ``original_name`` against the project's *creation-time*
  name. ``lifecycle_project_lock.py`` renames the shared sweep project twice
  (``verify_lock_renamed_<hex>`` then back to a *fresh*
  ``verify_lock_original_<hex>``, never the original creation-time name), so
  by teardown time the name never matches again -- the purge silently
  no-ops every run (47 ``verify_lock_original_*`` trash entries observed).
* ``lifecycle_indexer_correctness.py`` called a command named
  ``"delete_project"``, which does not exist on the live server -- every
  invocation raised and was swallowed by a bare ``except: pass`` (32 leaked
  ``verify_indexer_usage_idem_*`` projects, never even soft-deleted).
* ``lifecycle_global_search.py`` had no cleanup code at all (109 leaked
  ``verify-global-search-*`` projects).
* ``lifecycle_indexing_ignore_parity.py`` and the three vectorization
  lifecycles (via ``vectorization_fixture_common.py``) called
  ``project_set_mark_del`` but never followed up with
  ``permanently_delete_from_trash``, leaving trash-only residue.

Resolution strategy (see :func:`purge_disposable_project`): the live
``list_trashed_projects`` response carries only ``folder_name`` /
``original_name`` / ``deleted_at`` / ``path`` -- no ``project_id`` (verified
against ``code_analysis.commands.trash_commands.ListTrashedProjectsCommand``
and ``code_analysis.core.trash_utils.get_project_id_from_trash_folder``: the
latter reads a ``projectid`` marker file *inside* the trashed folder on the
server's local disk, which is never exposed to a remote client -- there is
no MCP command that reads an arbitrary path under ``trash_dir``). So a
genuinely ID-based lookup is not available to this client. Instead, this
helper snapshots the trash folder-name set *before* calling
``project_set_mark_del`` and diffs it against the set *after*: the
newly-appeared folder is the one this call just created, independent of
whatever name the project carried at deletion time. This is rename-proof by
construction (it never inspects ``original_name`` for the common case) and
is the strategy used whenever exactly one new folder appears. A same-name
``original_name`` match (the old strategy) is kept only as a fallback for
the cases the diff can't resolve on its own (lookup failure before the
call, or a concurrent purge from another run landing in the same window).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import truncate

# Same marker realsrv_test.core.fixtures_registration.py polls for: the
# server's rejection text when a project_id no longer has a DB row. Treated
# as an already-successful delete rather than a failure -- teardown must be
# idempotent against a project that some earlier step already removed.
_ALREADY_ABSENT_MARKER = "not found in database"


async def _list_trash_items(
    client: CodeAnalysisAsyncClient,
) -> Optional[List[Dict[str, Any]]]:
    """Best-effort, read-only ``list_trashed_projects`` fetch.

    Returns:
        The response's ``items`` list, or ``None`` if the call itself failed
        (never raises) -- callers must treat ``None`` as "unknown", not as
        "empty", so a lookup failure can never be misread as "nothing in
        trash".
    """
    try:
        resp = await client.call_validated("list_trashed_projects", {})
    except Exception:  # noqa: BLE001 - best-effort lookup only
        return None
    if not resp.get("success"):
        return None
    data = resp.get("data") or {}
    items = data.get("items")
    return items if isinstance(items, list) else []


def _folder_names(items: List[Dict[str, Any]]) -> Set[str]:
    """Return the set of ``folder_name`` values across trash ``items``."""
    return {
        str(item["folder_name"])
        for item in items
        if isinstance(item, dict) and item.get("folder_name")
    }


def _best_match_by_name(
    items: List[Dict[str, Any]], candidate_folder_names: Set[str], project_name: str
) -> Optional[str]:
    """Among ``candidate_folder_names``, pick the one whose parsed
    ``original_name`` equals ``project_name``, preferring the most recently
    deleted entry when more than one matches.

    Args:
        items: Full ``list_trashed_projects`` items (for their
            ``original_name``/``deleted_at`` fields).
        candidate_folder_names: Subset of folder names to consider (may be
            every folder name, or just a diff set).
        project_name: The disposable project's directory/display name.

    Returns:
        A matching ``folder_name``, or ``None`` if none matched.
    """
    matches = [
        item
        for item in items
        if isinstance(item, dict)
        and item.get("folder_name") in candidate_folder_names
        and item.get("original_name") == project_name
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: str(item.get("deleted_at") or ""), reverse=True)
    return str(matches[0]["folder_name"])


async def _resolve_trash_folder_name(
    client: CodeAnalysisAsyncClient,
    *,
    before_names: Optional[Set[str]],
    project_name: Optional[str],
) -> tuple[Optional[str], str]:
    """Resolve the trash folder this call's ``project_set_mark_del`` created.

    Args:
        client: Connected async client.
        before_names: Folder-name set captured before ``project_set_mark_del``
            ran, or ``None`` if that snapshot itself failed.
        project_name: The disposable project's directory/display name, used
            only as a fallback matcher (see module docstring).

    Returns:
        ``(folder_name, strategy)`` -- ``folder_name`` is ``None`` if no
        strategy resolved one; ``strategy`` names which one was used (or
        would have been attempted) for the caller's outcome string.
    """
    after_items = await _list_trash_items(client)
    if after_items is None:
        return None, "trash-lookup-failed"
    after_names = _folder_names(after_items)

    new_names = (after_names - before_names) if before_names is not None else set()
    if len(new_names) == 1:
        return next(iter(new_names)), "diff"

    if len(new_names) > 1 and project_name:
        folder_name = _best_match_by_name(after_items, new_names, project_name)
        if folder_name:
            return folder_name, "diff+name"

    if project_name:
        folder_name = _best_match_by_name(after_items, after_names, project_name)
        if folder_name:
            return folder_name, "name-fallback"

    if len(new_names) > 1:
        return None, "ambiguous-diff"
    return None, "not-found"


async def purge_disposable_project(
    client: CodeAnalysisAsyncClient,
    project_id: str,
    project_name: Optional[str] = None,
) -> str:
    """Soft-delete ``project_id`` and permanently purge its trash folder.

    Best-effort end to end: never raises. Every livetest teardown that owns
    a throwaway project should call this instead of hand-rolling
    ``project_set_mark_del`` (+ maybe a trash purge) -- see the module
    docstring for the leak history this replaces.

    Args:
        client: Connected async client.
        project_id: UUID4 of the disposable project to purge.
        project_name: The project's directory/display name, if known. Used
            only as a fallback trash-folder matcher when the before/after
            folder-name diff can't resolve one on its own (see
            :func:`_resolve_trash_folder_name`); omit only when the caller
            truly never captured it.

    Returns:
        A short, human-readable outcome string for the caller's WARN/OK log
        line or ``CommandOutcome.reason`` text -- never raises.
    """
    before_items = await _list_trash_items(client)
    before_names = _folder_names(before_items) if before_items is not None else None

    try:
        mark_resp = await client.call_validated(
            "project_set_mark_del",
            {"project_id": project_id, "delete_from_disk": False},
        )
    except Exception as exc:  # noqa: BLE001 - best-effort cleanup only
        if _ALREADY_ABSENT_MARKER in str(exc).lower():
            pass  # already gone from the DB; still try to purge stale trash below
        else:
            return truncate(f"mark_del-raised: {exc!r}")
    else:
        if not mark_resp.get("success"):
            error_text = str(mark_resp.get("error"))
            if _ALREADY_ABSENT_MARKER not in error_text.lower():
                return truncate(f"mark_del-failed: {error_text}")
            # already-absent: fall through, same as the raised branch above.

    folder_name, strategy = await _resolve_trash_folder_name(
        client, before_names=before_names, project_name=project_name
    )
    if not folder_name:
        return f"mark_del-ok; trash-entry-not-found ({strategy}); left in trash"

    try:
        purge_resp = await client.call_validated(
            "permanently_delete_from_trash", {"trash_folder_name": folder_name}
        )
    except Exception as exc:  # noqa: BLE001 - best-effort cleanup only
        return truncate(f"purge-raised ({strategy}, {folder_name!r}): {exc!r}")
    if not purge_resp.get("success"):
        return truncate(
            f"purge-failed ({strategy}, {folder_name!r}): {purge_resp.get('error')!r}"
        )
    return f"purged ({strategy}): {folder_name}"
