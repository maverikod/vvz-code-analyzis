"""Tests for .env loading (permission-safe startup)."""

from __future__ import annotations

from pathlib import Path

from code_analysis.core import env_loader


def test_load_dotenv_near_config_skips_unreadable_env(
    tmp_path: Path, monkeypatch
) -> None:
    """Verify test load dotenv near config skips unreadable env."""
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET=1\n", encoding="utf-8")
    env_file.chmod(0o000)

    monkeypatch.delenv("SECRET", raising=False)
    monkeypatch.setenv("CASMGR_SECRETS", str(tmp_path / "missing-secrets"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(env_loader, "load_dotenv_best_effort", lambda **kw: False)

    loaded = env_loader.load_dotenv_near_config(config)
    assert loaded is False
    assert "SECRET" not in __import__("os").environ

    env_file.chmod(0o644)
