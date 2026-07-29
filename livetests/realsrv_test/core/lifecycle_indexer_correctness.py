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
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
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

    outcome, _data = await call_step_with_data(
        client,
        "git_add",
        {"project_id": project_id, "all": True},
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
    three call sites - each revision only appends a trailing comment line
    carrying a unique marker token after them, so the target/type/line shape
    of the three usages stays identical across revisions.

    Each stage+reindex cycle is independently confirmed to have actually
    re-run ``analyze_file`` (not silently skipped by its mtime-unchanged
    guard) via the SAME ``content_stale`` roundtrip signal
    ``realsrv_test.core.lifecycle_content_stale`` proves for bug 56c23bd9:
    ``git_pull_safe``'s own per-file mark sets ``content_stale=True`` without
    reindexing; a real ``analyze_file`` run (via ``sync_file_to_db_atomic``
    -> ``build_file_data_atomic_batches``) unconditionally clears it back to
    ``False`` as part of the same write. Searching the cycle's own marker
    token and checking ``content_stale`` before/after each
    ``update_indexes`` call rules out a false GREEN from a run that never
    actually reprocessed the file.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME_USAGES_IDEMPOTENT: outcome}`` -
        :attr:`Status.EXECUTED_OK` only when both ``update_indexes`` runs are
        confirmed (via ``content_stale`` clearing) to have really
        reprocessed the file, and the usage count after the second run
        equals the count after the first - both equal to the expected 3
        call sites (a 0-vs-0 "pass" would hide a broken fixture/check, not
        prove idempotence).
    """
    if not fixtures.session_id:
        return _no_session_skip(CHECK_NAME_USAGES_IDEMPOTENT)

    project_id = fixtures.project_id
    suffix = uuid.uuid4().hex[:8]
    target_name = f"idem_usage_target_{suffix}"
    caller_name = f"idem_usage_caller_{suffix}"
    relative_path = f"verify_usage_idem_{suffix}.py"
    expected_call_sites = 3
    marker1 = f"idxrevmarkerone{suffix}"
    marker2 = f"idxrevmarkertwo{suffix}"

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
    v2_content = (body + f"\n# revision: 2 {marker1}\n").encode("utf-8")
    v3_content = (body + f"\n# revision: 3 {marker2}\n").encode("utf-8")

    async def _content_stale_for_marker_once(
        token: str,
    ) -> Tuple[Status, Optional[bool], str]:
        """Run one search for a revision marker token; return the hit's content_stale flag.

        Args:
            token: Unique marker token embedded as a trailing comment in the
                revision this call expects to find.

        Returns:
            ``(Status.EXECUTED_OK, True|False, "")`` when the fixture file is
            found in the search results, ``(Status.EXECUTED_OK, None,
            reason)`` when the search succeeded but found no hit for it
            (cannot assert), or ``(other_status, None, reason)`` when the
            search call itself failed.
        """
        outcome, data = await call_step_with_data(
            client,
            "search",
            {
                "project_id": project_id,
                "query": token,
                "enable_semantic": False,
                "enable_grep": False,
            },
            ok_reason="content_stale probe search executed",
        )
        if outcome.status is not Status.EXECUTED_OK:
            return outcome.status, None, outcome.reason
        items = (data or {}).get("items")
        if not isinstance(items, list):
            items = []
        wanted_suffix = "/" + relative_path
        for row in items:
            if not isinstance(row, dict):
                continue
            candidate = str(
                row.get("file_path") or row.get("path") or ""
            ).replace("\\", "/")
            if candidate == relative_path or candidate.endswith(wanted_suffix):
                return Status.EXECUTED_OK, bool(row.get("content_stale")), ""
        return (
            Status.EXECUTED_OK,
            None,
            f"no search hit for marker {token!r} among {len(items)} result(s)",
        )

    async def _content_stale_for_marker(
        token: str,
        *,
        expected: bool,
        timeout: float = 6.0,
        interval: float = 1.0,
    ) -> Tuple[Status, Optional[bool], str]:
        """Bounded-poll :func:`_content_stale_for_marker_once` until it matches ``expected``.

        The fulltext ``search`` index (the only client-reachable source of
        ``content_stale``) has shown brief propagation lag immediately after
        a write in back-to-back staging cycles - a transient result here must
        not be mistaken for the real defect this check exists to prove. Polls
        a short, fixed number of times (never an unbounded/infinite retry)
        and returns the LAST observed result either once it matches
        ``expected`` or once the deadline passes.

        Args:
            token: Unique marker token to search for.
            expected: The ``content_stale`` value this call is waiting to see.
            timeout: Maximum seconds to poll before giving up.
            interval: Seconds to sleep between polls.

        Returns:
            Same shape as :func:`_content_stale_for_marker_once`.
        """
        deadline = time.monotonic() + timeout
        status, stale, reason = await _content_stale_for_marker_once(token)
        while status is not Status.EXECUTED_OK or stale is not expected:
            if time.monotonic() >= deadline:
                return status, stale, reason
            await asyncio.sleep(interval)
            status, stale, reason = await _content_stale_for_marker_once(token)
        return status, stale, reason

    try:
        file_id = await client.file_sessions.upload_new(
            fixtures.session_id,
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
            "git_add",
            {"project_id": project_id, "all": True},
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
        project_root=str(fixtures.project_root),
        session_id=fixtures.session_id,
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

    pre1_status, pre1_stale, pre1_reason = await _content_stale_for_marker(
        marker1, expected=True
    )
    if pre1_status is not Status.EXECUTED_OK or pre1_stale is not True:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            Status.FAILED,
            "stage cycle 1 did not leave the file content_stale=True before "
            f"the first update_indexes (status={pre1_status}, "
            f"stale={pre1_stale!r}, {pre1_reason}) - cannot trust the "
            "upcoming reindex-confirmation signal",
        )

    first_reindex, _data = await call_step_with_data(
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

    post1_status, post1_stale, post1_reason = await _content_stale_for_marker(
        marker1, expected=False
    )
    if post1_status is not Status.EXECUTED_OK or post1_stale is not False:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            Status.FAILED,
            "first update_indexes did not clear content_stale for the "
            f"fixture file (status={post1_status}, stale={post1_stale!r}, "
            f"{post1_reason}) - it was likely SKIPPED by the mtime-unchanged "
            "guard rather than really reprocessed, so the usage count below "
            "cannot be trusted as a real first pass",
        )

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
        project_root=str(fixtures.project_root),
        session_id=fixtures.session_id,
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

    pre2_status, pre2_stale, pre2_reason = await _content_stale_for_marker(
        marker2, expected=True
    )
    if pre2_status is not Status.EXECUTED_OK or pre2_stale is not True:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            Status.FAILED,
            "stage cycle 2 did not leave the file content_stale=True before "
            f"the second update_indexes (status={pre2_status}, "
            f"stale={pre2_stale!r}, {pre2_reason}) - cannot trust the "
            "upcoming reindex-confirmation signal",
        )

    second_reindex, _data = await call_step_with_data(
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

    post2_status, post2_stale, post2_reason = await _content_stale_for_marker(
        marker2, expected=False
    )
    if post2_status is not Status.EXECUTED_OK or post2_stale is not False:
        return _outcome(
            CHECK_NAME_USAGES_IDEMPOTENT,
            Status.FAILED,
            "second update_indexes did not clear content_stale for the "
            f"fixture file (status={post2_status}, stale={post2_stale!r}, "
            f"{post2_reason}) - it was likely SKIPPED by the mtime-unchanged "
            "guard rather than really reprocessed, so the usage count below "
            "cannot be trusted as a real second pass",
        )

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
            f"{target_name} after the FIRST (content_stale-confirmed real) "
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
            "confirmed (via content_stale clearing) to be a genuine "
            "reprocessing pass with the same 3 call sites (bug a586efdb: "
            "update_indexes never clears old usages before re-adding them)",
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
        "across two update_indexes runs",
    )
