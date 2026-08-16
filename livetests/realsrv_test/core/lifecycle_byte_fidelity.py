"""
Byte-fidelity checks for the project file save path (bug 44724d35).

Registered as suite ``s17`` (``realsrv_test.suites.s17_byte_fidelity``,
``SUITE_NAME = "bytes"``).

Defect this suite exists for: ``project_file_transfer_upload_save`` rewrote
the line endings of the bytes it was handed. A file uploaded with CRLF
terminators landed on disk with LF -- ``b"alpha\\r\\nbeta\\r\\ngamma\\r\\n"``
(20 bytes) was stored as ``b"alpha\\nbeta\\ngamma\\n"`` (17 bytes) -- and the
save reported success, so the caller had no signal that its content had been
altered and no declared parameter to opt out. Root cause: the server read the
completed transfer buffer in Python's default *text* mode
(``Path.read_text()`` / ``gzip.open(..., "rt")``), which applies universal-
newline translation, collapsing ``\\r\\n`` and lone ``\\r`` to ``\\n`` before
the bytes ever reached the file handler.

Mechanism of every check below: push a payload with non-LF terminators
through the real transfer + save path, read it back through the real
download path (the adapter streams downloads in binary, so the read-back is
byte-exact -- verified live), and assert the bytes are identical. Each check
fails RED against the unfixed server and passes GREEN once the save path
preserves the bytes it is given.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Dict, Optional

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext

CHECK_NAME_CREATE_CRLF = "upload_save_create_preserves_crlf"
CHECK_NAME_UPDATE_CRLF = "upload_save_update_preserves_crlf"
CHECK_NAME_GZIP_CRLF = "upload_save_gzip_preserves_crlf"
CHECK_NAME_MIXED = "upload_save_preserves_mixed_line_endings"

# 20 bytes; stored as 17 by the unfixed server (the bug report's own payload).
_CRLF_PAYLOAD = b"alpha\r\nbeta\r\ngamma\r\n"
# CRLF, lone CR, bare LF, and a final line with no terminator at all: any
# text-mode read collapses the first two, any text-mode write can append or
# translate the last.
_MIXED_PAYLOAD = b"crlf\r\ncr\rlf\n\r\nno-trailing-newline"


def _outcome(name: str, status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map every check returns.

    Args:
        name: The check's unique name (one of the ``CHECK_NAME_*`` constants).
        status: Outcome status for the check.
        reason: Human-readable explanation of the result.

    Returns:
        ``{name: CommandOutcome(...)}``, the shape ``run_lifecycles`` merges.
    """
    return {name: CommandOutcome(name, Bucket.BUCKET_A, status, reason)}


def _no_session_skip(name: str) -> Dict[str, CommandOutcome]:
    """Return an EXPECTED_ERROR skip outcome when fixture seeding never ran.

    Args:
        name: The check's unique name.

    Returns:
        ``{name: CommandOutcome(...)}`` classified as a legitimate skip.
    """
    return _outcome(
        name, Status.EXPECTED_ERROR, "skipped: no fixture session_id available"
    )


async def _download_bytes(
    client: CodeAnalysisAsyncClient,
    fixtures: FixtureContext,
    file_id: str,
) -> bytes:
    """Read one indexed project file back as raw bytes through the real download path.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.
        file_id: ``files.id`` of the file to read back.

    Returns:
        The exact bytes the server streamed for that file.
    """
    dest = Path(tempfile.gettempdir()) / f"byte_fidelity_{uuid.uuid4().hex}.bin"
    try:
        await client.file_sessions.download(
            str(fixtures.session_id), dest, file_id, compression="identity"
        )
        return dest.read_bytes()
    finally:
        dest.unlink(missing_ok=True)


def _verdict(
    name: str,
    sent: bytes,
    stored: bytes,
    context: str,
) -> Dict[str, CommandOutcome]:
    """Compare sent and stored bytes and classify the result.

    Args:
        name: The check's unique name.
        sent: Bytes handed to the save path.
        stored: Bytes the server returned on read-back.
        context: Short description of the path exercised (create/update/gzip).

    Returns:
        ``{name: CommandOutcome(...)}`` -- EXECUTED_OK on an exact match,
        FAILED (with both byte strings and lengths) on any difference.
    """
    if stored == sent:
        return _outcome(
            name,
            Status.EXECUTED_OK,
            f"{context}: {len(sent)} bytes in, {len(stored)} bytes out, byte-identical",
        )
    return _outcome(
        name,
        Status.FAILED,
        (
            f"{context}: save altered the content -- sent {len(sent)} bytes "
            f"{sent!r}, stored {len(stored)} bytes {stored!r} (bug 44724d35)"
        ),
    )


