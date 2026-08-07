"""Project-wide verification entrypoint."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class PipelineCheck:
    """Named verification unit exposed through the pipeline CLI."""

    name: str
    description: str
    pytest_targets: tuple[str, ...] = ()
    runner: Callable[[], int] | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _run_command(argv: Sequence[str]) -> int:
    completed = subprocess.run(
        list(argv),
        cwd=_repo_root(),
        check=False,
    )
    return int(completed.returncode)


def _pytest_command(pytest_targets: Sequence[str]) -> list[str]:
    return [sys.executable, "-m", "pytest", *pytest_targets]


def _run_pytest(pytest_targets: Sequence[str]) -> int:
    return _run_command(_pytest_command(pytest_targets))


def _resolve_live_verifier_ssl_paths() -> dict[str, str]:
    env = os.environ
    paths = {
        "cert": env.get("PIPELINE_LIVE_CERT", "/etc/casmgr/mtls/client.crt"),
        "key": env.get("PIPELINE_LIVE_KEY", "/etc/casmgr/mtls/client.key"),
        "ca": env.get("PIPELINE_LIVE_CA", "/etc/casmgr/mtls/ca.crt"),
    }
    missing = [name for name, raw_path in paths.items() if not Path(raw_path).exists()]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(
            "live-deployed-server requires readable mTLS files for "
            f"{joined}; override with PIPELINE_LIVE_CERT/KEY/CA if needed"
        )
    return paths


def _live_verifier_command(suite: str | None = None) -> list[str]:
    """Build the live-verifier subprocess argv.

    ``suite``, if given, is appended as a trailing positional argument. The
    shim (``scripts/verify_client_all_commands_live.py``) delegates to
    ``realsrv_test._cli.main_sync()``, whose parser accepts ``suites:
    nargs="*"`` positionals -- passing exactly one name runs only that suite
    instead of the full sweep (see ``realsrv_test._cli._async_main``:
    ``runners = collect_runners(requested or None)``, ``full_sweep=not
    requested``).
    """
    env = os.environ
    ssl_paths = _resolve_live_verifier_ssl_paths()
    host = env.get("PIPELINE_LIVE_HOST", "192.168.254.26")
    port = env.get("PIPELINE_LIVE_PORT", "15010")
    project_prefix = env.get("PIPELINE_LIVE_PROJECT_PREFIX", "pipeline_live")
    command = [
        sys.executable,
        "scripts/verify_client_all_commands_live.py",
        "--host",
        host,
        "--port",
        str(port),
        "--cert",
        ssl_paths["cert"],
        "--key",
        ssl_paths["key"],
        "--ca",
        ssl_paths["ca"],
        "--project-prefix",
        project_prefix,
    ]
    if suite:
        command.append(suite)
    return command


def _run_live_verifier(suite: str | None) -> int:
    """Run the live verifier (optionally scoped to one suite); exit code passthrough.

    Missing mTLS preconditions print the reason and return 2 (same contract
    as an unknown check name) -- this is the single-check invocation path;
    ``run_all()`` uses ``_attempt_live_deployed_server`` instead, which
    classifies this same condition as an explicit SKIP rather than a bare
    exit code.
    """
    try:
        command = _live_verifier_command(suite=suite)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return _run_command(command)


def _run_live_deployed_server() -> int:
    return _run_live_verifier(None)


def _run_live_nonpy() -> int:
    return _run_live_verifier("nonpy")


def _run_live_throughput() -> int:
    return _run_live_verifier("throughput")


def _run_live_indexer() -> int:
    return _run_live_verifier("indexer")


def _run_live_apisurface() -> int:
    return _run_live_verifier("apisurface")


def _run_live_sessions() -> int:
    return _run_live_verifier("sessions")


def _run_live_stability() -> int:
    return _run_live_verifier("stability")


def _run_live_client_overhead() -> int:
    return _run_live_verifier("client_overhead")


def _run_live_byte_fidelity() -> int:
    return _run_live_verifier("bytes")


_CHECKS: tuple[PipelineCheck, ...] = (
    PipelineCheck(
        name="pipeline-cli",
        description="Verify the pipeline CLI contract and console-script wiring.",
        pytest_targets=("tests/test_pipeline_cli.py",),
    ),
    PipelineCheck(
        name="lint-config",
        description="Verify lint_code respects repository flake8 configuration.",
        pytest_targets=("tests/test_code_quality_linter.py",),
    ),
    PipelineCheck(
        name="anchor-check",
        description="Verify replace_file_lines anchor writes still work without config.json.",
        pytest_targets=("tests/commands/test_anchor_check.py",),
    ),
    PipelineCheck(
        name="fs-grep",
        description="Verify fs_grep honors large-file guards without config.json.",
        pytest_targets=("tests/commands/test_fs_grep_command.py",),
    ),
    PipelineCheck(
        name="handler-registry",
        description="Verify handler registry suffix groups match the current product contract.",
        pytest_targets=("tests/file_handlers/test_registry.py",),
    ),
    PipelineCheck(
        name="batch-stable-id",
        description="Verify batch insert+replace preserves unrelated sibling stable_id values.",
        pytest_targets=("tests/test_batch_insert_replace_stable_id.py",),
    ),
    PipelineCheck(
        name="sibling-insert-stale-target",
        description="Verify sibling insert rejects stale target stable_id after the original node was deleted.",
        pytest_targets=("tests/test_sibling_insert_positioning.py",),
    ),
    PipelineCheck(
        name="install-config",
        description="Verify package install config finalizes registration.instance_uuid on first install.",
        pytest_targets=("tests/test_casmgr_install_server_config.py",),
    ),
    PipelineCheck(
        name="create-text-file",
        description="Verify create_text_file succeeds without a local config.json in isolated test contexts.",
        pytest_targets=("tests/test_create_text_file_command.py",),
    ),
    PipelineCheck(
        name="cst-save-tree",
        description="Verify cst_save_tree retry paths do not block the asyncio loop.",
        pytest_targets=("tests/test_cst_save_tree_command.py",),
    ),
    PipelineCheck(
        name="restore-watch-dirs",
        description="Verify restore watch-dir fallback works without a local active config.json.",
        pytest_targets=("tests/test_database_restore_watch_dirs_fallback.py",),
    ),
    PipelineCheck(
        name="docstring-batch-persist",
        description="Verify docstring chunk batch persistence does not hang on sync DB batch helpers.",
        pytest_targets=("tests/test_docstring_chunker_batch_persist.py",),
    ),
    PipelineCheck(
        name="invalid-open-preview",
        description="Verify universal_file_open works in isolated invalid-file preview flows without config.json.",
        pytest_targets=("tests/test_edit_on_invalid_files.py",),
    ),
    PipelineCheck(
        name="file-session-client",
        description="Verify FileSessionClient workflow helpers match the current session validation contract.",
        pytest_targets=("tests/test_file_session_client.py",),
    ),
    PipelineCheck(
        name="file-watcher-config",
        description="Verify file watcher runtime settings follow the mount-root watch-dir contract.",
        pytest_targets=("tests/test_file_watcher_watch_dirs_config.py",),
    ),
    PipelineCheck(
        name="get-file-lines",
        description=(
            "Verify the internal raw line-range reader (formerly the get_file_lines "
            "command, removed from the public surface per TODO a7091850; still used "
            "by read_project_text_file/universal_file_read routing) keeps "
            "INVALID_RANGE behavior in isolated contexts without config.json."
        ),
        pytest_targets=("tests/test_get_file_lines_validate.py",),
    ),
    PipelineCheck(
        name="fulltext-search",
        description="Verify fulltext result shape and prefix-query behavior.",
        pytest_targets=(
            "tests/unit/test_search_paginated_fulltext.py",
            "tests/test_domain_search_full_text_port.py",
            "tests/test_fulltext_driver_backend_config.py",
        ),
    ),
    PipelineCheck(
        name="mtime-reindex",
        description="Verify update_indexes reindexes files missing content rows.",
        pytest_targets=("tests/test_last_modified_indexing_and_file_row.py",),
    ),
    PipelineCheck(
        name="packaging-config",
        description="Verify packaging config template expectations.",
        pytest_targets=("tests/test_packaging_config_template.py",),
    ),
    PipelineCheck(
        name="git-branch-commands",
        description="Verify git branch command tests are isolated from broken global git config.",
        pytest_targets=("tests/test_git_branch_commands.py",),
    ),
    PipelineCheck(
        name="git-pull-safe-content-stale",
        description="Verify git_pull_safe stale-marking tests do not hardcode an invalid git PATH.",
        pytest_targets=("tests/test_git_pull_safe_content_stale.py",),
    ),
    PipelineCheck(
        name="info-command",
        description="Verify info command runtime metadata and single-source client versioning contracts stay aligned.",
        pytest_targets=(
            "tests/test_info_command.py",
            "tests/test_client_version_single_source.py",
        ),
    ),
    PipelineCheck(
        name="integrity-analysis",
        description="Verify integrity-analysis tests match the current docker asset layout.",
        pytest_targets=("tests/test_integrity_analysis.py",),
    ),
    PipelineCheck(
        name="json-save-tree",
        description="Verify json_save_tree isolated path-safety and happy-path tests do not hang on optional config/git logic.",
        pytest_targets=("tests/test_json_save_tree_command.py",),
    ),
    PipelineCheck(
        name="log-view-pagination",
        description="Verify log viewer pagination commands do not hang on async thread offload.",
        pytest_targets=("tests/test_log_view_pagination.py",),
    ),
    PipelineCheck(
        name="logical-write-submit",
        description="Verify async logical-write helpers do not leak asyncio default-executor teardown hangs.",
        pytest_targets=("tests/test_logical_write_submit.py",),
    ),
    PipelineCheck(
        name="main-loop-decoupling",
        description="Verify metadata-alignment setup does not leave global logging disabled before watchdog stall detection runs.",
        pytest_targets=(
            "tests/test_registered_commands_metadata_alignment.py",
            "tests/test_main_loop_decoupling.py",
        ),
    ),
    PipelineCheck(
        name="mcp-queue-regressions",
        description="Verify queue command-execution regressions keep config/bootstrap state available in child processes and skip cleanly when multiprocessing semaphores are unavailable in the sandbox.",
        pytest_targets=(
            "tests/test_base_mcp_command_resolve_config_path.py",
            "tests/test_mcp_queue_regressions.py",
            "tests/test_search_inline_timeout.py",
        ),
    ),
    PipelineCheck(
        name="openapi-jsonrpc-concurrency",
        description="Verify concurrent OpenAPI and JSON-RPC tests provision their own config and do not depend on a repo-root config.json.",
        pytest_targets=("tests/test_openapi_jsonrpc_concurrency.py",),
    ),
    PipelineCheck(
        name="processing-paused-projects",
        description="Verify set_project_processing_paused falls back cleanly when isolated tests run without a repo-root config.json.",
        pytest_targets=("tests/test_processing_paused_projects.py",),
    ),
    PipelineCheck(
        name="project-activity-locks-migrations",
        description="Verify PostgreSQL lock/session migration helpers commit once per idempotent ensure call.",
        pytest_targets=("tests/test_project_activity_locks_migrations.py",),
    ),
    PipelineCheck(
        name="project-pip-logging",
        description="Verify project pip session logs resolve server.log_dir from minimal local config fragments.",
        pytest_targets=("tests/test_project_pip_logging.py",),
    ),
    PipelineCheck(
        name="project-text-file-routing",
        description="Verify read_project_text_file keeps Python line-read routing compatible with project-relative resolver-based tests.",
        pytest_targets=("tests/test_project_text_file_commands.py",),
    ),
    PipelineCheck(
        name="query-cst-line-range",
        description="Verify query_cst line-range replacements do not require a repo-root config.json in isolated tests.",
        pytest_targets=("tests/test_query_cst/test_line_range_replace.py",),
    ),
    PipelineCheck(
        name="schema-core-uuid-migration",
        description="Verify PostgreSQL core UUID DDL preserves valid foreign keys that target UNIQUE watch_dirs.id.",
        pytest_targets=("tests/test_schema_core_uuid_migration.py",),
    ),
    PipelineCheck(
        name="schema-rest-uuid-migration",
        description="Verify PostgreSQL rest-table UUID DDL keeps foreign keys when referenced table definitions are not bundled into the local wrapped schema fixture.",
        pytest_targets=("tests/test_schema_rest_uuid_migration.py",),
    ),
    PipelineCheck(
        name="startup-reconciliation",
        description="Verify startup reconciliation isolated tests do not require a repo-root config.json for orphan-project purge paths.",
        pytest_targets=("tests/test_startup_reconciliation.py",),
    ),
    PipelineCheck(
        name="text-universal-edit-write-close",
        description="Verify universal_file_open/write preview-commit flows work with isolated database bundles that only expose project root objects.",
        pytest_targets=("tests/test_text_universal_edit_write_close.py",),
    ),
    PipelineCheck(
        name="preview-edit-addressing-all-formats",
        description="Verify active edit-session previews still return usable node refs across JSON/YAML/text/markdown formats.",
        pytest_targets=("tests/test_preview_edit_addressing_all_formats.py",),
    ),
    PipelineCheck(
        name="tree-temp-preview-navigation",
        description="Verify direct tree_temp_roots preview navigation keeps Sidecar stable-id drill-down compatibility.",
        pytest_targets=("tests/test_tree_temp_preview_navigation.py",),
    ),
    PipelineCheck(
        name="tree-temp-universal-json-preview-sessions",
        description="Verify JSON tree-temp preview session helpers work with isolated absolute-root project rows and preserve stable-id preview behavior.",
        pytest_targets=("tests/test_tree_temp_universal_json_preview_sessions.py",),
    ),
    PipelineCheck(
        name="tree-temp-universal-yaml-preview-sessions",
        description="Verify YAML stable-id preview sessions still route through tree-temp acquisition and sidecar focus compatibility paths.",
        pytest_targets=("tests/test_tree_temp_universal_yaml_preview_sessions.py",),
    ),
    PipelineCheck(
        name="universal-file-save-routing",
        description="Verify universal_file_save routing keeps isolated Python create/save flows working without a repo-root config.json.",
        pytest_targets=("tests/test_universal_file_save_command.py",),
    ),
    PipelineCheck(
        name="tree-temp-edit-session-preview",
        description="Verify active tree-temp edit sessions preview the draft via tree-temp handlers instead of marked-tree navigation.",
        pytest_targets=("tests/test_tree_temp_edit_session_preview.py",),
    ),
    PipelineCheck(
        name="transfer-lock-batch-commands",
        description="Verify transfer-by-id lock/download/upload flows survive adapter-bootstrap module reload order and isolated database doubles without a repo-root config.json.",
        pytest_targets=(
            "tests/test_mcp_adapter_bootstrap.py",
            "tests/test_transfer_lock_batch_commands.py",
        ),
    ),
    PipelineCheck(
        name="vectorization-uuid-sql-order",
        description="Verify UUID-era vectorization SQL still uses the real code_chunks ordering columns.",
        pytest_targets=("tests/test_vectorization_uuid_sql_order.py",),
    ),
    PipelineCheck(
        name="verify-lifecycle-content-stale-save",
        description="Verify the content_stale roundtrip stub matches the current git-based lifecycle harness contract.",
        pytest_targets=("tests/test_verify_lifecycle_content_stale_save.py",),
    ),
    PipelineCheck(
        name="watcher-project-metadata",
        description="Verify watcher projectid metadata refresh uses the database object's sync hook in isolated test contexts.",
        pytest_targets=("tests/test_watcher_project_metadata.py",),
    ),
    PipelineCheck(
        name="search-close-pagination",
        description="Verify search page/status read paths handle closed or missing sessions in configless isolated test contexts.",
        pytest_targets=(
            "tests/unit/test_search_close_command.py",
            "tests/unit/test_search_get_page_command.py",
            "tests/unit/test_search_get_status_command.py",
        ),
    ),
    PipelineCheck(
        name="byte-verbatim-io",
        description=(
            "Verify the transfer-buffer reader and the text save path store "
            "content byte-verbatim (bug 44724d35: CRLF was rewritten to LF)."
        ),
        pytest_targets=("tests/test_transfer_buffer_text_io.py",),
    ),
    PipelineCheck(
        name="trash-list-name-parse",
        description="Verify list_trashed_projects preserves original_name when unique-suffix trash folders are created.",
        pytest_targets=("tests/test_trash_list_name_parsing.py",),
    ),
    # "live-fixture-rename-sync" (verifies the live verifier keeps fixture
    # project_name/root in sync after rename_project roundtrips) existed in
    # casmgr:1.6.87 (built from an uncommitted tree, versions 1.6.84-87 exist
    # in no branch) but its test file, tests/test_live_fixture_rename_sync.py,
    # was never committed and its content could not be recovered from the
    # docker image diff alone. Deliberately NOT re-registered here -- doing so
    # would reference a nonexistent test file. Re-add once the test is
    # rewritten from a real spec, not guessed from a name.
    PipelineCheck(
        name="live-deployed-server",
        description="Run the mTLS all-commands verifier against the deployed CAS server.",
        runner=_run_live_deployed_server,
    ),
    # The checks below each run exactly ONE realsrv-test suite -- a strict
    # SUBSET of live-deployed-server's full sweep. They exist for targeted
    # post-deploy verification of one bug fix (e.g. "did suite throughput go
    # green after this deploy") without paying for the whole ~7 minute
    # sweep. Deliberately EXCLUDED from run_all() (see its docstring) for
    # exactly that reason: each would just re-run work live-deployed-server
    # already covers.
    PipelineCheck(
        name="live-nonpy",
        description=(
            "Run only the 'nonpy' realsrv-test suite against the deployed CAS "
            "server -- a subset of live-deployed-server."
        ),
        runner=_run_live_nonpy,
    ),
    PipelineCheck(
        name="live-throughput",
        description=(
            "Run only the 'throughput' realsrv-test suite against the deployed "
            "CAS server -- a subset of live-deployed-server."
        ),
        runner=_run_live_throughput,
    ),
    PipelineCheck(
        name="live-indexer",
        description=(
            "Run only the 'indexer' realsrv-test suite against the deployed CAS "
            "server -- a subset of live-deployed-server."
        ),
        runner=_run_live_indexer,
    ),
    PipelineCheck(
        name="live-apisurface",
        description=(
            "Run only the 'apisurface' realsrv-test suite against the deployed "
            "CAS server -- a subset of live-deployed-server."
        ),
        runner=_run_live_apisurface,
    ),
    PipelineCheck(
        name="live-sessions",
        description=(
            "Run only the 'sessions' realsrv-test suite against the deployed "
            "CAS server -- a subset of live-deployed-server. Proves an idle, "
            "closed search session actually gets swept (bug: data/search_sessions "
            "accumulated unbounded, measured 69 sessions / 56,505 files / 1.6GB "
            "locally with no expiry)."
        ),
        runner=_run_live_sessions,
    ),
    PipelineCheck(
        name="live-stability",
        description=(
            "Run only the 'stability' realsrv-test suite against the deployed "
            "CAS server -- a subset of live-deployed-server. Guards bug "
            "2aaac911's fix (the live pipeline's release gate must not give "
            "verdicts that depend on what else ran): asserts the "
            "ambient-load probe that gates the throughput suite's timing "
            "metrics correctly flags self-generated concurrent interference "
            "as degraded, quiet nothing else in flight."
        ),
        runner=_run_live_stability,
    ),
    PipelineCheck(
        name="live-client-overhead",
        description=(
            "Run only the 'client_overhead' realsrv-test suite against the "
            "deployed CAS server -- a subset of live-deployed-server. Guards "
            "bug 8e6acb34 Fix 1: asserts code_analysis_client's per-call "
            "overhead over a warm, connection-reused raw-httpx floor (the "
            "realistic fresh-process-per-call pattern) stays within a "
            "stated budget, so the on-disk schema cache regression does not "
            "silently come back."
        ),
        runner=_run_live_client_overhead,
    ),
    PipelineCheck(
        name="live-byte-fidelity",
        description=(
            "Run only the 'bytes' realsrv-test suite against the deployed CAS "
            "server -- a subset of live-deployed-server. Guards bug 44724d35: "
            "project_file_transfer_upload_save rewrote the line endings of the "
            "bytes it was given (20 bytes of CRLF stored as 17 bytes of LF, "
            "reported as success, with no opt-out). Asserts the create path, "
            "the file_id update path, and the gzip transfer branch all store "
            "the uploaded bytes verbatim."
        ),
        runner=_run_live_byte_fidelity,
    ),
)

_CHECKS_BY_NAME = {check.name: check for check in _CHECKS}
_FULL_SUITE_TARGETS: tuple[str, ...] = ("tests",)


def list_checks() -> tuple[PipelineCheck, ...]:
    """Return the immutable pipeline check catalog."""
    return _CHECKS


def _print_check_catalog() -> None:
    for check in _CHECKS:
        print(f"{check.name}\t{check.description}")


def run_check(check_name: str) -> int:
    """Run one named pipeline check."""
    check = _CHECKS_BY_NAME.get(check_name)
    if check is None:
        available = ", ".join(sorted(_CHECKS_BY_NAME))
        print(
            f"Unknown pipeline check: {check_name}. Available: {available}",
            file=sys.stderr,
        )
        return 2
    if check.runner is not None:
        return check.runner()
    return _run_pytest(check.pytest_targets)


@dataclass(frozen=True)
class RunAllResult:
    """Outcome of one component of a `run_all()` invocation.

    ``status`` is one of ``"passed"``, ``"failed"``, ``"skipped"``. A
    ``"skipped"`` component (its PRECONDITIONS were absent, e.g. no mTLS
    files on a dev machine) never fails the overall run by itself; a
    ``"failed"`` component (it DID run and came back nonzero) always does.
    """

    name: str
    status: str
    detail: str = ""


def _attempt_full_pytest_suite() -> RunAllResult:
    """Run every test in ``tests/`` for `run_all()`."""
    code = _run_pytest(_FULL_SUITE_TARGETS)
    if code == 0:
        return RunAllResult("full-pytest-suite", "passed")
    return RunAllResult("full-pytest-suite", "failed", f"pytest exit code {code}")


def _attempt_live_deployed_server() -> RunAllResult:
    """Run the full live sweep (``live-deployed-server``) for `run_all()`.

    Distinguishes a missing PRECONDITION (no mTLS files -- ``ValueError``
    from ``_resolve_live_verifier_ssl_paths``) as an explicit SKIP from a
    genuine FAIL (the verifier ran and returned nonzero). This mirrors
    ``_run_live_deployed_server`` (used by direct ``pipeline
    live-deployed-server`` invocations) but reports the distinction instead
    of collapsing both to the same bare exit code.
    """
    try:
        command = _live_verifier_command()
    except ValueError as exc:
        return RunAllResult("live-deployed-server", "skipped", str(exc))
    code = _run_command(command)
    if code == 0:
        return RunAllResult("live-deployed-server", "passed")
    return RunAllResult("live-deployed-server", "failed", f"verifier exit code {code}")


_STATUS_MARKERS = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}


def _print_run_all_summary(results: Sequence[RunAllResult]) -> None:
    """Print a per-component PASS/FAIL/SKIP summary for a `run_all()` invocation."""
    print()
    print("=== pipeline run-all summary ===")
    for result in results:
        marker = _STATUS_MARKERS[result.status]
        line = f"[{marker}] {result.name}"
        if result.detail:
            line += f" -- {result.detail}"
        print(line)


def run_all() -> int:
    """Run every test AND every check, per the pipeline contract.

    Concretely: the full pytest suite (``tests/``) PLUS the runner-based
    ``live-deployed-server`` check (the full live sweep). The per-suite live
    checks (``live-nonpy``, ``live-throughput``, ``live-indexer``,
    ``live-apisurface``, ``live-sessions``, ``live-stability``,
    ``live-client-overhead``, ``live-byte-fidelity``) are deliberately EXCLUDED here --
    each is a strict subset of ``live-deployed-server``'s full sweep, so
    re-running them in a no-arg invocation would duplicate ~7 minutes of live
    work for no added coverage; use them individually for targeted
    post-deploy verification of one suite instead.

    A component whose PRECONDITIONS are absent (currently only
    ``live-deployed-server`` without readable mTLS files) is reported as an
    explicit SKIP and does NOT by itself fail the run. A component that DID
    run and failed always fails the run. Exit codes are aggregated: any
    "failed" component makes the overall run fail (exit 1); an all-SKIP or
    all-PASS run (with no failures) succeeds (exit 0).
    """
    results = [_attempt_full_pytest_suite(), _attempt_live_deployed_server()]
    _print_run_all_summary(results)
    if any(r.status == "failed" for r in results):
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(prog="pipeline")
    parser.add_argument(
        "check_name",
        nargs="?",
        help="Optional named check from `pipeline --list`.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_checks_flag",
        help="List available named checks and exit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the pipeline CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.list_checks_flag:
        _print_check_catalog()
        return 0

    if args.check_name:
        return run_check(str(args.check_name))

    return run_all()
