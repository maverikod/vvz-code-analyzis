"""
Disposable-project fixture seeding for the live-server verifier.

Creates one throwaway project (via ``create_project``, minimal bootstrap —
no venv, no rules template, since this is a short-lived smoke fixture, not a
real workspace), opens one client session, then seeds one ``.py`` / ``.yaml``
/ ``.md`` file **through that session** via ``client.file_sessions.upload_new``
(the ``.py`` file also defines a class/method pair used by the entity-lookup
command lifecycle). ``project_root`` is a server-side absolute path — this
verifier runs on a workstation and never writes to it directly; every fixture
file is created via the real client upload path instead, the same way a real
client would create a new project file. Once the files exist, this module
gives the project a minimal real git history (``git_add`` + ``git_commit``,
git itself is initialized automatically by ``create_project``), waits for the
project to register in the database, and seeds a throwaway feature branch.
Teardown lives in ``_verify_client_all_commands_teardown.py`` (split out to
keep this module under the project's module-size guideline — CR-008).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_fixtures_registration import (
    resolve_seeded_file_ids,
    seed_feature_branch,
    wait_for_project_registered,
)

# SampleClass.sample_method calls greet() so entity dependency/usage lookups
# (get_code_entity_info, get_entity_dependencies/dependents, find_dependencies,
# find_usages, list_class_methods) have a real class/function/edge to report.
_PY_FIXTURE_CONTENT = (
    "def greet() -> str:\n"
    '    """Return a fixture greeting."""\n'
    '    return "hello"\n'
    "\n"
    "\n"
    "class SampleClass:\n"
    '    """Fixture class exercised by the entity-lookup command lifecycle."""\n'
    "\n"
    "    def sample_method(self) -> str:\n"
    '        """Return the fixture greeting via :func:`greet`."""\n'
    "        return greet()\n"
)
_YAML_FIXTURE_CONTENT = "key: value\n"
_MD_FIXTURE_CONTENT = "# Title\n\nVerify sweep fixture note.\n"

_PY_FIXTURE_RELPATH = "verify_module.py"
_YAML_FIXTURE_RELPATH = "verify_config.yaml"
_MD_FIXTURE_RELPATH = "verify_notes.md"

_SAMPLE_CLASS_NAME = "SampleClass"
_SAMPLE_METHOD_NAME = "sample_method"
_SAMPLE_FUNCTION_NAME = "greet"
_SAMPLE_MODULE_NAME = "verify_module"


@dataclass
class FixtureContext:
    """Disposable live-server fixture used as the target of the command sweep.

    Attributes:
        project_id: UUID4 of the disposable project.
        project_name: Directory/display name of the disposable project.
        watch_dir_id: UUID4 of the watch directory the project was created under.
        project_root: Absolute filesystem path to the project directory.
        py_file_path: Project-relative path to the seeded ``.py`` fixture file.
        yaml_file_path: Project-relative path to the seeded ``.yaml`` fixture file.
        md_file_path: Project-relative path to the seeded ``.md`` fixture file.
        session_id: UUID4 of the one client session opened for this run.
        files_seeded: True only if all three fixture files were uploaded
            through the client session (``project_file_transfer_upload_save``
            create mode via ``client.file_sessions.upload_new``).
        seed_error: Explanation of the fixture-file seeding failure, if any.
        warnings: Non-fatal issues collected while assembling the fixture.
        py_file_id: ``file_id`` of the seeded ``.py`` file, returned directly by
            ``upload_new`` (``None`` only if seeding failed and the
            ``list_project_files`` fallback also could not resolve it).
        yaml_file_id: ``file_id`` of the seeded ``.yaml`` file, likewise.
        md_file_id: ``file_id`` of the seeded ``.md`` file, likewise.
        feature_branch_name: Throwaway branch created for git_branch_compare /
            upstream / tracking commands.
        class_name: Name of the class seeded in the ``.py`` fixture.
        method_name: Name of the method seeded on ``class_name``.
        function_name: Name of the module-level function seeded in the ``.py``
            fixture (called by ``method_name``).
        module_name: Module name (no ``.py``) usable with ``run_project_module``.
    """

    project_id: str
    project_name: str
    watch_dir_id: str
    project_root: Path
    py_file_path: str = _PY_FIXTURE_RELPATH
    yaml_file_path: str = _YAML_FIXTURE_RELPATH
    md_file_path: str = _MD_FIXTURE_RELPATH
    session_id: Optional[str] = None
    files_seeded: bool = False
    seed_error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    py_file_id: Optional[str] = None
    yaml_file_id: Optional[str] = None
    md_file_id: Optional[str] = None
    feature_branch_name: str = ""
    class_name: str = _SAMPLE_CLASS_NAME
    method_name: str = _SAMPLE_METHOD_NAME
    function_name: str = _SAMPLE_FUNCTION_NAME
    module_name: str = _SAMPLE_MODULE_NAME


def _inner(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Unwrap a successful ``{"success": True, "data": {...}}`` envelope.

    Args:
        resp: Raw JSON-RPC command response.

    Returns:
        The ``data`` payload.

    Raises:
        RuntimeError: If ``resp`` does not report success.
    """
    if resp.get("success") is not True:
        raise RuntimeError(resp)
    data = resp.get("data")
    return data if isinstance(data, dict) else resp


