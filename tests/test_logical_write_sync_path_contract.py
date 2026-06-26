"""
Contract tests: logical write sync path must not reintroduce multi-RPC transactions.

Guardrails against regressions that split one logical save across multiple
begin_transaction / execute_batch / commit RPC sequences on the SQLite client.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    """Return repo root."""
    p = Path(__file__).resolve()
    for parent in [p.parent, *p.parents]:
        if (parent / "code_analysis" / "core").is_dir():
            return parent
    raise RuntimeError("repository root not found from test file")


def test_sync_file_to_db_atomic_source_no_transaction_helpers() -> None:
    """Verify test sync file to db atomic source no transaction helpers."""
    path = _repo_root() / "code_analysis" / "core" / "database" / "file_tree_sync.py"
    if not path.is_file():
        raise AssertionError(f"missing {path}")
    text = path.read_text(encoding="utf-8")
    for needle in (
        "begin_transaction(",
        "execute_batch(",
        "commit_transaction(",
        "rollback_transaction(",
    ):
        assert needle not in text, f"{path} must not contain {needle!r}"


def test_clear_project_data_impl_uses_logical_write_only() -> None:
    """Verify test clear project data impl uses logical write only."""
    path = _repo_root() / "code_analysis" / "commands" / "clear_project_data_impl.py"
    if not path.is_file():
        raise AssertionError(f"missing {path}")
    text = path.read_text(encoding="utf-8")
    for needle in (
        "begin_transaction(",
        "execute_batch(",
        "commit_transaction(",
        "rollback_transaction(",
    ):
        assert needle not in text, f"{path} must not contain {needle!r}"


def test_update_file_data_atomic_batch_uses_logical_write_only() -> None:
    """Verify test update file data atomic batch uses logical write only."""
    path = (
        _repo_root()
        / "code_analysis"
        / "core"
        / "database_client"
        / "file_data_batch.py"
    )
    if not path.is_file():
        raise AssertionError(f"missing {path}")
    text = path.read_text(encoding="utf-8")
    assert "begin_transaction(" not in text
    assert "execute_batch(" not in text
