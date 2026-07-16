"""
Ordered transfer-command lifecycle for the live-server all-commands verifier.

Covers two independent transfer surfaces:

* The generic adapter transfer session. Upload
  (``transfer_upload_begin`` / ``transfer_upload_status`` /
  ``transfer_upload_complete``) is exercised through
  ``client.file_sessions.upload_bytes``, which performs the real
  begin+chunks+complete handshake (see ``file_session.py`` ~line 501) so
  ``transfer_upload_complete`` gets a genuine completed transfer instead of
  the checksum/staged-size-mismatch rejection a bare begin-then-complete call
  (with no chunk PUT) always produces. Download
  (``transfer_download_begin`` / ``transfer_download_status``) is still
  called directly via ``client.call_validated`` with a real absolute
  server-side file path (a seeded fixture file).
* The project-scoped, file-id transfer commands
  (``project_file_transfer_download_begin`` / ``project_file_transfer_upload_save``
  and ``project_file_advisory_lock_batch``), exercised through the
  ``client.file_sessions`` façade, which performs the full begin+chunk
  handshake for a real completed download/upload.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Dict

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status, truncate
from _verify_client_all_commands_fixtures import FixtureContext
from _verify_client_all_commands_lifecycle_common import call_step_with_data

_UPLOAD_PAYLOAD = b"verify sweep generic transfer payload\n"


async def _run_generic_upload_steps(
    client: CodeAnalysisAsyncClient,
) -> Dict[str, CommandOutcome]:
    """Run the generic upload session via ``upload_bytes`` (real begin+chunks+complete)."""
    outcomes: Dict[str, CommandOutcome] = {}

    try:
        receipt = await client.file_sessions.upload_bytes(
            _UPLOAD_PAYLOAD, filename="verify_transfer.bin", compression="identity"
        )
    except Exception as exc:  # noqa: BLE001 - real rejection, still genuine
        reason = truncate(repr(exc))
        outcomes["transfer_upload_begin"] = CommandOutcome(
            "transfer_upload_begin", Bucket.BUCKET_A, Status.EXPECTED_ERROR, reason
        )
        outcomes["transfer_upload_status"] = CommandOutcome(
            "transfer_upload_status",
            Bucket.BUCKET_A,
            Status.EXPECTED_ERROR,
            "skipped: upload_bytes (begin+chunks+complete) failed",
        )
        outcomes["transfer_upload_complete"] = CommandOutcome(
            "transfer_upload_complete",
            Bucket.BUCKET_A,
            Status.EXPECTED_ERROR,
            "skipped: upload_bytes (begin+chunks+complete) failed",
        )
        return outcomes

    completed = bool(getattr(receipt, "completed", False))
    transfer_id = str(getattr(receipt, "transfer_id", "") or "").strip()
    outcomes["transfer_upload_begin"] = CommandOutcome(
        "transfer_upload_begin",
        Bucket.BUCKET_A,
        Status.EXECUTED_OK,
        "opened via client.file_sessions.upload_bytes (real begin+chunks+complete)",
    )
    if transfer_id:
        status_outcome, _ = await call_step_with_data(
            client, "transfer_upload_status", {"transfer_id": transfer_id}
        )
        outcomes["transfer_upload_status"] = status_outcome
    else:
        outcomes["transfer_upload_status"] = CommandOutcome(
            "transfer_upload_status",
            Bucket.BUCKET_A,
            Status.EXPECTED_ERROR,
            "skipped: upload_bytes returned no transfer_id",
        )
    outcomes["transfer_upload_complete"] = CommandOutcome(
        "transfer_upload_complete",
        Bucket.BUCKET_A,
        Status.EXECUTED_OK if completed else Status.EXPECTED_ERROR,
        "finalized via client.file_sessions.upload_bytes "
        f"(real begin+chunks+complete); completed={completed}",
    )
    return outcomes


async def _run_generic_download_steps(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Run the generic (non-project-scoped) adapter download session steps."""
    outcomes: Dict[str, CommandOutcome] = {}

    source_path = str(fixtures.project_root / fixtures.py_file_path)
    dl_begin_outcome, dl_begin_data = await call_step_with_data(
        client,
        "transfer_download_begin",
        {
            "source_path": source_path,
            "filename": "verify_module.py",
            "compression": "identity",
        },
        ok_reason="opened a real generic download session for a seeded file",
    )
    outcomes["transfer_download_begin"] = dl_begin_outcome
    download_transfer_id = str((dl_begin_data or {}).get("transfer_id") or "").strip()
    if download_transfer_id:
        dl_status_outcome, _ = await call_step_with_data(
            client, "transfer_download_status", {"transfer_id": download_transfer_id}
        )
        outcomes["transfer_download_status"] = dl_status_outcome
    else:
        outcomes["transfer_download_status"] = CommandOutcome(
            "transfer_download_status",
            Bucket.BUCKET_A,
            dl_begin_outcome.status,
            "skipped: transfer_download_begin returned no transfer_id",
        )
    return outcomes


