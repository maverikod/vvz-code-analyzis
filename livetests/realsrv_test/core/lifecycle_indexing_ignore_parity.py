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

Mechanism (post-1.6.113 design fix -- do not reintroduce upload-based
seeding here): create a disposable *source* project and upload the two
fixture files into it via ``file_sessions.upload_new`` -- an unavoidable
registration in that throwaway project, which is discarded afterwards and
never assessed. The files under test are then materialized in a second,
disposable *target* project via ``git_clone`` (a plain local-path clone of
the source project's own root, mirroring the self-remote idiom in
``lifecycle_content_stale_git.py``). ``git_clone`` registers only the
*project* row (``CreateProjectCommand`` with ``use_existing_dir=True,
scaffold=False`` -- writes ``projectid``, inserts the ``projects`` row, does
not walk or register individual files); the cloned working tree lands on
disk through raw ``git clone``, so neither fixture file has a ``files`` row
in the target project before ``update_indexes`` runs. This is required
because ``file_sessions.upload_new`` (``project_file_transfer_upload_save``
create mode) pre-registers ``files.id`` via
``register_file_row_for_new_content`` synchronously on upload, with no
ignore-policy check -- seeding the ignored file that way gives it a
``file_id`` before ``update_indexes`` ever runs, so the "no file_id after
update_indexes" assertion could never pass regardless of the server-side fix
(diagnosed against deployed 1.6.113, where the eligibility-walk fix itself
was confirmed correct; the check's own seeding was the defect).

Once both fixture files exist unregistered in the target project, run
``update_indexes`` once (synchronous, no watcher restart), then read back via
``list_project_files`` (``python_only=True``, exact-path lookup) -- the
control file (``src/real.py``) must be registered, the ``test_data/`` file
(``test_data/fixture.py``) must NOT be.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext
from realsrv_test.core.lifecycle_common import call_step_with_data

CHECK_NAME = "update_indexes_excludes_watcher_ignored_test_data"

_GIT_IDENTITY_NAME = "verify-ignore-parity-bot"
_GIT_IDENTITY_EMAIL = "verify-ignore-parity-bot@example.invalid"


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

    TWO ISOLATED PROJECTS (own throwaway projects, not ``fixtures.project_id``):
    a *source* project the fixture files are uploaded into (registration
    there is unavoidable and irrelevant -- it is discarded), and a *target*
    project materialized from it via ``git_clone`` so the files land on disk
    unregistered (see the module docstring for why upload-based seeding
    cannot exercise this check). ``update_indexes`` only ever processes the
    target project's two fixture files and its own bootstrap files, keeping
    the verdict unambiguous.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run (only
            ``fixtures.session_id`` is used -- the client session is not
            project-scoped; the source/target throwaway projects are created
            below).

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

    created_project_ids: List[str] = []
    try:
        return await _run_ignore_parity_check(
            client,
            watch_dir_id=watch_dir_id,
            session_id=fixtures.session_id,
            created_project_ids=created_project_ids,
        )
    finally:
        for leftover_project_id in created_project_ids:
            try:
                await client.call_validated(
                    "project_set_mark_del", {"project_id": leftover_project_id}
                )
            except Exception:  # noqa: BLE001 - best-effort cleanup only
                pass


async def _seed_source_project(
    client: CodeAnalysisAsyncClient,
    *,
    watch_dir_id: str,
    session_id: str,
    ignored_path: str,
    ignored_content: bytes,
    control_path: str,
    control_content: bytes,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Create and seed the throwaway project the target is ``git_clone``d from.

    Uploads through ``file_sessions.upload_new`` here is fine -- this project
    is never itself checked for ignore-policy parity, only used as a git
    remote for the target project below, then discarded.

    Args:
        client: Connected async client.
        watch_dir_id: Watch directory to create the source project under.
        session_id: Open file-session id (not project-scoped).
        ignored_path: Project-relative path of the watcher-ignored fixture file.
        ignored_content: Bytes to upload at ``ignored_path``.
        control_path: Project-relative path of the control fixture file.
        control_content: Bytes to upload at ``control_path``.

    Returns:
        ``(source_project_id, source_project_root, error)`` -- ``error`` is
        ``None`` on success. ``source_project_id`` may be set even when
        ``error`` is not ``None`` (a later step failed after project
        creation), so the caller can still clean it up.
    """
    suffix = uuid.uuid4().hex[:8]
    create_status, create_data = await call_step_with_data(
        client,
        "create_project",
        {
            "watch_dir_id": watch_dir_id,
            "project_name": f"verify_ignore_parity_src_{suffix}",
            "description": "throwaway git_clone source for the indexing/watcher ignore-parity check",
            "create_venv": False,
            "apply_template": False,
        },
        ok_reason="seed source project created",
    )
    if create_status.status is not Status.EXECUTED_OK:
        return (
            None,
            None,
            f"could not create the seed source project ({create_status.reason})",
        )
    source_project_id = str((create_data or {}).get("project_id") or "")
    source_project_root = str((create_data or {}).get("project_root") or "")
    if not source_project_id or not source_project_root:
        return (
            source_project_id or None,
            None,
            f"create_project response missing project_id/project_root: {create_data!r}",
        )

    try:
        await client.file_sessions.upload_new(
            session_id, ignored_content, source_project_id, ignored_path
        )
        await client.file_sessions.upload_new(
            session_id, control_content, source_project_id, control_path
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return source_project_id, None, f"source fixture seed failed: {exc!r}"

    identity_outcome, _identity_data = await call_step_with_data(
        client,
        "git_identity_set",
        {
            "project_id": source_project_id,
            "name": _GIT_IDENTITY_NAME,
            "email": _GIT_IDENTITY_EMAIL,
        },
        ok_reason="git identity configured for the seed source project",
    )
    if identity_outcome.status is not Status.EXECUTED_OK:
        return (
            source_project_id,
            None,
            f"git_identity_set on the seed source project did not succeed: {identity_outcome.reason}",
        )

    add_outcome, _add_data = await call_step_with_data(
        client,
        "git_add",
        {"project_id": source_project_id, "all": True},
        ok_reason="source fixture files staged",
    )
    if add_outcome.status is not Status.EXECUTED_OK:
        return (
            source_project_id,
            None,
            f"git_add on the seed source project did not succeed: {add_outcome.reason}",
        )

    commit_outcome, _commit_data = await call_step_with_data(
        client,
        "git_commit",
        {
            "project_id": source_project_id,
            "message": "ignore-parity check: seed fixture files",
        },
        ok_reason="source fixture commit created",
    )
    if commit_outcome.status is not Status.EXECUTED_OK:
        return (
            source_project_id,
            None,
            f"git_commit on the seed source project did not succeed: {commit_outcome.reason}",
        )

    return source_project_id, source_project_root, None


async def _run_ignore_parity_check(
    client: CodeAnalysisAsyncClient,
    *,
    watch_dir_id: str,
    session_id: str,
    created_project_ids: List[str],
) -> Dict[str, CommandOutcome]:
    """Seed a source project, ``git_clone`` it into an unregistered target,
    run ``update_indexes`` once, and assert.

    Args:
        client: Connected async client.
        watch_dir_id: Watch directory both throwaway projects are created under.
        session_id: Open file-session id (not project-scoped).
        created_project_ids: Appended with every project_id this check
            creates (source and target), so the caller can best-effort clean
            up all of them regardless of where a failure happens.

    Returns:
        ``{CHECK_NAME: outcome}``.
    """
    ignored_path = "test_data/fixture.py"
    control_path = "src/real.py"
    token = uuid.uuid4().hex[:12]
    ignored_content = (
        f'"""Fixture file under test_data/ -- watcher-ignored (token {token})."""\n'
        "x = 1\n"
    ).encode("utf-8")
    control_content = (
        f'"""Fixture control file under src/ -- must be indexed (token {token})."""\n'
        "y = 2\n"
    ).encode("utf-8")

    source_project_id, source_project_root, seed_error = await _seed_source_project(
        client,
        watch_dir_id=watch_dir_id,
        session_id=session_id,
        ignored_path=ignored_path,
        ignored_content=ignored_content,
        control_path=control_path,
        control_content=control_content,
    )
    if source_project_id:
        created_project_ids.append(source_project_id)
    if seed_error:
        return _outcome(Status.FAILED, truncate(seed_error))

    clone_suffix = uuid.uuid4().hex[:8]
    clone_outcome, clone_data = await call_step_with_data(
        client,
        "git_clone",
        {
            "url": source_project_root,
            "watch_dir_id": watch_dir_id,
            "target_name": f"verify_ignore_parity_{clone_suffix}",
        },
        ok_reason="target project materialized via git_clone (files unregistered)",
    )
    if clone_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            clone_outcome.status,
            f"git_clone of the seed source did not succeed: {clone_outcome.reason}",
        )
    target_project_id = str((clone_data or {}).get("project_id") or "")
    if not target_project_id:
        return _outcome(
            Status.FAILED,
            f"git_clone response missing project_id: {clone_data!r}",
        )
    created_project_ids.append(target_project_id)

    reindex_outcome, _reindex_data = await call_step_with_data(
        client,
        "update_indexes",
        {"project_id": target_project_id},
        ok_reason="update_indexes run completed",
    )
    if reindex_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            reindex_outcome.status,
            f"update_indexes did not succeed: {reindex_outcome.reason}",
        )

    try:
        control_file_id = await _lookup_file_id(client, target_project_id, control_path)
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return _outcome(
            Status.FAILED,
            truncate(f"list_project_files lookup for {control_path} failed: {exc!r}"),
        )
    try:
        ignored_file_id = await _lookup_file_id(client, target_project_id, ignored_path)
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
