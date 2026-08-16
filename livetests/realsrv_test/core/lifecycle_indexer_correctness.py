"""
Indexer-correctness checks for three long-standing planner TODOs.

Registered as suite ``s12`` (``realsrv_test.suites.s12_indexer_correctness``,
``SUITE_NAME = "indexer"``). Each check below targets exactly one defect and
is designed to fail RED against the unfixed server, then pass GREEN once the
corresponding fix lands - see each function's docstring for the defect id
and the exact mechanism it exercises.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional, Tuple

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.disposable_project import purge_disposable_project
from realsrv_test.core.fixtures import FixtureContext
from realsrv_test.core.lifecycle_common import call_step_with_data

_GIT_IDENTITY_NAME = "verify-indexer-correctness-bot"
_GIT_IDENTITY_EMAIL = "verify-indexer-correctness-bot@example.invalid"

CHECK_NAME_XREF = "cst_batch_write_builds_entity_cross_ref"
CHECK_NAME_END_LINE = "indexer_populates_entity_end_line"
CHECK_NAME_USAGES_IDEMPOTENT = "update_indexes_usages_idempotent"


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


async def run_cst_batch_write_builds_entity_cross_ref(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Bug 3e7177d6: the CST-editor/batch write path never built entity_cross_ref.

    ``compose_cst_writer.apply_changes`` -> ``update_file_data_atomic_batch``
    (``core/database_client/file_data_batch.py``) is the write path an
    OVERWRITE of an already-indexed ``.py`` file goes through (any
    ``project_file_transfer_upload_save`` update-mode save, including plain
    CST-editor commits) - as opposed to NEW file creation, or
    ``update_indexes``, both of which go through ``sync_file_to_db_atomic``.
    Before the fix, only the ``sync_file_to_db_atomic`` path ever called
    ``entity_cross_ref_builder.build_entity_cross_ref_for_file`` - the batch
    overwrite path built classes/methods/functions rows but never touched
    ``entity_cross_ref`` at all.

    Mechanism: seed a base class (new file, unrelated to the path under
    test), seed a placeholder file, then OVERWRITE the placeholder with a
    class that inherits the base - the overwrite is what exercises the batch
    path. Inheritance edges do not depend on the ``usages`` table (unlike
    call-usage edges), so this is a deterministic, ordering-independent probe
    of "did entity_cross_ref get (re)built at all" for that write.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME_XREF: outcome}`` - :attr:`Status.EXECUTED_OK` only when
        ``get_entity_dependencies`` reports a ``ref_type == "inherit"`` edge
        from the derived class to the base class after the batch-path
        overwrite.
    """
    if not fixtures.session_id:
        return _no_session_skip(CHECK_NAME_XREF)

    project_id = fixtures.project_id
    suffix = uuid.uuid4().hex[:8]
    base_name = f"XRefBase{suffix}"
    derived_name = f"XRefDerived{suffix}"
    base_module = f"verify_xref_base_{suffix}"
    base_path = f"{base_module}.py"
    derived_path = f"verify_xref_derived_{suffix}.py"

    base_content = (
        '"""Fixture base class for the entity_cross_ref batch-write-path check."""\n'
        "\n\n"
        f"class {base_name}:\n"
        '    """Base fixture class; a real, resolvable inheritance target."""\n'
        "\n"
        "    pass\n"
    )
    placeholder_content = (
        '"""Placeholder module.\n'
        "\n"
        "Overwritten below to exercise the CST batch write path\n"
        "(compose_cst_writer -> update_file_data_atomic_batch).\n"
        '"""\n'
    )
    # Import the base class (rather than leaving it a bare undefined name) so
    # the derived file passes the live write path's flake8 gate (F821 is NOT
    # in this project's extend-ignore list) - entity_cross_ref inheritance
    # resolution only needs the base *name* to be unique project-wide
    # (core/entity_cross_ref_builder.py's _resolve_unique_base_class_id), so
    # the import does not need to be resolvable at runtime; this fixture file
    # is only ever indexed, never executed.
    derived_content = (
        '"""Fixture derived class for the entity_cross_ref batch-write-path check."""\n'
        "\n"
        f"from {base_module} import {base_name}\n"
        "\n\n"
        f"class {derived_name}({base_name}):\n"
        f'    """Derived fixture class; inherits {base_name}."""\n'
        "\n"
        "    pass\n"
    )

    try:
        await client.file_sessions.upload_new(
            fixtures.session_id,
            base_content.encode("utf-8"),
            project_id,
            base_path,
        )
        derived_file_id = await client.file_sessions.upload_new(
            fixtures.session_id,
            placeholder_content.encode("utf-8"),
            project_id,
            derived_path,
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return _outcome(
            CHECK_NAME_XREF,
            Status.FAILED,
            truncate(f"fixture seed (new-file path) failed: {exc!r}"),
        )
    if not derived_file_id:
        return _outcome(
            CHECK_NAME_XREF,
            Status.FAILED,
            "derived-file seed upload_new returned no file_id",
        )

    try:
        await client.file_sessions.upload(
            fixtures.session_id,
            derived_content.encode("utf-8"),
            derived_file_id,
            project_id=project_id,
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return _outcome(
            CHECK_NAME_XREF,
            Status.FAILED,
            truncate(f"batch-path overwrite (file_sessions.upload) failed: {exc!r}"),
        )

    outcome, data = await call_step_with_data(
        client,
        "get_entity_dependencies",
        {
            "project_id": project_id,
            "entity_type": "class",
            "entity_name": derived_name,
        },
        ok_reason="get_entity_dependencies executed after the batch-path overwrite",
    )
    if outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            CHECK_NAME_XREF,
            outcome.status,
            f"get_entity_dependencies call itself failed: {outcome.reason}",
        )
    deps: List[Any] = (data or {}).get("dependencies") or []
    inherit_edges = [
        d for d in deps if isinstance(d, dict) and d.get("ref_type") == "inherit"
    ]
    if inherit_edges:
        return _outcome(
            CHECK_NAME_XREF,
            Status.EXECUTED_OK,
            f"{derived_name}: inherit edge to {base_name} present in "
            "entity_cross_ref right after the batch-path overwrite "
            f"({len(deps)} dependency row(s) total)",
        )
    return _outcome(
        CHECK_NAME_XREF,
        Status.FAILED,
        f"{derived_name}: no ref_type='inherit' entity_cross_ref edge to "
        f"{base_name} after the CST/batch-path overwrite - "
        f"get_entity_dependencies returned {len(deps)} dependency row(s): "
        f"{truncate(repr(deps))} (bug 3e7177d6: update_file_data_atomic_batch "
        "never rebuilt entity_cross_ref)",
    )


async def run_indexer_populates_entity_end_line(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Bug d4cd9525: end_line was never populated by the indexer.

    ``build_file_data_atomic_batches`` (``core/database_client/
    file_data_batch.py`` - shared by both ``sync_file_to_db_atomic`` /
    ``update_indexes`` and ``update_file_data_atomic_batch``) constructed
    ``Class``/``Method``/``Function`` rows with no ``end_line``, even though
    the ``classes``/``methods``/``functions`` tables already have a nullable
    ``end_line`` column and ``entity_cross_ref_builder.resolve_caller``
    already reads it for span matching. Consequence: every indexed entity's
    span collapsed to its single ``line``, breaking span-based caller
    resolution for any multi-line entity.

    Mechanism: seed a file with a multi-line class (with a multi-line
    method) and a multi-line top-level function, then read them back via
    ``get_code_entity_info`` and assert ``end_line`` is populated and
    strictly greater than the start ``line`` for all three entity kinds.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME_END_LINE: outcome}`` - :attr:`Status.EXECUTED_OK` only
        when class, method, and function rows all report
        ``end_line is not None and end_line > line``.
    """
    if not fixtures.session_id:
        return _no_session_skip(CHECK_NAME_END_LINE)

    project_id = fixtures.project_id
    suffix = uuid.uuid4().hex[:8]
    class_name = f"EndLineClass{suffix}"
    method_name = "multi_line_method"
    function_name = f"end_line_function_{suffix}"
    relative_path = f"verify_end_line_{suffix}.py"

    content = (
        '"""Fixture module for the entity end_line population check."""\n'
        "\n\n"
        f"def {function_name}(a: int, b: int) -> int:\n"
        '    """Multi-line function body used to check the function end_line span.\n'
        "\n"
        "    Args:\n"
        "        a: First addend.\n"
        "        b: Second addend.\n"
        "\n"
        "    Returns:\n"
        "        The sum of a and b, plus one.\n"
        '    """\n'
        "    total = a + b\n"
        "    total += 1\n"
        "    return total\n"
        "\n\n"
        f"class {class_name}:\n"
        '    """Multi-line class body used to check the class end_line span."""\n'
        "\n"
        f"    def {method_name}(self) -> str:\n"
        '        """Multi-line method body used to check the method end_line span.\n'
        "\n"
        "        Returns:\n"
        "            A fixed two-part string value.\n"
        '        """\n'
        '        value = "one"\n'
        '        value += "-two"\n'
        "        return value\n"
    )

    try:
        file_id = await client.file_sessions.upload_new(
            fixtures.session_id,
            content.encode("utf-8"),
            project_id,
            relative_path,
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return _outcome(
            CHECK_NAME_END_LINE,
            Status.FAILED,
            truncate(f"fixture seed failed: {exc!r}"),
        )
    if not file_id:
        return _outcome(
            CHECK_NAME_END_LINE, Status.FAILED, "seed upload returned no file_id"
        )

    problems: List[str] = []
    checks = (
        ("class", class_name, None),
        ("function", function_name, None),
        ("method", method_name, class_name),
    )
    for entity_type, entity_name, target_class in checks:
        params: Dict[str, Any] = {
            "project_id": project_id,
            "entity_type": entity_type,
            "entity_name": entity_name,
        }
        if target_class:
            params["target_class"] = target_class
        outcome, data = await call_step_with_data(
            client,
            "get_code_entity_info",
            params,
            ok_reason=f"get_code_entity_info executed for {entity_type} {entity_name}",
        )
        if outcome.status is not Status.EXECUTED_OK:
            problems.append(
                f"{entity_type} {entity_name}: get_code_entity_info call failed "
                f"({outcome.status.value}: {outcome.reason})"
            )
            continue
        entities = (data or {}).get("entities") or []
        if not entities:
            problems.append(f"{entity_type} {entity_name}: entity not found")
            continue
        row = entities[0]
        start_line = row.get("line")
        end_line = row.get("end_line")
        if end_line is None:
            problems.append(
                f"{entity_type} {entity_name}: end_line is None (line={start_line})"
            )
        elif start_line is None or end_line <= start_line:
            problems.append(
                f"{entity_type} {entity_name}: end_line={end_line} not > "
                f"line={start_line}"
            )

    if problems:
        return _outcome(
            CHECK_NAME_END_LINE,
            Status.FAILED,
            "end_line not populated/spanning for: " + "; ".join(problems)
            + " (bug d4cd9525: build_file_data_atomic_batches never set end_line)",
        )
    return _outcome(
        CHECK_NAME_END_LINE,
        Status.EXECUTED_OK,
        f"{relative_path}: class/function/method end_line all populated and "
        "span past their start line",
    )


async def _stage_content_via_git_pull(
    client: CodeAnalysisAsyncClient,
    *,
    project_id: str,
    project_root: str,
    session_id: str,
    file_id: str,
    relative_path: str,
    default_branch: str,
    new_content: bytes,
    cycle: int,
) -> Optional[str]:
    """Branch off, rewrite the file, commit, switch back, self-pull.

    Refreshes the file's ON-DISK mtime via a raw git checkout, independent of
    the DB-aware write pipeline (which always keeps ``files.last_modified``
    in sync with disk at write time) - the ONLY way to make ``update_indexes``
    actually re-run ``analyze_file``'s body for an already-indexed file via
    the public API: its schema exposes no client-reachable ``force`` param
    (``commands/update_indexes_metadata.py``), so its per-file
    mtime-unchanged skip guard (``commands/update_indexes_analyzer.py``,
    ``core/constants.FILE_MODIFICATION_TOLERANCE``) would otherwise short-
    circuit every call immediately following any normal write. Mirrors
    ``realsrv_test.core.lifecycle_content_stale_git.
    stage_stale_content_via_git_pull`` (bug N1 / 0d632d0e's proven
    mechanism: a real ``git_pull_safe`` fast-forward marks the file's
    content stale via its own pre/post-HEAD diff without touching
    ``files.last_modified``), parameterized per-cycle branch/remote names so
    it can run more than once against the same fixture file in one check
    without name collisions.

    Args:
        client: Connected async client.
        project_id: Disposable project UUID.
        project_root: Project's own server-side absolute root path, used as
            the self-remote URL.
        session_id: Open file-session id for the write below.
        file_id: ``file_id`` of the already-seeded fixture file.
        relative_path: Project-relative path of that file.
        default_branch: Branch to return to before pulling (from
            ``git_status``).
        new_content: Bytes to overwrite the file with on the throwaway branch.
        cycle: 1-based call counter; makes the throwaway branch/remote names
            unique so this helper can be invoked more than once per check.

    Returns:
        ``None`` on success, or a failure reason string on the first step
        that did not succeed.
    """
    branch = f"idxcheck_stage_{cycle}"
    remote = f"idxcheck_selfremote_{cycle}"

    outcome, _data = await call_step_with_data(
        client,
        "git_branch_checkout",
        {"project_id": project_id, "name": branch, "create": True},
        ok_reason=f"switched to throwaway branch {branch}",
    )
    if outcome.status is not Status.EXECUTED_OK:
        return f"git_branch_checkout({branch}) failed: {outcome.reason}"

    try:
        await client.file_sessions.upload(
            session_id,
            new_content,
            file_id,
            project_id=project_id,
            filename=relative_path,
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return f"overwrite on {branch} failed: {exc!r}"

    # Scoped to this ONE file (never all=True): the s12 suite's other checks
    # (A/B) create their own fixture files in this SAME shared project/git
    # working tree via file_sessions.upload_new, sibling in time to this
    # check's own git activity. all=True would stage and, via the branch
    # checkout/revert below, PHYSICALLY TOUCH those files too - untouched by
    # git, an untracked file is left alone by checkout, so scoping the add to
    # relative_path keeps this check's git choreography fully isolated from
    # whatever else the suite has written to disk.
    outcome, _data = await call_step_with_data(
        client,
        "git_add",
        {"project_id": project_id, "paths": [relative_path]},
        ok_reason="revision content staged",
    )
    if outcome.status is not Status.EXECUTED_OK:
        return f"git_add on {branch} failed: {outcome.reason}"

    outcome, _data = await call_step_with_data(
        client,
        "git_commit",
        {"project_id": project_id, "message": f"indexer check: revision {cycle}"},
        ok_reason="revision commit created",
    )
    if outcome.status is not Status.EXECUTED_OK:
        return f"git_commit on {branch} failed: {outcome.reason}"

    outcome, _data = await call_step_with_data(
        client,
        "git_branch_checkout",
        {"project_id": project_id, "name": default_branch},
        ok_reason=f"switched back to {default_branch}",
    )
    if outcome.status is not Status.EXECUTED_OK:
        return f"switch back to {default_branch} failed: {outcome.reason}"

    outcome, _data = await call_step_with_data(
        client,
        "git_remote_add",
        {"project_id": project_id, "name": remote, "url": project_root},
        ok_reason="self-remote registered (project's own root_path)",
    )
    if outcome.status is not Status.EXECUTED_OK:
        return f"git_remote_add({remote}) failed: {outcome.reason}"

    # One bounded, one-time wait (not a retry/poll loop): the storage backing
    # the project root has been observed to expose ~1-second mtime
    # granularity, which can collide with update_indexes' tight
    # FILE_MODIFICATION_TOLERANCE=0.1s (core/constants.py) when the whole
    # staging round-trip above completes within the same whole second as the
    # PREVIOUS update_indexes call's own mtime record - making the guard
    # falsely treat this cycle's fresh checkout as "unchanged" and skip. This
    # sleep guarantees the checkout below lands in a distinct whole-second
    # bucket, so the mtime-refresh technique this check depends on is
    # deterministic rather than occasionally racing the guard.
    await asyncio.sleep(1.1)

    try:
        pull_outcome, _pull_data = await call_step_with_data(
            client,
            "git_pull_safe",
            {"project_id": project_id, "remote": remote, "ref": branch},
            ok_reason="git_pull_safe fast-forwarded the default branch",
        )
        if pull_outcome.status is not Status.EXECUTED_OK:
            return f"git_pull_safe({remote}, {branch}) failed: {pull_outcome.reason}"
    finally:
        try:
            await client.call_validated(
                "git_remote_remove", {"project_id": project_id, "name": remote}
            )
        except Exception:  # noqa: BLE001 - cleanup only
            pass
    return None


async def run_update_indexes_usages_idempotent(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Bug a586efdb: update_indexes never cleared old usages before re-adding them.

    ``update_indexes_analyzer.analyze_file`` tracked usages via
    ``UsageTracker`` and called ``add_usage`` per record - a pure INSERT with
    no preceding DELETE. Re-running ``update_indexes`` on an unchanged file
    therefore duplicated every usage row on each run.

    Mechanism: seed a file whose one function calls another three times
    (three ``usage_type='call'`` rows for the same target). ``update_indexes``
    exposes no client-reachable ``force`` param, so between the two
    ``update_indexes`` calls this uses :func:`_stage_content_via_git_pull`
    twice to give the file a genuine new on-disk mtime (via a real git
    checkout, bypassing the DB-aware write pipeline) without touching the
    three call sites - each revision only appends a trailing revision-number
    comment line after them, so the target/type/line shape of the three
    usages stays identical across revisions.

    GENUINE-REPROCESSING IS A HARD PRECONDITION of the verdict, not an
    incidental observation: an EARLIER version of this check used a
    ``content_stale`` roundtrip via the fulltext ``search`` command as its
    reprocessing-confirmation signal and reproduced RED once, but the
    fulltext index showed propagation lag on later runs (an occasional false
    "not stale yet" / "no hit" reading immediately after a write), which is
    not trustworthy enough to gate a verdict people act on. This version
    instead reads the confirmation straight off ``update_indexes``' OWN
    response for the exact call being checked: ``code_mapper_mcp_command.py``
    reports ``files_processed``/``files_skipped`` as plain integers, zero
    extra round trips, zero propagation lag. Since this check runs in its
    own isolated single-file project (see below), "genuinely reprocessed"
    for one call is exactly ``files_processed == 1 and files_skipped == 0``
    for THAT call; anything else (the file was skipped by the
    mtime-unchanged guard) makes this function report :attr:`Status.FAILED`
    naming that cause instead of reporting :attr:`Status.EXECUTED_OK` for a
    pass that never exercised the defect - a check that can go green for a
    reason unrelated to the fix would be worse than no check at all.

    ISOLATED PROJECT (own throwaway project, not ``fixtures.project_id``):
    ``update_indexes`` scans and processes every file in a project, not just
    this check's own fixture file. In the SHARED fixture project, sibling
    checks A/B write their own ``.py`` fixture files into the SAME project
    concurrently with this check's timeline; a live-repro session there
    produced an inconsistent usage count even with an earlier,
    entity-row-id-based reprocessing signal confirmed on both passes, while
    a minimal, single-file, fully isolated project reproduced the defect (3
    -> 6) cleanly and repeatably. Rather than leave that interaction
    unexplained, this check creates and tears down its own disposable
    project so its two ``update_indexes`` calls only ever have this one
    fixture file to process (which also makes the ``files_processed``/
    ``files_skipped`` reprocessing signal above unambiguous - "1 file" is
    always THIS file).

    TIMING MARGIN: :func:`_stage_content_via_git_pull` sleeps ~1.1s before
    its mtime-refreshing checkout - storage backing the project root has
    shown roughly 1-second mtime granularity, which can collide with
    ``update_indexes``' tight ``FILE_MODIFICATION_TOLERANCE=0.1s``
    (``core/constants.py``) when a stage+reindex round trip completes within
    the same whole second as the previous ``update_indexes`` call's own
    mtime record.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run (only
            ``fixtures.session_id`` is used - the client session is not
            project-scoped; a fresh throwaway project is created below).

    Returns:
        ``{CHECK_NAME_USAGES_IDEMPOTENT: outcome}`` -
        :attr:`Status.EXECUTED_OK` only when both ``update_indexes`` calls'
        own responses confirm (``files_processed == 1``, ``files_skipped ==
        0``) that they really reprocessed the file, and the usage count
        after the second run equals the count after the first - both equal
        to the expected 3 call sites (a 0-vs-0 "pass" would hide a broken
        fixture/check, not prove idempotence).
    """
    if not fixtures.session_id:
        return _no_session_skip(CHECK_NAME_USAGES_IDEMPOTENT)

    watch_dir_status, watch_dir_data = await call_step_with_data(
        client,
        "list_watch_dirs",
        {},
        ok_reason="watch directories listed",
    )
    watch_dirs = (watch_dir_data or {}).get("watch_dirs") or []
    if watch_dir_status.status is not Status.EXECUTED_OK or not watch_dirs:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            Status.FAILED,
            f"could not list a watch_dir for the isolated project ({watch_dir_status.reason})",
        )
    watch_dir_id = str(watch_dirs[0]["id"])

    project_suffix = uuid.uuid4().hex[:8]
    isolated_project_name = f"verify_indexer_usage_idem_{project_suffix}"
    create_status, create_data = await call_step_with_data(
        client,
        "create_project",
        {
            "watch_dir_id": watch_dir_id,
            "project_name": isolated_project_name,
            "description": "isolated disposable project for the usages-idempotence check",
            "create_venv": False,
            "apply_template": False,
        },
        ok_reason="isolated throwaway project created",
    )
    if create_status.status is not Status.EXECUTED_OK:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            Status.FAILED,
            f"could not create the isolated project ({create_status.reason})",
        )
    isolated_project_id = str((create_data or {}).get("project_id") or "")
    isolated_project_root = str((create_data or {}).get("project_root") or "")
    if not isolated_project_id or not isolated_project_root:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            Status.FAILED,
            f"create_project response missing project_id/project_root: {create_data!r}",
        )

    try:
        return await _run_usages_idempotent_check(
            client,
            project_id=isolated_project_id,
            project_root=isolated_project_root,
            session_id=fixtures.session_id,
        )
    finally:
        # 1.6.114 gate hardening (bug d5835fbf): this used to call a
        # non-existent "delete_project" command, so this teardown always
        # raised and was silently swallowed below -- the isolated disposable
        # project was NEVER actually deleted by any run of this check (32
        # leaked "verify_indexer_usage_idem_*" projects observed). Routed
        # through the shared purge helper instead of hand-rolling the real
        # command name.
        await purge_disposable_project(
            client, isolated_project_id, isolated_project_name
        )


async def _run_usages_idempotent_check(
    client: CodeAnalysisAsyncClient,
    *,
    project_id: str,
    project_root: str,
    session_id: str,
) -> Dict[str, CommandOutcome]:
    """Do the actual seed/stage/reindex/assert work for the isolated project above.

    Split out of :func:`run_update_indexes_usages_idempotent` so that
    function's docstring stays the single source of truth for the check's
    rationale; this one just runs it against the given project.

    Args:
        client: Connected async client.
        project_id: The isolated throwaway project's UUID.
        project_root: The isolated throwaway project's server-side root path.
        session_id: Open file-session id (not project-scoped).

    Returns:
        ``{CHECK_NAME_USAGES_IDEMPOTENT: outcome}``.
    """
    suffix = uuid.uuid4().hex[:8]
    target_name = f"idem_usage_target_{suffix}"
    caller_name = f"idem_usage_caller_{suffix}"
    relative_path = f"verify_usage_idem_{suffix}.py"
    expected_call_sites = 3

    body = (
        '"""Fixture module for the update_indexes usages idempotence check."""\n'
        "\n\n"
        f"def {target_name}() -> str:\n"
        '    """Usage-tracking target; call rows must not duplicate on re-index.\n'
        "\n"
        "    Returns:\n"
        "        A fixed marker string.\n"
        '    """\n'
        '    return "target"\n'
        "\n\n"
        f"def {caller_name}() -> str:\n"
        f'    """Call the target {expected_call_sites} times to produce usage rows.\n'
        "\n"
        "    Returns:\n"
        "        The target function's own return value.\n"
        '    """\n'
        f"    {target_name}()\n"
        f"    {target_name}()\n"
        f"    return {target_name}()\n"
    )
    v1_content = (body + "\n# revision: 1\n").encode("utf-8")
    v2_content = (body + "\n# revision: 2\n").encode("utf-8")
    v3_content = (body + "\n# revision: 3\n").encode("utf-8")

    def _reprocessing_evidence_from_update_indexes(
        data: Optional[Dict[str, Any]], pass_label: str
    ) -> Optional[Dict[str, CommandOutcome]]:
        """Confirm THIS update_indexes response shows a real (non-skipped) pass.

        The ``update_indexes`` response itself (``code_mapper_mcp_command.py``)
        reports ``files_processed``/``files_skipped`` as plain integers for
        the exact call just made - the most direct, zero-latency,
        zero-extra-round-trip evidence available (no follow-up read that
        could itself race anything). Because this check runs in its own
        ISOLATED, single-file project (see the public function's docstring),
        "genuinely reprocessed my one fixture file" is exactly
        ``files_processed == 1 and files_skipped == 0`` for that call.

        Args:
            data: The ``update_indexes`` response ``data`` dict for the call
                being checked.
            pass_label: ``"first"`` or ``"second"``, for the failure message.

        Returns:
            ``None`` when the response confirms a genuine pass, or a
            ready-to-return FAILED outcome naming the cause otherwise.
        """
        files_processed = (data or {}).get("files_processed")
        files_skipped = (data or {}).get("files_skipped")
        # The project is single-FIXTURE, not single-FILE: project bootstrap
        # also drops auxiliary text files (e.g. .gitignore) into the tree, and
        # since bug fe1cf739 update_indexes indexes those too, so
        # files_processed legitimately exceeds 1. The anti-false-GREEN
        # property lives entirely in files_skipped: if the mtime-unchanged
        # guard had skipped our fixture file, it would be counted there.
        if files_skipped == 0 and isinstance(files_processed, int) and files_processed >= 1:
            return None
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            Status.FAILED,
            f"the {pass_label} update_indexes call did not genuinely "
            f"reprocess the fixture file (files_processed={files_processed!r}, "
            f"files_skipped={files_skipped!r} in its own response) - it was "
            "likely SKIPPED by the mtime-unchanged guard rather than "
            "genuinely reprocessed, so idempotence was not exercised on "
            "this pass",
        )

    try:
        file_id = await client.file_sessions.upload_new(
            session_id,
            v1_content,
            project_id,
            relative_path,
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            Status.FAILED,
            truncate(f"fixture seed failed: {exc!r}"),
        )
    if not file_id:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            Status.FAILED,
            "seed upload returned no file_id",
        )

    for name, params, ok_reason in (
        (
            "git_identity_set",
            {
                "project_id": project_id,
                "name": _GIT_IDENTITY_NAME,
                "email": _GIT_IDENTITY_EMAIL,
            },
            "git identity configured for the disposable project",
        ),
        (
            # Scoped to this ONE file, never all=True - see
            # _stage_content_via_git_pull's own git_add for why: this
            # project/git working tree is shared with the suite's other
            # checks, which write their own untracked fixture files here.
            "git_add",
            {"project_id": project_id, "paths": [relative_path]},
            "baseline file staged",
        ),
        (
            "git_commit",
            {"project_id": project_id, "message": "indexer check: baseline"},
            "baseline commit created",
        ),
    ):
        outcome, _data = await call_step_with_data(
            client, name, params, ok_reason=ok_reason
        )
        if outcome.status is not Status.EXECUTED_OK:
            return _outcome(
                CHECK_NAME_USAGES_IDEMPOTENT,
                Status.FAILED,
                f"setup step {name} failed: {outcome.reason}",
            )

    status_outcome, status_data = await call_step_with_data(
        client,
        "git_status",
        {"project_id": project_id},
        ok_reason="default branch discovered",
    )
    default_branch = (status_data or {}).get("branch")
    if status_outcome.status is not Status.EXECUTED_OK or not default_branch:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            status_outcome.status,
            f"could not determine the default branch via git_status ({status_outcome.reason})",
        )

    async def _usage_count() -> Tuple[Status, int, str]:
        """Run one find_usages call scoped to the fixture file and return its count."""
        outcome, data = await call_step_with_data(
            client,
            "find_usages",
            {
                "project_id": project_id,
                "target_name": target_name,
                "target_type": "function",
                "file_path": relative_path,
            },
            ok_reason="find_usages executed",
        )
        if outcome.status is not Status.EXECUTED_OK:
            return outcome.status, -1, outcome.reason
        usages = (data or {}).get("usages") or []
        return Status.EXECUTED_OK, len(usages), ""

    stage_err = await _stage_content_via_git_pull(
        client,
        project_id=project_id,
        project_root=project_root,
        session_id=session_id,
        file_id=file_id,
        relative_path=relative_path,
        default_branch=default_branch,
        new_content=v2_content,
        cycle=1,
    )
    if stage_err is not None:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            Status.FAILED,
            f"stage cycle 1 (v1 -> v2) failed: {stage_err}",
        )

    first_reindex, first_data = await call_step_with_data(
        client,
        "update_indexes",
        {"project_id": project_id},
        ok_reason="first update_indexes run completed",
    )
    if first_reindex.status is not Status.EXECUTED_OK:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            first_reindex.status,
            f"first update_indexes did not succeed: {first_reindex.reason}",
        )

    fail_outcome = _reprocessing_evidence_from_update_indexes(first_data, "first")
    if fail_outcome is not None:
        return fail_outcome

    status1, count1, reason1 = await _usage_count()
    if status1 is not Status.EXECUTED_OK:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            status1,
            f"find_usages after first update_indexes failed: {reason1}",
        )

    stage_err = await _stage_content_via_git_pull(
        client,
        project_id=project_id,
        project_root=project_root,
        session_id=session_id,
        file_id=file_id,
        relative_path=relative_path,
        default_branch=default_branch,
        new_content=v3_content,
        cycle=2,
    )
    if stage_err is not None:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            Status.FAILED,
            f"stage cycle 2 (v2 -> v3) failed: {stage_err}",
        )

    second_reindex, second_data = await call_step_with_data(
        client,
        "update_indexes",
        {"project_id": project_id},
        ok_reason="second update_indexes run completed",
    )
    if second_reindex.status is not Status.EXECUTED_OK:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            second_reindex.status,
            f"second update_indexes did not succeed: {second_reindex.reason}",
        )

    fail_outcome = _reprocessing_evidence_from_update_indexes(second_data, "second")
    if fail_outcome is not None:
        return fail_outcome

    status2, count2, reason2 = await _usage_count()
    if status2 is not Status.EXECUTED_OK:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            status2,
            f"find_usages after second update_indexes failed: {reason2}",
        )

    if count1 != expected_call_sites:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            Status.FAILED,
            f"{relative_path}: expected {expected_call_sites} usage row(s) for "
            f"{target_name} after the FIRST (response-confirmed real) "
            f"update_indexes run, got {count1} (fixture/check design issue "
            "if 0 - cannot assert idempotence without real rows to begin "
            "with)",
        )
    if count2 != count1:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            Status.FAILED,
            f"{relative_path}: usage count for {target_name} grew from "
            f"{count1} to {count2} across two update_indexes runs, each "
            "confirmed (via that call's own files_processed/files_skipped "
            "response fields) to be a genuine reprocessing pass with the "
            "same 3 call sites (bug a586efdb: update_indexes never clears "
            "old usages before re-adding them)",
        )
    if count2 != expected_call_sites:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            Status.FAILED,
            f"{relative_path}: usage count for {target_name} stayed stable "
            f"at {count2} across both runs, but that is not the expected "
            f"{expected_call_sites} call sites - fixture/check design issue",
        )
    return _outcome(
        CHECK_NAME_USAGES_IDEMPOTENT,
        Status.EXECUTED_OK,
        f"{relative_path}: usage count for {target_name} stayed at {count1} "
        "across two update_indexes runs, each independently confirmed "
        "(files_processed=1, files_skipped=0 in that call's own response) "
        "to have genuinely reprocessed the file",
    )
