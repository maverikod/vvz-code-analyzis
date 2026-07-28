"""Contract tests for the project pipeline CLI."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from code_analysis import pipeline_cli


def test_list_checks_contains_named_bugfix_checks() -> None:
    """Verify the CLI exposes the named checks used for local verification."""
    names = [check.name for check in pipeline_cli.list_checks()]
    assert names == [
        "pipeline-cli",
        "lint-config",
        "anchor-check",
        "fs-grep",
        "handler-registry",
        "batch-stable-id",
        "sibling-insert-stale-target",
        "install-config",
        "create-text-file",
        "cst-save-tree",
        "restore-watch-dirs",
        "docstring-batch-persist",
        "invalid-open-preview",
        "file-session-client",
        "file-watcher-config",
        "get-file-lines",
        "fulltext-search",
        "mtime-reindex",
        "packaging-config",
        "git-branch-commands",
        "git-pull-safe-content-stale",
        "info-command",
        "integrity-analysis",
        "json-save-tree",
        "log-view-pagination",
        "logical-write-submit",
        "main-loop-decoupling",
        "mcp-queue-regressions",
        "openapi-jsonrpc-concurrency",
        "processing-paused-projects",
        "project-activity-locks-migrations",
        "project-pip-logging",
        "project-text-file-routing",
        "query-cst-line-range",
        "schema-core-uuid-migration",
        "schema-rest-uuid-migration",
        "startup-reconciliation",
        "text-universal-edit-write-close",
        "preview-edit-addressing-all-formats",
        "tree-temp-preview-navigation",
        "tree-temp-universal-json-preview-sessions",
        "tree-temp-universal-yaml-preview-sessions",
        "universal-file-save-routing",
        "tree-temp-edit-session-preview",
        "transfer-lock-batch-commands",
        "vectorization-uuid-sql-order",
        "verify-lifecycle-content-stale-save",
        "watcher-project-metadata",
        "search-close-pagination",
        "trash-list-name-parse",
        "live-deployed-server",
    ]


def test_main_list_prints_catalog(capsys) -> None:
    """Verify `pipeline --list` prints the available checks."""
    exit_code = pipeline_cli.main(["--list"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "lint-config" in captured.out
    assert "anchor-check" in captured.out
    assert "fs-grep" in captured.out
    assert "handler-registry" in captured.out
    assert "batch-stable-id" in captured.out
    assert "sibling-insert-stale-target" in captured.out
    assert "install-config" in captured.out
    assert "create-text-file" in captured.out
    assert "cst-save-tree" in captured.out
    assert "restore-watch-dirs" in captured.out
    assert "docstring-batch-persist" in captured.out
    assert "invalid-open-preview" in captured.out
    assert "file-session-client" in captured.out
    assert "file-watcher-config" in captured.out
    assert "get-file-lines" in captured.out
    assert "fulltext-search" in captured.out
    assert "git-branch-commands" in captured.out
    assert "git-pull-safe-content-stale" in captured.out
    assert "info-command" in captured.out
    assert "integrity-analysis" in captured.out
    assert "json-save-tree" in captured.out
    assert "log-view-pagination" in captured.out
    assert "logical-write-submit" in captured.out
    assert "main-loop-decoupling" in captured.out
    assert "mcp-queue-regressions" in captured.out
    assert "openapi-jsonrpc-concurrency" in captured.out
    assert "processing-paused-projects" in captured.out
    assert "project-activity-locks-migrations" in captured.out
    assert "project-pip-logging" in captured.out
    assert "project-text-file-routing" in captured.out
    assert "query-cst-line-range" in captured.out
    assert "schema-core-uuid-migration" in captured.out
    assert "schema-rest-uuid-migration" in captured.out
    assert "startup-reconciliation" in captured.out
    assert "text-universal-edit-write-close" in captured.out
    assert "preview-edit-addressing-all-formats" in captured.out
    assert "tree-temp-preview-navigation" in captured.out
    assert "tree-temp-universal-json-preview-sessions" in captured.out
    assert "tree-temp-universal-yaml-preview-sessions" in captured.out
    assert "universal-file-save-routing" in captured.out
    assert "tree-temp-edit-session-preview" in captured.out
    assert "transfer-lock-batch-commands" in captured.out
    assert "vectorization-uuid-sql-order" in captured.out
    assert "verify-lifecycle-content-stale-save" in captured.out
    assert "watcher-project-metadata" in captured.out
    assert "search-close-pagination" in captured.out
    assert "trash-list-name-parse" in captured.out
    assert "live-deployed-server" in captured.out


def test_run_check_executes_expected_pytest_targets(monkeypatch) -> None:
    """Verify a named check runs the expected pytest selection."""
    recorded: dict[str, object] = {}

    def fake_run(cmd, cwd, check):
        recorded["cmd"] = cmd
        recorded["cwd"] = cwd
        recorded["check"] = check
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(pipeline_cli.subprocess, "run", fake_run)

    exit_code = pipeline_cli.main(["fulltext-search"])

    assert exit_code == 0
    assert recorded["cmd"] == [
        pipeline_cli.sys.executable,
        "-m",
        "pytest",
        "tests/unit/test_search_paginated_fulltext.py",
        "tests/test_domain_search_full_text_port.py",
        "tests/test_fulltext_driver_backend_config.py",
    ]
    assert recorded["cwd"] == Path(__file__).resolve().parents[1]
    assert recorded["check"] is False


def test_main_without_args_runs_full_suite(monkeypatch) -> None:
    """Verify bare `pipeline` runs the full pytest suite."""
    recorded: dict[str, object] = {}

    def fake_run(cmd, cwd, check):
        recorded["cmd"] = cmd
        recorded["cwd"] = cwd
        recorded["check"] = check
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(pipeline_cli.subprocess, "run", fake_run)

    exit_code = pipeline_cli.main([])

    assert exit_code == 0
    assert recorded["cmd"] == [pipeline_cli.sys.executable, "-m", "pytest", "tests"]
    assert recorded["cwd"] == Path(__file__).resolve().parents[1]
    assert recorded["check"] is False


def test_main_unknown_check_returns_error(capsys) -> None:
    """Verify unknown checks fail with a useful message."""
    exit_code = pipeline_cli.main(["missing-check"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Unknown pipeline check" in captured.err


def test_pyproject_declares_pipeline_console_script() -> None:
    """Verify editable installs expose the standard pipeline command."""
    pyproject_text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert "[project.scripts]" in pyproject_text
    assert 'pipeline = "code_analysis.pipeline_cli:main"' in pyproject_text
