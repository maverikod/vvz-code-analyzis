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
        "file-mode-preserved",
        "byte-verbatim-io",
        "trash-list-name-parse",
        "live-deployed-server",
        "live-nonpy",
        "live-throughput",
        "live-indexer",
        "live-apisurface",
        "live-sessions",
        "live-stability",
        "live-client-overhead",
        "live-byte-fidelity",
        "live-file-mode",
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
    assert "byte-verbatim-io" in captured.out
    assert "file-mode-preserved" in captured.out
    assert "live-deployed-server" in captured.out
    assert "live-nonpy" in captured.out
    assert "live-throughput" in captured.out
    assert "live-indexer" in captured.out
    assert "live-apisurface" in captured.out
    assert "live-byte-fidelity" in captured.out
    assert "live-file-mode" in captured.out


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


def test_main_without_args_runs_full_suite_and_live_sweep_when_mtls_present(
    monkeypatch,
) -> None:
    """Bare `pipeline` runs pytest AND the full live sweep (not the 4 per-suite checks)."""
    calls: list[list[str]] = []

    def fake_run(cmd, cwd, check):
        calls.append(list(cmd))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(pipeline_cli.subprocess, "run", fake_run)
    monkeypatch.setattr(
        pipeline_cli,
        "_resolve_live_verifier_ssl_paths",
        lambda: {"cert": "c", "key": "k", "ca": "a"},
    )

    exit_code = pipeline_cli.main([])

    assert exit_code == 0
    assert len(calls) == 2
    assert calls[0] == [pipeline_cli.sys.executable, "-m", "pytest", "tests"]
    assert calls[1][1] == "scripts/verify_client_all_commands_live.py"
    # No suite name appended -- this is the full sweep, not a per-suite check.
    assert "nonpy" not in calls[1]
    assert "throughput" not in calls[1]
    assert "indexer" not in calls[1]
    assert "apisurface" not in calls[1]


def test_main_without_args_skips_live_sweep_without_mtls_preconditions(
    monkeypatch, capsys
) -> None:
    """A missing-precondition live sweep is an explicit SKIP, not a FAIL, and does not fail the run."""

    def fake_run(cmd, cwd, check):
        return SimpleNamespace(returncode=0)

    def _raise_missing_mtls() -> dict[str, str]:
        raise ValueError("no mtls files on this machine")

    monkeypatch.setattr(pipeline_cli.subprocess, "run", fake_run)
    monkeypatch.setattr(
        pipeline_cli, "_resolve_live_verifier_ssl_paths", _raise_missing_mtls
    )

    exit_code = pipeline_cli.main([])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[PASS] full-pytest-suite" in captured.out
    assert "[SKIP] live-deployed-server" in captured.out
    assert "no mtls files on this machine" in captured.out


def test_main_without_args_fails_when_pytest_fails_even_if_live_skipped(
    monkeypatch, capsys
) -> None:
    """A genuine pytest failure fails the run regardless of the live sweep's SKIP status."""

    def fake_run(cmd, cwd, check):
        return SimpleNamespace(returncode=1)

    def _raise_missing_mtls() -> dict[str, str]:
        raise ValueError("no mtls files on this machine")

    monkeypatch.setattr(pipeline_cli.subprocess, "run", fake_run)
    monkeypatch.setattr(
        pipeline_cli, "_resolve_live_verifier_ssl_paths", _raise_missing_mtls
    )

    exit_code = pipeline_cli.main([])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "[FAIL] full-pytest-suite" in captured.out
    assert "[SKIP] live-deployed-server" in captured.out


def test_main_without_args_fails_when_live_sweep_fails(monkeypatch, capsys) -> None:
    """A live sweep that RAN and failed fails the run (distinct from a SKIP)."""

    def fake_run(cmd, cwd, check):
        if "scripts/verify_client_all_commands_live.py" in cmd:
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(pipeline_cli.subprocess, "run", fake_run)
    monkeypatch.setattr(
        pipeline_cli,
        "_resolve_live_verifier_ssl_paths",
        lambda: {"cert": "c", "key": "k", "ca": "a"},
    )

    exit_code = pipeline_cli.main([])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "[PASS] full-pytest-suite" in captured.out
    assert "[FAIL] live-deployed-server" in captured.out


def test_run_check_live_suite_forwards_suite_name(monkeypatch) -> None:
    """Verify `pipeline live-nonpy` forwards the suite name to the live verifier."""
    recorded: dict[str, object] = {}

    def fake_run(cmd, cwd, check):
        recorded["cmd"] = cmd
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(pipeline_cli.subprocess, "run", fake_run)
    monkeypatch.setattr(
        pipeline_cli,
        "_resolve_live_verifier_ssl_paths",
        lambda: {"cert": "c", "key": "k", "ca": "a"},
    )

    exit_code = pipeline_cli.main(["live-nonpy"])

    assert exit_code == 0
    assert recorded["cmd"][1] == "scripts/verify_client_all_commands_live.py"
    assert recorded["cmd"][-1] == "nonpy"


def test_run_check_live_deployed_server_missing_mtls_returns_2(
    monkeypatch, capsys
) -> None:
    """A direct (non-run_all) invocation with missing mTLS preconditions still returns 2."""

    def _raise_missing_mtls() -> dict[str, str]:
        raise ValueError("no mtls files on this machine")

    monkeypatch.setattr(
        pipeline_cli, "_resolve_live_verifier_ssl_paths", _raise_missing_mtls
    )

    exit_code = pipeline_cli.main(["live-deployed-server"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "no mtls files on this machine" in captured.err


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