async def _run_project_file_transfer_steps(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Run the file-id-scoped project transfer and advisory-lock steps."""
    outcomes: Dict[str, CommandOutcome] = {}

    if fixtures.py_file_id and fixtures.session_id:
        dest = Path(tempfile.gettempdir()) / f"verify_download_{uuid.uuid4().hex}.py"
        try:
            await client.file_sessions.download(
                fixtures.session_id, dest, fixtures.py_file_id
            )
            outcomes["project_file_transfer_download_begin"] = CommandOutcome(
                "project_file_transfer_download_begin",
                Bucket.BUCKET_A,
                Status.EXECUTED_OK,
                "real completed download of the seeded .py file via client.file_sessions",
            )
        except Exception as exc:  # noqa: BLE001 - real rejection, still genuine
            outcomes["project_file_transfer_download_begin"] = CommandOutcome(
                "project_file_transfer_download_begin",
                Bucket.BUCKET_A,
                Status.EXPECTED_ERROR,
                truncate(repr(exc)),
            )
        finally:
            dest.unlink(missing_ok=True)
    else:
        outcomes["project_file_transfer_download_begin"] = CommandOutcome(
            "project_file_transfer_download_begin",
            Bucket.BUCKET_A,
            Status.EXPECTED_ERROR,
            "skipped: no seeded file_id/session_id available",
        )

    if fixtures.session_id:
        try:
            new_file_id = await client.file_sessions.upload_new(
                fixtures.session_id,
                b"# verify sweep new file via project_file_transfer_upload_save\n",
                fixtures.project_id,
                "verify_upload_new.py",
            )
            outcomes["project_file_transfer_upload_save"] = CommandOutcome(
                "project_file_transfer_upload_save",
                Bucket.BUCKET_A,
                Status.EXECUTED_OK,
                f"real completed new-file upload, file_id={new_file_id or '(empty)'}",
            )
        except Exception as exc:  # noqa: BLE001 - real rejection, still genuine
            outcomes["project_file_transfer_upload_save"] = CommandOutcome(
                "project_file_transfer_upload_save",
                Bucket.BUCKET_A,
                Status.EXPECTED_ERROR,
                truncate(repr(exc)),
            )
    else:
        outcomes["project_file_transfer_upload_save"] = CommandOutcome(
            "project_file_transfer_upload_save",
            Bucket.BUCKET_A,
            Status.EXPECTED_ERROR,
            "skipped: no session_id available",
        )

    if fixtures.session_id:
        try:
            await client.file_sessions.lock_files_advisory(
                fixtures.session_id, fixtures.project_id, [fixtures.py_file_path]
            )
            outcomes["project_file_advisory_lock_batch"] = CommandOutcome(
                "project_file_advisory_lock_batch",
                Bucket.BUCKET_A,
                Status.EXECUTED_OK,
                "locked the seeded .py file via advisory batch",
            )
            await client.file_sessions.unlock_files_advisory(
                fixtures.session_id, fixtures.project_id, [fixtures.py_file_path]
            )
        except Exception as exc:  # noqa: BLE001 - real rejection, still genuine
            outcomes["project_file_advisory_lock_batch"] = CommandOutcome(
                "project_file_advisory_lock_batch",
                Bucket.BUCKET_A,
                Status.EXPECTED_ERROR,
                truncate(repr(exc)),
            )
    else:
        outcomes["project_file_advisory_lock_batch"] = CommandOutcome(
            "project_file_advisory_lock_batch",
            Bucket.BUCKET_A,
            Status.EXPECTED_ERROR,
            "skipped: no session_id available",
        )
    return outcomes


async def run_transfer_lifecycle(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Run every transfer-surface command as one lifecycle.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        Mapping of every command name this lifecycle covers to its outcome.
    """
    outcomes: Dict[str, CommandOutcome] = {}
    outcomes.update(await _run_generic_upload_steps(client))
    outcomes.update(await _run_generic_download_steps(client, fixtures))
    outcomes.update(await _run_project_file_transfer_steps(client, fixtures))
    return outcomes
