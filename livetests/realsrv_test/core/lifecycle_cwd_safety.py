"""
The client must never touch files in the caller's working directory (bug c3fafbd4).

Registered as suite ``s19`` (``realsrv_test.suites.s19_cwd_safety``,
``SUITE_NAME = "cwdsafety"``).

Defect this suite exists for: ``FileSessionClient.upload_bytes`` staged the
payload at ``Path(filename)`` -- a relative path, i.e. inside the calling
process's current working directory -- and deleted it again afterwards. Since
the pipeline runs with the repository root as its working directory, this
suite's own sibling (``nonpy``, which seeds fixture files named
``pyproject.toml``, ``script.sh``, ``.gitignore`` and ``notes.md``) silently
OVERWROTE and DELETED the developer's own ``pyproject.toml`` and
``.gitignore`` on every full sweep -- while reporting success. The other two
names simply did not exist at the repo root, which is why the symptom always
looked like "exactly these two files vanish".

The check below is deliberately harmless: it plants a decoy under a name
nothing else uses, uploads a file with that same basename, and asserts the
decoy is still there, byte for byte. It never uses a real project filename,
and it removes its decoy whatever happens.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Dict

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext

CHECK_NAME_CWD_UNTOUCHED = "upload_does_not_touch_caller_cwd"

_DECOY_CONTENT = b"PRECIOUS: a file that belongs to whoever ran this pipeline\n"
_UPLOAD_CONTENT = b"# uploaded fixture, must land on the server only\n"


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


async def run_upload_does_not_touch_caller_cwd(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Bug c3fafbd4: an upload must leave the caller's working directory alone.

    Plants a decoy in the process's cwd, uploads a project file carrying the
    same basename, and asserts the decoy survives unchanged.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME_CWD_UNTOUCHED: CommandOutcome(...)}``.
    """
    name = CHECK_NAME_CWD_UNTOUCHED
    if not fixtures.session_id:
        return _outcome(
            name, Status.EXPECTED_ERROR, "skipped: no fixture session_id available"
        )

    basename = f"cwd_guard_{uuid.uuid4().hex[:12]}.md"
    decoy = Path.cwd() / basename
    if decoy.exists():
        return _outcome(
            name,
            Status.INCONCLUSIVE,
            f"decoy name {basename} unexpectedly already exists in {Path.cwd()}",
        )

    try:
        decoy.write_bytes(_DECOY_CONTENT)
    except OSError as exc:
        return _outcome(
            name,
            Status.INCONCLUSIVE,
            f"could not plant a decoy in the working directory: {truncate(repr(exc))}",
        )

    try:
        try:
            await client.file_sessions.upload_new(
                str(fixtures.session_id),
                _UPLOAD_CONTENT,
                fixtures.project_id,
                f"cwd_safety_{uuid.uuid4().hex[:8]}/{basename}",
            )
        except Exception as exc:  # noqa: BLE001 - a broken upload is a real failure
            return _outcome(name, Status.FAILED, truncate(repr(exc)))

        if not decoy.exists():
            return _outcome(
                name,
                Status.FAILED,
                (
                    f"uploading a file named {basename!r} DELETED the same-named "
                    f"file in the caller's working directory ({Path.cwd()}); the "
                    "client stages payloads in the cwd instead of a temp "
                    "directory (bug c3fafbd4)"
                ),
            )
        stored = decoy.read_bytes()
        if stored != _DECOY_CONTENT:
            return _outcome(
                name,
                Status.FAILED,
                (
                    f"uploading a file named {basename!r} OVERWROTE the same-named "
                    f"file in the caller's working directory ({Path.cwd()}): "
                    f"{len(_DECOY_CONTENT)} bytes became {len(stored)} bytes "
                    "(bug c3fafbd4)"
                ),
            )
    finally:
        try:
            decoy.unlink(missing_ok=True)
        except OSError:
            pass

    return _outcome(
        name,
        Status.EXECUTED_OK,
        (
            f"uploaded a file named {basename!r}; the same-named file in the "
            "caller's working directory was left untouched"
        ),
    )
