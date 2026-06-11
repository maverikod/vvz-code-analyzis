"""batch_output_dir resolution and ServerConfig validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from code_analysis.core.config import ServerConfig
from code_analysis.core.storage_paths import (
    apply_resolved_batch_output_dir,
    resolve_batch_output_dir,
)


def test_resolve_batch_output_dir_relative_to_config_dir(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    resolved = resolve_batch_output_dir(
        config_path=config_path, dir_str="data/batch_output"
    )
    assert resolved == (tmp_path / "data" / "batch_output").resolve()


def test_server_config_accepts_relative_batch_output_dir() -> None:
    cfg = ServerConfig(chunker={"enabled": False, "url": "localhost", "port": 8009})
    assert cfg.batch_output_dir == "data/batch_output"


def test_apply_resolved_batch_output_dir_prod_fallback(
    monkeypatch, tmp_path: Path
) -> None:
    config_path = Path("/etc/casmgr/config.json")
    db_path = tmp_path / "data" / "code_analysis.db"

    def _fake_load(_path: Path) -> dict:
        return {
            "code_analysis": {
                "storage": {"db_path": str(db_path)},
            }
        }

    monkeypatch.setattr(
        "code_analysis.core.storage_paths.load_raw_config",
        _fake_load,
    )
    out = apply_resolved_batch_output_dir({}, config_path)
    assert out["batch_output_dir"] == str((db_path.parent / "batch_output").resolve())
    ServerConfig(**out, chunker={"enabled": True, "url": "127.0.0.1", "port": 8009})


def test_server_config_rejects_batch_output_under_usr() -> None:
    with pytest.raises(ValueError, match="system path"):
        ServerConfig(
            batch_output_dir="/usr/lib/casmgr-server/data/batch_output",
            chunker={"enabled": False, "url": "localhost", "port": 8009},
        )