async def _pick_watch_dir_id(client: CodeAnalysisAsyncClient) -> str:
    """Fetch the first available watch directory id via ``list_watch_dirs``.

    Args:
        client: Connected async client.

    Returns:
        A watch directory UUID4 suitable for ``create_project``.

    Raises:
        RuntimeError: If no watch directories are registered on the server.
    """
    resp = await client.call_validated("list_watch_dirs", {})
    data = _inner(resp)
    watch_dirs = data.get("watch_dirs") or []
    if not watch_dirs:
        raise RuntimeError("list_watch_dirs returned no watch directories")
    return str(watch_dirs[0]["id"])


async def _create_disposable_project(
    client: CodeAnalysisAsyncClient, project_prefix: str
) -> FixtureContext:
    """Create the throwaway project and return its :class:`FixtureContext`.

    Args:
        client: Connected async client.
        project_prefix: Prefix used to build a unique project name.

    Returns:
        A partially populated fixture context (files not seeded yet).

    Raises:
        RuntimeError: If ``create_project`` does not report success or omits
            a filesystem root path.
    """
    watch_dir_id = await _pick_watch_dir_id(client)
    project_name = f"{project_prefix}_{uuid.uuid4().hex[:8]}"
    resp = await client.call_validated(
        "create_project",
        {
            "watch_dir_id": watch_dir_id,
            "project_name": project_name,
            "description": "Disposable fixture for verify_client_all_commands_live.py",
            # Minimal bootstrap: this project lives for one sweep run only.
            "create_venv": False,
            "apply_template": False,
        },
    )
    data = _inner(resp)
    project_id = data.get("project_id")
    project_root_str = data.get("project_root")
    if not project_id or not project_root_str:
        raise RuntimeError(
            f"create_project response missing project_id/project_root: {data!r}"
        )
    return FixtureContext(
        project_id=str(project_id),
        project_name=project_name,
        watch_dir_id=watch_dir_id,
        project_root=Path(project_root_str),
    )


