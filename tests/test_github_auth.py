"""Tests for GitHub command-block authentication configuration."""

from __future__ import annotations

from code_analysis.core.github_auth import (
    DEFAULT_GITHUB_TOKEN_ENV,
    GITHUB_NOT_CONFIGURED,
    resolve_github_auth,
)


def test_resolve_github_auth_uses_default_env(monkeypatch) -> None:
    """Verify GitHub auth reads the token from the default environment variable."""
    monkeypatch.setenv(DEFAULT_GITHUB_TOKEN_ENV, "ghp_example")

    headers, error = resolve_github_auth({"code_analysis": {"github": {}}})

    assert error is None
    assert headers is not None
    assert headers["Authorization"] == "Bearer ghp_example"


def test_resolve_github_auth_missing_env_returns_not_configured(monkeypatch) -> None:
    """Verify GitHub auth reports not configured when env tokens are absent."""
    monkeypatch.delenv(DEFAULT_GITHUB_TOKEN_ENV, raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    headers, error = resolve_github_auth({"code_analysis": {"github": {}}})

    assert headers is None
    assert error == GITHUB_NOT_CONFIGURED
