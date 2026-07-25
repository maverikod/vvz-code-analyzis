"""
Git-federation helpers for the content_stale roundtrip check (bug N1 / 0d632d0e).

Split out of ``_verify_client_all_commands_lifecycle_content_stale.py`` to
stay under CR-008's module-size guideline (~350 lines prefer-split, ~450+
must-split). See that module's docstring for the full rationale of why a
``git_pull_safe``-based design replaced the original ``.py``-write and
``.md``-write attempts, and for what each step here is proving.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import Status
from _verify_client_all_commands_lifecycle_common import call_step_with_data

STALE_BRANCH = "stale_source"
SELF_REMOTE = "content_stale_selfremote"
GIT_IDENTITY_NAME = "verify-content-stale-bot"
GIT_IDENTITY_EMAIL = "verify-content-stale-bot@example.invalid"


async def require_step(
    client: CodeAnalysisAsyncClient,
    name: str,
    params: Dict[str, Any],
    ok_reason: str,
    *,
    fail_prefix: str,
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """Run one required setup step.

    Returns:
        ``(True, data, None)`` on success, or ``(False, None, reason)`` with
        a ready-to-report failure reason string.
    """
    outcome, data = await call_step_with_data(
        client, name, params, ok_reason=ok_reason
    )
    if outcome.status is not Status.EXECUTED_OK:
        return False, None, f"{fail_prefix}: {name} did not succeed ({outcome.reason})"
    return True, data, None


async def best_effort_remote_remove(
    client: CodeAnalysisAsyncClient, project_id: str
) -> None:
    """Drop the throwaway self-remote without letting cleanup failures affect the verdict."""
    try:
        await client.call_validated(
            "git_remote_remove", {"project_id": project_id, "name": SELF_REMOTE}
        )
    except Exception:  # noqa: BLE001 - cleanup only
        pass


async def stage_stale_content_via_git_pull(
    client: CodeAnalysisAsyncClient,
    *,
    project_id: str,
    project_root: str,
    session_id: str,
    file_id: str,
    relative_path: str,
    default_branch: str,
    new_content: bytes,
) -> Optional[str]:
    """Branch off, rewrite the fixture file, commit, switch back, self-pull.

    This produces the real, registered ``content_stale=TRUE`` mark via
    ``git_pull_safe``'s own per-file diff-based marking
    (``commands/git_admin_commands.py::_mark_pull_changed_files_stale``):

    1. Branch+checkout to a throwaway branch and overwrite the seeded file
       with ``new_content`` through the normal write path (synchronous
       reindex — DB ``code_content`` now holds the new content) and commit it
       there.
    2. Checkout back to ``default_branch`` — a RAW git operation that reverts
       the on-disk bytes to the baseline commit without going through any CA
       write handler.
    3. Add a SELF remote (the project's own ``root_path`` — git supports
       local-path remotes natively) and run
       ``git_pull_safe(remote=<self>, ref=<throwaway branch>)``, which
       fast-forwards ``default_branch`` to the throwaway branch's tip and
       marks the touched file ``content_stale=TRUE`` via its own
       pre/post-HEAD diff.

    Args:
        client: Connected async client.
        project_id: Disposable project UUID.
        project_root: Project's own server-side absolute root path, used
            as the self-remote URL.
        session_id: Open file-session id for the write in step 1.
        file_id: ``file_id`` of the already-seeded baseline file.
        relative_path: Project-relative path of that file.
        default_branch: Branch to return to before pulling (from
            ``git_status``).
        new_content: Bytes to overwrite the file with on the throwaway branch.

    Returns:
        ``None`` on success, or a failure reason string on the first step
        that did not succeed.
    """
    ok, _data, reason = await require_step(
        client,
        "git_branch_checkout",
        {"project_id": project_id, "name": STALE_BRANCH, "create": True},
        ok_reason=f"switched to throwaway branch {STALE_BRANCH}",
        fail_prefix="stale-branch setup",
    )
    if not ok:
        return reason

    try:
        await client.file_sessions.upload(
            session_id,
            new_content,
            file_id,
            project_id=project_id,
            filename=relative_path,
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return f"new-content write on {STALE_BRANCH} failed: {exc!r}"

    ok, _data, reason = await require_step(
        client,
        "git_add",
        {"project_id": project_id, "all": True},
        ok_reason="new-content file staged",
        fail_prefix="stale-branch setup",
    )
    if not ok:
        return reason

    ok, _data, reason = await require_step(
        client,
        "git_commit",
        {"project_id": project_id, "message": "content_stale check: new content"},
        ok_reason="new-content commit created",
        fail_prefix="stale-branch setup",
    )
    if not ok:
        return reason

    ok, _data, reason = await require_step(
        client,
        "git_branch_checkout",
        {"project_id": project_id, "name": default_branch},
        ok_reason=f"switched back to {default_branch}",
        fail_prefix="pull setup",
    )
    if not ok:
        return reason

    ok, _data, reason = await require_step(
        client,
        "git_remote_add",
        {"project_id": project_id, "name": SELF_REMOTE, "url": project_root},
        ok_reason="self-remote registered (project's own root_path)",
        fail_prefix="pull setup",
    )
    if not ok:
        return reason

    pull_outcome, _pull_data = await call_step_with_data(
        client,
        "git_pull_safe",
        {"project_id": project_id, "remote": SELF_REMOTE, "ref": STALE_BRANCH},
        ok_reason="git_pull_safe fast-forwarded the default branch",
    )
    if pull_outcome.status is not Status.EXECUTED_OK:
        return (
            f"git_pull_safe did not succeed ({pull_outcome.reason}) - "
            "content_stale never got marked"
        )
    return None
