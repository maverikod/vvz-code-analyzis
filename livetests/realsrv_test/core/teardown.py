"""
Disposable-project teardown for the live-server all-commands verifier.

Closes the sweep-wide session and purges the disposable project created by
``realsrv_test.core.fixtures.seed_fixtures``, or — per the
operator's ``--keep-project`` flag — leaves it in place for manual inspection.
The purge itself is delegated to
``realsrv_test.core.disposable_project.purge_disposable_project`` (bug
d5835fbf), which resolves the trash folder by diffing
``list_trashed_projects`` before/after the soft-delete instead of matching
``original_name`` against the project's creation-time name — see that
module's docstring for why: ``lifecycle_project_lock.py`` renames this exact
shared fixture project mid-sweep, so a name-based match here used to miss
every time (47 leaked ``verify_lock_original_*`` trash entries observed
before this fix). A purge failure, or a folder name that fails to resolve,
is logged as a WARN rather than an abort: by that point
``project_set_mark_del`` has already succeeded, so the project is out of the
DB either way, and trash is a safe holding area for manual (or
``clear_trash``) cleanup later.

The project_id-in-schema scoping gate below (``schema_has_project_id``) is
applied only here, immediately before this module's own
``project_set_mark_del`` call — this is the sole caller of
``project_set_mark_del`` outside ``purge_disposable_project`` (see
``realsrv_test.core.catalog.BUCKET_B_REASONS``), so it stays a
teardown.py-local safety check rather than something the shared helper
enforces for every disposable-project call site.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import schema_has_project_id
from realsrv_test.core.disposable_project import purge_disposable_project
from realsrv_test.core.fixtures import FixtureContext


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

    # project_set_mark_del + trash purge, both delegated to the shared,
    # rename-proof helper (bug d5835fbf) — see module docstring for why a
    # name-based trash match (the old approach here) used to miss this exact
    # shared fixture project after lifecycle_project_lock.py renames it.
    result = await purge_disposable_project(
        client, fixtures.project_id, fixtures.project_name
    )
    if result.startswith("mark_del-raised") or result.startswith("mark_del-failed"):
        print(
            f"TEARDOWN ABORTED: {result}. project_id={fixtures.project_id} "
            "was never purged."
        )
        return False
    if result.startswith("purged"):
        print(
            f"OK    teardown: {result} "
            f"(project_id={fixtures.project_id}, {fixtures.project_name})"
        )
        return ok

    # Any other outcome (already-absent-but-trash-entry-not-found,
    # purge-raised, purge-failed) is a WARN, not an abort: by this point
    # project_set_mark_del already succeeded (or the project was already
    # absent), so a stuck trash purge only leaves the project sitting in
    # trash — a safe holding area, not a DB-consistency problem.
    print(
        f"WARN  teardown: {result} "
        f"(project_id={fixtures.project_id}, {fixtures.project_name})"
    )
    return ok
