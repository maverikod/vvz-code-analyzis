"""Tests for GitHub command-block authentication configuration."""

from code_analysis.core.github_auth import GITHUB_NOT_CONFIGURED, resolve_github_auth


def test_resolve_github_auth_reads_token_path(tmp_path) -> None:
    """Verify GitHub auth reads the token from the configured token file."""
    token_file = tmp_path / "github-token"
    token_file.write_text(" ghp_example \n", encoding="utf-8")

    headers, error = resolve_github_auth(
        {"code_analysis": {"github": {"token_path": str(token_file)}}}
    )

    assert error is None
    assert headers is not None
    assert headers["Authorization"] == "Bearer ghp_example"
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"


def test_resolve_github_auth_missing_token_path_returns_not_configured() -> None:
    """Verify GitHub auth reports not configured when token_path is absent."""
    headers, error = resolve_github_auth({"code_analysis": {"github": {}}})

    assert headers is None
    assert error == GITHUB_NOT_CONFIGURED


def test_resolve_github_auth_empty_token_file_returns_not_configured(tmp_path) -> None:
    """Verify GitHub auth reports not configured when token content is empty."""
    token_file = tmp_path / "github-token"
    token_file.write_text(" \n", encoding="utf-8")

    headers, error = resolve_github_auth(
        {"code_analysis": {"github": {"token_path": str(token_file)}}}
    )

    assert headers is None
    assert error == GITHUB_NOT_CONFIGURED
