"""
File-permission preservation checks for the save path (bug 92e6d693).

Registered as suite ``s18`` (``realsrv_test.suites.s18_file_mode``,
``SUITE_NAME = "filemode"``).

Defect this suite exists for: overwriting an already-indexed ``.py`` file
through ``project_file_transfer_upload_save`` left it mode ``0600``. Creating
the same file yields ``0644``, so the update path -- and only the update path
-- stripped group/other read access. The server itself owns the file, so
nothing on the API surface noticed; the damage shows up in every OTHER
process that has to read the file (a sandbox import failing with
PermissionError, a build, a web server), which is why it reached production.

Mechanism: the CST write path stages the new content in a
``tempfile.mkstemp`` file -- always ``0600`` -- and then ``os.replace``s it
over the target. ``os.replace`` keeps the SOURCE's permission bits, so the
target silently inherits ``0600``.

The checks below compare the mode reported for a file after it is created
with the mode reported after it is overwritten. They are deliberately written
against the reported values rather than a hardcoded ``644``: the contract is
"a save preserves the file's permissions", not "every file is 644", so the
assertion holds whatever umask the deployment runs under.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Dict, Optional, Tuple

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext

CHECK_NAME_PY_UPDATE = "upload_save_update_preserves_py_file_mode"
CHECK_NAME_TEXT_UPDATE = "upload_save_update_preserves_text_file_mode"

# Both bodies satisfy the server's docstring policy (a module docstring, and a
# function docstring carrying a Returns section): the save is rejected
# outright otherwise, and a rejected save would say nothing about permissions.
_PY_INITIAL = (
    '"""Fixture module."""\n\n\ndef greet() -> str:\n'
    '    """Build the greeting.\n\n    Returns:\n'
    '        The greeting text.\n    """\n    return "hello"\n'
).encode("utf-8")
_PY_UPDATED = (
    '"""Fixture module, edited."""\n\n\ndef greet() -> str:\n'
    '    """Build the greeting.\n\n    Returns:\n'
    '        The greeting text.\n    """\n    return "hi"\n'
).encode("utf-8")

_TEXT_INITIAL = b"first revision\n"
_TEXT_UPDATED = b"second revision\n"


def _outcome(name: str, status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map every check returns.

    Args:
        name: The check's unique name.
        status: Outcome status for the check.
        reason: Human-readable explanation of the result.

    Returns:
        ``{name: CommandOutcome(...)}``, the shape ``run_lifecycles`` merges.
    """
    return {name: CommandOutcome(name, Bucket.BUCKET_A, status, reason)}


async def _reported_mode(
    client: CodeAnalysisAsyncClient,
    fixtures: FixtureContext,
    file_id: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Return the server-reported permission bits for one file.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.
        file_id: ``files.id`` of the file to inspect.

    Returns:
        ``(mode, error)``: the octal mode string reported by
        ``project_file_transfer_download_begin``, or ``(None, reason)`` when
        the field is absent -- which itself means the deployed server predates
        the observability this check needs.
    """
    resp = await client.call_validated(
        "project_file_transfer_download_begin",
        {
            "file_id": file_id,
            "project_id": fixtures.project_id,
            "compression": "identity",
            "include_backup_history": False,
            "lock_mode": "none",
        },
    )
    if resp.get("success") is not True:
        return None, f"download_begin failed: {truncate(repr(resp.get('error')))}"
    data = resp.get("data") or {}
    if "mode" not in data:
        return None, (
            "the deployed server's project_file_transfer_download_begin "
            "response carries no 'mode' field, so this check cannot observe "
            "file permissions at all"
        )
    return str(data["mode"]), None


async def _run_mode_preservation_check(
    client: CodeAnalysisAsyncClient,
    fixtures: FixtureContext,
    *,
    name: str,
    rel_path: str,
    initial: bytes,
    updated: bytes,
) -> Dict[str, CommandOutcome]:
    """Create a file, overwrite it, and assert its permissions did not change.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.
        name: The check's unique name.
        rel_path: Project-relative path for the probe file.
        initial: Bytes for the create.
        updated: Bytes for the overwrite.

    Returns:
        ``{name: CommandOutcome(...)}`` for the comparison.
    """
    if not fixtures.session_id:
        return _outcome(
            name, Status.EXPECTED_ERROR, "skipped: no fixture session_id available"
        )
    session_id = str(fixtures.session_id)
    try:
        file_id = str(
            await client.file_sessions.upload_new(
                session_id, initial, fixtures.project_id, rel_path
            )
        )
        mode_after_create, err = await _reported_mode(client, fixtures, file_id)
        if err is not None:
            return _outcome(name, Status.INCONCLUSIVE, err)

        await client.file_sessions.upload(
            session_id,
            updated,
            file_id,
            project_id=fixtures.project_id,
            filename=rel_path.rsplit("/", 1)[-1],
        )
        mode_after_update, err = await _reported_mode(client, fixtures, file_id)
        if err is not None:
            return _outcome(name, Status.INCONCLUSIVE, err)
    except Exception as exc:  # noqa: BLE001 - a broken step is a real failure here
        return _outcome(name, Status.FAILED, truncate(repr(exc)))

    if mode_after_update == mode_after_create:
        return _outcome(
            name,
            Status.EXECUTED_OK,
            f"{rel_path}: mode {mode_after_create} preserved across the overwrite",
        )
    return _outcome(
        name,
        Status.FAILED,
        (
            f"{rel_path}: the overwrite changed the file's permissions -- "
            f"mode was {mode_after_create} after create and is "
            f"{mode_after_update} after update (bug 92e6d693)"
        ),
    )


async def run_py_update_preserves_mode(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Bug 92e6d693: overwriting an indexed ``.py`` file preserves its mode.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME_PY_UPDATE: CommandOutcome(...)}``.
    """
    return await _run_mode_preservation_check(
        client,
        fixtures,
        name=CHECK_NAME_PY_UPDATE,
        rel_path=f"file_mode_probe_{uuid.uuid4().hex[:8]}.py",
        initial=_PY_INITIAL,
        updated=_PY_UPDATED,
    )


async def run_text_update_preserves_mode(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Bug 92e6d693: overwriting an indexed text file preserves its mode.

    The text handler writes in place rather than staging through a temp file,
    so this case is expected to hold already; it is here so a future change to
    the text write path cannot introduce the same defect unnoticed.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME_TEXT_UPDATE: CommandOutcome(...)}``.
    """
    return await _run_mode_preservation_check(
        client,
        fixtures,
        name=CHECK_NAME_TEXT_UPDATE,
        rel_path=f"file_mode_probe_{uuid.uuid4().hex[:8]}.md",
        initial=_TEXT_INITIAL,
        updated=_TEXT_UPDATED,
    )