async def _upload_fixture_files(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> None:
    """Upload the ``.py`` / ``.yaml`` / ``.md`` fixture files through the client.

    Uses ``client.file_sessions.upload_new`` (create-mode
    ``project_file_transfer_upload_save``) so every fixture file is created the
    same way a real client would create it. ``fixtures.project_root`` is a
    server-side path never reachable from the workstation running this
    verifier, so it is never written to directly. Captures each returned
    ``file_id`` straight from ``upload_new`` on ``fixtures``.

    Args:
        client: Connected async client.
        fixtures: Fixture context with ``project_id``/``session_id`` already set.

    Raises:
        Exception: Propagated from the first failing upload (transport,
            validation, or server-side rejection) — the caller marks fixture
            seeding failed and records the error.
    """
    fixtures.py_file_id = await client.file_sessions.upload_new(
        fixtures.session_id,
        _PY_FIXTURE_CONTENT.encode("utf-8"),
        fixtures.project_id,
        fixtures.py_file_path,
    )
    fixtures.yaml_file_id = await client.file_sessions.upload_new(
        fixtures.session_id,
        _YAML_FIXTURE_CONTENT.encode("utf-8"),
        fixtures.project_id,
        fixtures.yaml_file_path,
    )
    fixtures.md_file_id = await client.file_sessions.upload_new(
        fixtures.session_id,
        _MD_FIXTURE_CONTENT.encode("utf-8"),
        fixtures.project_id,
        fixtures.md_file_path,
    )


async def _seed_git_history(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> None:
    """Stage and commit the seeded fixture files (best-effort, non-fatal).

    ``create_project`` already runs ``git init`` automatically; this only
    needs to produce one real commit so ``git_log``/``git_status``/``git_diff``
    style Bucket A commands have real history to inspect during the sweep.

    Args:
        client: Connected async client.
        fixtures: Fixture context with ``project_id`` already set.
    """
    try:
        add_resp = await client.call_validated(
            "git_add", {"project_id": fixtures.project_id, "all": True}
        )
        if not add_resp.get("success"):
            fixtures.warnings.append(f"git_add: {add_resp.get('error')!r}")
            return
        commit_resp = await client.call_validated(
            "git_commit",
            {
                "project_id": fixtures.project_id,
                "message": "verify sweep: seed fixture files",
            },
        )
        if not commit_resp.get("success"):
            fixtures.warnings.append(f"git_commit: {commit_resp.get('error')!r}")
    except Exception as exc:  # pragma: no cover - best-effort git bootstrap
        fixtures.warnings.append(f"git history seed failed: {exc!r}")


async def seed_fixtures(
    client: CodeAnalysisAsyncClient, project_prefix: str
) -> FixtureContext:
    """Create and populate the disposable project used as the sweep's target.

    Args:
        client: Connected async client (mTLS handshake already confirmed).
        project_prefix: Prefix used to build a unique disposable project name.

    Returns:
        A fully populated :class:`FixtureContext`.

    Raises:
        RuntimeError: If the project itself cannot be created — this is fully
            blocking since almost every Bucket A command needs ``project_id``.
    """
    fixtures = await _create_disposable_project(client, project_prefix)

    session_resp = await client.call_validated(
        "session_create", {"comment": "verify_client_all_commands_live sweep"}
    )
    session_data = _inner(session_resp)
    fixtures.session_id = str(session_data["session_id"])

    try:
        await _upload_fixture_files(client, fixtures)
        fixtures.files_seeded = True
    except Exception as exc:  # noqa: BLE001 - any upload failure marks seeding failed
        fixtures.seed_error = repr(exc)
        fixtures.warnings.append(f"fixture file seeding failed: {exc!r}")
        print(f"WARN  fixture file seeding failed: {exc!r}")

    if fixtures.files_seeded:
        await _seed_git_history(client, fixtures)
    else:
        fixtures.warnings.append("git history not seeded: no fixture files uploaded")

    # Bounded wait for the async DB-registration race (search / revectorize /
    # rebuild_faiss / repair_database / repair_worker_status / update_indexes
    # all 404 as "not found in database" if called before this resolves). Runs
    # after the upload above so the confirmation check has real files to work
    # with. Does not raise on timeout — it prints a warning and lets dependent
    # commands surface their own real errors instead of aborting the whole run.
    registered = await wait_for_project_registered(client, fixtures.project_id)
    if not registered:
        fixtures.warnings.append(
            "project registration not confirmed within the bounded wait; "
            "dependent commands may surface real 'not found in database' errors"
        )

    fixtures.feature_branch_name = f"verify_feature_{uuid.uuid4().hex[:8]}"
    await seed_feature_branch(client, fixtures)

    # Fallback only: upload_new already returned each file_id directly above.
    await resolve_seeded_file_ids(client, fixtures)

    return fixtures


# NOTE: teardown_fixtures() moved to _verify_client_all_commands_teardown.py
# (kept fixtures.py under the ~400-line module-size guideline — CR-008).
