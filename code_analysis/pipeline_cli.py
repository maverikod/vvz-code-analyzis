"""Project-wide verification entrypoint."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class PipelineCheck:
    """Named verification unit exposed through the pipeline CLI."""

    name: str
    description: str
    pytest_targets: tuple[str, ...]


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
        description="Verify get_file_lines keeps INVALID_RANGE behavior in isolated contexts without config.json.",
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
        description="Verify info command validation and runtime missing-node contracts stay aligned.",
        pytest_targets=("tests/test_info_command.py",),
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
        description="Verify queue integration tests skip cleanly when multiprocessing semaphores are unavailable in the sandbox.",
        pytest_targets=(
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
)

_CHECKS_BY_NAME = {check.name: check for check in _CHECKS}
_FULL_SUITE_TARGETS: tuple[str, ...] = ("tests",)


def list_checks() -> tuple[PipelineCheck, ...]:
    """Return the immutable pipeline check catalog."""
    return _CHECKS


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _pytest_command(pytest_targets: Sequence[str]) -> list[str]:
    return [sys.executable, "-m", "pytest", *pytest_targets]


def _run_pytest(pytest_targets: Sequence[str]) -> int:
    completed = subprocess.run(
        _pytest_command(pytest_targets),
        cwd=_repo_root(),
        check=False,
    )
    return int(completed.returncode)


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
    return _run_pytest(check.pytest_targets)


def run_all() -> int:
    """Run the full repository test suite."""
    return _run_pytest(_FULL_SUITE_TARGETS)


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