async def _create_and_compare(
    client: CodeAnalysisAsyncClient,
    fixtures: FixtureContext,
    *,
    name: str,
    payload: bytes,
    rel_path: str,
    compression: str,
    context: str,
) -> Dict[str, CommandOutcome]:
    """Create a new project file from ``payload`` and assert the stored bytes match.

    With ``compression="gzip"`` the transfer contract expects PLAINTEXT input:
    the client checksums ``payload`` and only then compresses it for the
    wire; the server verifies the declared checksum against the decompressed
    buffer and the save path decompresses it once more before writing. So
    ``payload`` is passed to ``upload_new`` unmodified here, exactly like the
    identity branch -- pre-compressing it before the call would make the
    client gzip already-gzipped bytes, and the save path's single
    decompression would then hand back garbage instead of the original text.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.
        name: The check's unique name.
        payload: Bytes the file must end up containing.
        rel_path: Project-relative path for the new file.
        compression: Transfer compression (``identity`` or ``gzip``).
        context: Short description of the path exercised, used in the reason.

    Returns:
        ``{name: CommandOutcome(...)}`` for the comparison.
    """
    if not fixtures.session_id:
        return _no_session_skip(name)
    try:
        file_id = await client.file_sessions.upload_new(
            str(fixtures.session_id),
            payload,
            fixtures.project_id,
            rel_path,
            compression=compression,
        )
        stored = await _download_bytes(client, fixtures, str(file_id))
    except Exception as exc:  # noqa: BLE001 - a broken step is a real failure here
        return _outcome(name, Status.FAILED, truncate(repr(exc)))
    return _verdict(name, payload, stored, context)


async def run_create_preserves_crlf(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Bug 44724d35: create-mode save must store CRLF bytes verbatim.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME_CREATE_CRLF: CommandOutcome(...)}``.
    """
    return await _create_and_compare(
        client,
        fixtures,
        name=CHECK_NAME_CREATE_CRLF,
        payload=_CRLF_PAYLOAD,
        rel_path=f"byte_fidelity_crlf_{uuid.uuid4().hex[:8]}.txt",
        compression="identity",
        context="create path (.txt, identity)",
    )


async def run_gzip_preserves_crlf(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Bug 44724d35: the gzip transfer branch must store CRLF bytes verbatim.

    The compressed branch decompresses the buffer through its own reader, so
    it needs its own coverage: a fix applied only to the plain branch would
    leave this one silently rewriting line endings.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME_GZIP_CRLF: CommandOutcome(...)}``.
    """
    return await _create_and_compare(
        client,
        fixtures,
        name=CHECK_NAME_GZIP_CRLF,
        payload=_CRLF_PAYLOAD,
        rel_path=f"byte_fidelity_gzip_{uuid.uuid4().hex[:8]}.md",
        compression="gzip",
        context="create path (.md, gzip)",
    )


async def run_mixed_line_endings(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Bug 44724d35: mixed CRLF/CR/LF and a missing trailing newline survive a save.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME_MIXED: CommandOutcome(...)}``.
    """
    return await _create_and_compare(
        client,
        fixtures,
        name=CHECK_NAME_MIXED,
        payload=_MIXED_PAYLOAD,
        rel_path=f"byte_fidelity_mixed_{uuid.uuid4().hex[:8]}.txt",
        compression="identity",
        context="create path (.txt, mixed terminators, no trailing newline)",
    )


async def run_update_preserves_crlf(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Bug 44724d35: update-mode (``file_id``) save must store CRLF bytes verbatim.

    Seeds an LF file first, then overwrites it with the CRLF payload, so the
    update path is exercised on an already-indexed row rather than a create.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME_UPDATE_CRLF: CommandOutcome(...)}``.
    """
    name = CHECK_NAME_UPDATE_CRLF
    if not fixtures.session_id:
        return _no_session_skip(name)
    rel_path = f"byte_fidelity_update_{uuid.uuid4().hex[:8]}.md"
    try:
        file_id: Optional[str] = await client.file_sessions.upload_new(
            str(fixtures.session_id),
            b"seed line one\nseed line two\n",
            fixtures.project_id,
            rel_path,
        )
        await client.file_sessions.upload(
            str(fixtures.session_id),
            _CRLF_PAYLOAD,
            str(file_id),
            project_id=fixtures.project_id,
            filename=Path(rel_path).name,
        )
        stored = await _download_bytes(client, fixtures, str(file_id))
    except Exception as exc:  # noqa: BLE001 - a broken step is a real failure here
        return _outcome(name, Status.FAILED, truncate(repr(exc)))
    return _verdict(name, _CRLF_PAYLOAD, stored, "update path (.md, file_id)")
