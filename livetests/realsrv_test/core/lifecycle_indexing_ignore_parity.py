"""
Indexing/watcher ignore-policy parity check (bug 5b663fbb).

Registered as suite ``s24`` (``realsrv_test.suites.s24_indexing_ignore_parity``,
``SUITE_NAME = "indexing_ignore_parity"``).

Before the fix, ``update_indexes``' eligibility walk
(``core/venv_path_policy.collect_python_files_for_indexing`` /
``collect_text_index_files_for_indexing``) pruned only
``core.constants.DEFAULT_IGNORE_PATTERNS`` (directory basenames), while the
file watcher's own scan/purge applies the broader
``watch_dir_settings.DEFAULT_WATCH_DIR_IGNORE_PATTERNS`` glob set (``**/
test_data/**``, ``**/*.egg-info/**``, ``**/develop-eggs/**``, ...). The two
policies diverged: ``update_indexes`` happily registered a ``test_data/``
file as a normal ``files`` row, and the very next watcher cycle's pre-scan
ignore purge deleted it again -- a live, permanently-recurring churn (measured
at 1496 rows/cycle on project 44a8ce88).

Mechanism: create a disposable project, upload one file under ``test_data/``
(watcher-ignored) and one control file under ``src/`` (not ignored), run
``update_indexes`` once (synchronous, no watcher restart), then read back via
``list_project_files`` (``python_only=True``, exact-path lookup) -- the
control file must be registered, the ``test_data/`` file must NOT be.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext
from realsrv_test.core.lifecycle_common import call_step_with_data

CHECK_NAME = "update_indexes_excludes_watcher_ignored_test_data"


def _outcome(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map this module returns.

    Args:
        status: Outcome status for the check.
        reason: Human-readable explanation of the result.

    Returns:
        ``{CHECK_NAME: CommandOutcome(...)}``, the shape ``run_lifecycles``
        merges.
    """
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}


def _no_session_skip() -> Dict[str, CommandOutcome]:
    """Return an EXPECTED_ERROR skip outcome when fixture seeding never ran."""
    return _outcome(Status.EXPECTED_ERROR, "skipped: no fixture session_id available")


async def _lookup_file_id(
    client: CodeAnalysisAsyncClient, project_id: str, relative_path: str
) -> Optional[str]:
    """Exact-path ``list_project_files`` (``python_only=True``) lookup.

    Args:
        client: Connected async client.
        project_id: Target project UUID.
        relative_path: Project-relative path to look up.

    Returns:
        ``file_id`` when the path is registered, else ``None``. Raises the
        underlying exception on transport/validation failure (caller wraps).
    """
    outcome, data = await call_step_with_data(
        client,
        "list_project_files",
        {
            "project_id": project_id,
            "file_pattern": relative_path,
            "python_only": True,
        },
        ok_reason="list_project_files exact-path lookup completed",
    )
    if outcome.status is not Status.EXECUTED_OK:
        raise RuntimeError(f"list_project_files failed: {outcome.reason}")
    rows: List[Any] = (data or {}).get("files") or (data or {}).get("items") or []
    if not rows:
        return None
    fid = rows[0].get("file_id") if isinstance(rows[0], dict) else None
    return str(fid) if fid else None


