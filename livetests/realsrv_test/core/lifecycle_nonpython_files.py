"""
Non-Python text-file indexing check (bug cluster 688d2d01 / 13945588 /
597ea8c5 / a51769dc / fe1cf739).

``update_indexes`` used to walk only ``.py`` files, so every other project
file -- ``pyproject.toml``, shell scripts, ``.gitignore``, plain text -- never
got a ``files`` row (no ``file_id`` -> AI Editor cannot lock it) and never got
``code_content`` (invisible to fulltext search). ``universal_file_preview``
also had no handler registered for ``.toml`` (``UNKNOWN_EXTENSION``).

This check seeds four whitelisted non-Python files under a throwaway
subdirectory unique to this run (never colliding with the ``.gitignore``
``create_project`` itself bootstraps at the project root -- reusing that
literal root path would risk a stale ``FILE_ALREADY_INDEXED`` rejection once
the fix is live and an earlier suite in the same pipeline run has already
called ``update_indexes``), runs ``update_indexes`` once, then asserts per
file:

(a) ``list_project_files`` (exact-path fast route) reports a non-null
    ``file_id``;
(b) the file's body -- carrying a run-unique token -- is visible to
    ``fulltext_search`` (a ``code_content`` proxy, following the same
    read-after-write convention as
    ``realsrv_test.core.lifecycle_fulltext_seeded``);

and, once, for the ``.toml`` file only:

(c) ``universal_file_preview`` succeeds (no ``UNKNOWN_EXTENSION``).

Conventions follow ``realsrv_test.core.lifecycle_list_files_fast.py`` /
``lifecycle_fulltext_seeded.py`` (single-check-family modules returning a
``{name: CommandOutcome}`` map, not one of the ordered
``lifecycle_common.call_step`` chains) -- reused here for the
``update_indexes`` step. Runs against the shared disposable project fixture
(no bespoke project of its own); teardown of that project is already the
pipeline's job (``realsrv_test.core.teardown``), so this module owns no
teardown of its own -- only the throwaway per-run file paths it creates,
which live and die with the disposable project.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext
from realsrv_test.core.lifecycle_common import call_step_with_data

_NAME_PREFIX = "nonpy"


@dataclass(frozen=True)
class _SeedFile:
    """One seeded non-Python whitelist fixture file."""

    outcome_key: str
    relative_path: str
    content: str
    token: str


def _build_seed_files(run_dir: str) -> List[_SeedFile]:
    """Build the four whitelist fixture files under a fresh throwaway subdir.

    Args:
        run_dir: Unique per-run subdirectory name (never previously indexed).

    Returns:
        One :class:`_SeedFile` per bug-cluster format (toml/sh/gitignore/md).
    """
    out: List[_SeedFile] = []
    for outcome_suffix, basename, comment_prefix in (
        ("pyproject_toml", "pyproject.toml", "#"),
        ("script_sh", "script.sh", "#"),
        ("gitignore", ".gitignore", "#"),
        ("notes_md", "notes.md", ""),
    ):
        token = f"verifynonpy{uuid.uuid4().hex}"
        if basename == "pyproject.toml":
            content = f'[tool.verify]\nname = "x"\n{comment_prefix} token: {token}\n'
        elif basename == "script.sh":
            content = f'#!/bin/sh\n{comment_prefix} token: {token}\necho "hi"\n'
        elif basename == ".gitignore":
            content = f"{comment_prefix} token: {token}\n*.pyc\n"
        else:
            content = f"# Notes\n\ntoken: {token}\n"
        out.append(
            _SeedFile(
                outcome_key=f"{_NAME_PREFIX}_{outcome_suffix}",
                relative_path=f"{run_dir}/{basename}",
                content=content,
                token=token,
            )
        )
    return out


def _path_in_hits(items: List[Any], relative_path: str) -> bool:
    """True if any fulltext hit's path matches ``relative_path``.

    Tolerates both the absolute ``file_path`` fulltext hits carry and a plain
    relative form (same tolerant-suffix rule as
    ``lifecycle_fulltext_seeded._seeded_path_in_hits`` / bug N1 / 0d632d0e
    Cause A -- duplicated here rather than imported to keep this a standalone,
    single-check module like its sibling).
    """
    wanted = relative_path.replace("\\", "/").lstrip("./")
    wanted_suffix = "/" + wanted
    for row in items:
        if not isinstance(row, dict):
            continue
        candidate = str(
            row.get("file_path") or row.get("path") or row.get("relative_path") or ""
        ).replace("\\", "/")
        if candidate == wanted or candidate.endswith(wanted_suffix):
            return True
    return False


def _outcome(key: str, status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification keyed by ``key``."""
    return {key: CommandOutcome(key, Bucket.BUCKET_A, status, reason)}