async def run_update_indexes_excludes_watcher_ignored_test_data(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Bug 5b663fbb: ``update_indexes`` must exclude what the watcher's default
    ignore policy excludes (``test_data/``, ``*.egg-info``, ``develop-eggs``, ...).

    ISOLATED PROJECT (own throwaway project, not ``fixtures.project_id``):
    mirrors ``realsrv_test.core.lifecycle_indexer_correctness``'s
    usages-idempotence check -- a project this check owns end-to-end, so
    ``update_indexes`` only ever processes these two fixture files and the
    project's own bootstrap files, keeping the verdict unambiguous.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run (only
            ``fixtures.session_id`` is used -- the client session is not
            project-scoped; a fresh throwaway project is created below).

    Returns:
        ``{CHECK_NAME: outcome}`` -- :attr:`Status.EXECUTED_OK` only when
        ``src/real.py`` is registered (has a ``file_id``) AND
        ``test_data/fixture.py`` is NOT registered (no ``file_id``) after one
        synchronous ``update_indexes`` run.
    """
    if not fixtures.session_id:
        return _no_session_skip()

    watch_dir_status, watch_dir_data = await call_step_with_data(
        client,
        "list_watch_dirs",
        {},
        ok_reason="watch directories listed",
    )
    watch_dirs = (watch_dir_data or {}).get("watch_dirs") or []
    if watch_dir_status.status is not Status.EXECUTED_OK or not watch_dirs:
        return _outcome(
            Status.FAILED,
            f"could not list a watch_dir for the isolated project ({watch_dir_status.reason})",
        )
    watch_dir_id = str(watch_dirs[0]["id"])

    project_suffix = uuid.uuid4().hex[:8]
    create_status, create_data = await call_step_with_data(
        client,
        "create_project",
        {
            "watch_dir_id": watch_dir_id,
            "project_name": f"verify_ignore_parity_{project_suffix}",
            "description": "isolated disposable project for the indexing/watcher ignore-parity check",
            "create_venv": False,
            "apply_template": False,
        },
        ok_reason="isolated throwaway project created",
    )
    if create_status.status is not Status.EXECUTED_OK:
        return _outcome(
            Status.FAILED,
            f"could not create the isolated project ({create_status.reason})",
        )
    project_id = str((create_data or {}).get("project_id") or "")
    if not project_id:
        return _outcome(
            Status.FAILED,
            f"create_project response missing project_id: {create_data!r}",
        )

    try:
        return await _run_ignore_parity_check(
            client, project_id=project_id, session_id=fixtures.session_id
        )
    finally:
        try:
            await client.call_validated(
                "delete_project",
                {"project_id": project_id, "delete_from_disk": True},
            )
        except Exception:  # noqa: BLE001 - best-effort cleanup only
            pass


async def _run_ignore_parity_check(
    client: CodeAnalysisAsyncClient,
    *,
    project_id: str,
    session_id: str,
) -> Dict[str, CommandOutcome]:
    """Seed the two fixture files, run ``update_indexes`` once, and assert.

    Args:
        client: Connected async client.
        project_id: The isolated throwaway project's UUID.
        session_id: Open file-session id (not project-scoped).

    Returns:
        ``{CHECK_NAME: outcome}``.
    """
    ignored_path = "test_data/fixture.py"
    control_path = "src/real.py"
    token = uuid.uuid4().hex[:12]
    ignored_content = (
        f'"""Fixture file under test_data/ -- watcher-ignored (token {token})."""\n'
        "x = 1\n"
    )
    control_content = (
        f'"""Fixture control file under src/ -- must be indexed (token {token})."""\n'
        "y = 2\n"
    )

    try:
        await client.file_sessions.upload_new(
            session_id,
            ignored_content.encode("utf-8"),
            project_id,
            ignored_path,
        )
        await client.file_sessions.upload_new(
            session_id,
            control_content.encode("utf-8"),
            project_id,
            control_path,
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return _outcome(Status.FAILED, truncate(f"fixture seed failed: {exc!r}"))

    reindex_outcome, reindex_data = await call_step_with_data(
        client,
        "update_indexes",
        {"project_id": project_id},
        ok_reason="update_indexes run completed",
    )
    if reindex_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            reindex_outcome.status,
            f"update_indexes did not succeed: {reindex_outcome.reason}",
        )

    try:
        control_file_id = await _lookup_file_id(client, project_id, control_path)
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return _outcome(
            Status.FAILED,
            truncate(f"list_project_files lookup for {control_path} failed: {exc!r}"),
        )
    try:
        ignored_file_id = await _lookup_file_id(client, project_id, ignored_path)
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return _outcome(
            Status.FAILED,
            truncate(f"list_project_files lookup for {ignored_path} failed: {exc!r}"),
        )

    problems: List[str] = []
    if not control_file_id:
        problems.append(
            f"{control_path}: expected a registered file_id after update_indexes, "
            "got none (fixture/check design issue -- this file must always index)"
        )
    if ignored_file_id:
        problems.append(
            f"{ignored_path}: expected NO registered file_id after update_indexes "
            f"(watcher-ignored path), got file_id={ignored_file_id!r} (bug "
            "5b663fbb: update_indexes' eligibility walk does not honor the "
            "watcher's DEFAULT_WATCH_DIR_IGNORE_PATTERNS, e.g. test_data/, so "
            "the next watcher pre-scan ignore purge deletes it again -- "
            "recurring per-cycle churn)"
        )

    if problems:
        return _outcome(Status.FAILED, "; ".join(problems))
    return _outcome(
        Status.EXECUTED_OK,
        f"{control_path} registered (file_id={control_file_id}), "
        f"{ignored_path} correctly excluded (watcher ignore-policy parity)",
    )