async def _seed_one_file(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext, seed: _SeedFile
) -> str:
    """Upload one seed file through the fixture session; return its error, if any."""
    try:
        await client.file_sessions.upload_new(
            fixtures.session_id,
            seed.content.encode("utf-8"),
            fixtures.project_id,
            seed.relative_path,
        )
    except Exception as exc:  # noqa: BLE001 - reported as a per-file outcome, not raised
        return repr(exc)
    return ""


async def _check_file_id_and_content(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext, seed: _SeedFile
) -> Dict[str, CommandOutcome]:
    """Assert (a) non-null file_id and (b) fulltext-visible code_content for one file."""
    list_outcome, list_data = await call_step_with_data(
        client,
        "list_project_files",
        {"project_id": fixtures.project_id, "file_pattern": seed.relative_path},
        ok_reason="list_project_files exact-path lookup completed",
    )
    if list_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            seed.outcome_key,
            Status.FAILED,
            f"list_project_files failed: {list_outcome.reason}",
        )
    rows = (list_data or {}).get("files") or (list_data or {}).get("items") or []
    file_id = rows[0].get("file_id") if rows else None
    if not file_id:
        return _outcome(
            seed.outcome_key,
            Status.FAILED,
            f"file_id is null/missing for {seed.relative_path!r} after "
            f"update_indexes (bug 688d2d01/13945588/597ea8c5): rows={rows!r}",
        )

    search_outcome, search_data = await call_step_with_data(
        client,
        "search",
        {
            "project_id": fixtures.project_id,
            "query": seed.token,
            "enable_semantic": False,
            "enable_grep": False,
        },
        ok_reason="fulltext token search completed",
    )
    if search_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            seed.outcome_key,
            Status.FAILED,
            f"file_id OK ({file_id}) but search call failed: {search_outcome.reason}",
        )
    items = (search_data or {}).get("items") or []
    if not _path_in_hits(items, seed.relative_path):
        return _outcome(
            seed.outcome_key,
            Status.FAILED,
            f"file_id OK ({file_id}) but code_content not fulltext-visible for "
            f"{seed.relative_path!r} (bug fe1cf739): 0 matching hits among "
            f"{len(items)} for token {seed.token!r}",
        )

    return _outcome(
        seed.outcome_key,
        Status.EXECUTED_OK,
        f"file_id={file_id!r} and code_content fulltext-visible for {seed.relative_path!r}",
    )


async def _check_toml_preview(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext, seed: _SeedFile
) -> Dict[str, CommandOutcome]:
    """Assert universal_file_preview succeeds on the seeded .toml file (bug a51769dc)."""
    key = f"{_NAME_PREFIX}_toml_preview"
    try:
        resp = await client.call_validated(
            "universal_file_preview",
            {"project_id": fixtures.project_id, "file_path": seed.relative_path},
        )
    except Exception as exc:  # noqa: BLE001 - reported as a check outcome, not raised
        return _outcome(key, Status.FAILED, truncate(f"call raised: {exc!r}"))
    if not resp.get("success"):
        return _outcome(
            key,
            Status.FAILED,
            truncate(f"universal_file_preview rejected .toml: {resp.get('error')!r}"),
        )
    return _outcome(key, Status.EXECUTED_OK, "universal_file_preview succeeded on .toml")


async def run_nonpython_files_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Seed pyproject.toml/script.sh/.gitignore/notes.md, index, then assert.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        One :class:`CommandOutcome` per file (file_id + code_content) plus one
        for the ``.toml`` preview check -- five entries total.
    """
    if not fixtures.session_id:
        return _outcome(
            f"{_NAME_PREFIX}_setup",
            Status.EXPECTED_ERROR,
            "skipped: no fixture session_id available",
        )

    run_dir = f"verify_nonpy_{uuid.uuid4().hex[:8]}"
    seeds = _build_seed_files(run_dir)

    seed_errors = []
    for seed in seeds:
        err = await _seed_one_file(client, fixtures, seed)
        if err:
            seed_errors.append(f"{seed.relative_path}: {err}")
    if seed_errors:
        return _outcome(
            f"{_NAME_PREFIX}_setup",
            Status.FAILED,
            truncate("seed upload failed: " + "; ".join(seed_errors)),
        )

    index_outcome, _index_data = await call_step_with_data(
        client,
        "update_indexes",
        {"project_id": fixtures.project_id},
        ok_reason="update_indexes completed after seeding the whitelist files",
    )
    if index_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            f"{_NAME_PREFIX}_setup",
            index_outcome.status,
            f"update_indexes did not succeed: {index_outcome.reason}",
        )

    outcomes: Dict[str, CommandOutcome] = {}
    for seed in seeds:
        outcomes.update(await _check_file_id_and_content(client, fixtures, seed))

    toml_seed = next(s for s in seeds if s.relative_path.endswith("pyproject.toml"))
    outcomes.update(await _check_toml_preview(client, fixtures, toml_seed))

    return outcomes
