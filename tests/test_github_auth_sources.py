"""
Regression tests for GitHub token resolution (bug d23e819a).

The deployed server had a valid token all along -- casmgr provisions
``CODE_ANALYSIS_GITHUB_TOKEN`` in ``/var/casmgr/secrets/.env`` and the
container receives it -- but this module read only a token FILE named by
``code_analysis.github.token_path``. The two halves never met, so every GitHub
command answered GITHUB_NOT_CONFIGURED, and because four distinct situations
shared that one code, nothing in the response said which half was missing.

These tests pin both halves of the fix: the environment source, and the
diagnostics that tell an operator what to do next.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_analysis.core.github_auth import (
    ENV_TOKEN_VAR,
    GITHUB_NOT_CONFIGURED,
    REASON_ENV_TOKEN_EMPTY,
    REASON_NO_TOKEN_SOURCE,
    REASON_TOKEN_FILE_EMPTY,
    REASON_TOKEN_FILE_UNREADABLE,
    describe_github_auth_state,
    resolve_github_auth,
    resolve_github_auth_detailed,
)

_FILE_TOKEN = "ghp_from_the_file_00000000000000000000"
_ENV_TOKEN = "ghp_from_the_environment_0000000000000"


def _config_with_token_path(token_path: str | None) -> dict:
    """Build a config dict with (or without) a github token_path."""
    github: dict = {} if token_path is None else {"token_path": token_path}
    return {"code_analysis": {"github": github}}


def test_env_token_is_used_when_no_token_path_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bug d23e819a: the provisioned environment token must be honoured."""
    monkeypatch.setenv(ENV_TOKEN_VAR, _ENV_TOKEN)

    headers, outcome = resolve_github_auth({"code_analysis": {}})

    assert outcome is None
    assert headers is not None
    assert headers["Authorization"] == f"Bearer {_ENV_TOKEN}"
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"


def test_env_token_is_used_even_with_no_config_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A server with the token in its environment works without github config."""
    monkeypatch.setenv(ENV_TOKEN_VAR, _ENV_TOKEN)

    headers, outcome = resolve_github_auth({})

    assert outcome is None
    assert headers is not None


def test_configured_token_path_wins_over_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit configuration beats the ambient environment."""
    token_file = tmp_path / "token"
    token_file.write_text(_FILE_TOKEN + "\n", encoding="utf-8")
    monkeypatch.setenv(ENV_TOKEN_VAR, _ENV_TOKEN)

    headers, outcome = resolve_github_auth(_config_with_token_path(str(token_file)))

    assert outcome is None
    assert headers is not None
    assert headers["Authorization"] == f"Bearer {_FILE_TOKEN}"


def test_a_configured_path_that_does_not_exist_is_reported_precisely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken explicit path is an operator error, not a silent env fallback."""
    monkeypatch.setenv(ENV_TOKEN_VAR, _ENV_TOKEN)
    missing = tmp_path / "nope" / "token"

    headers, outcome, reason = resolve_github_auth_detailed(
        _config_with_token_path(str(missing))
    )

    assert headers is None
    assert outcome == GITHUB_NOT_CONFIGURED
    assert reason == REASON_TOKEN_FILE_UNREADABLE


def test_an_empty_token_file_is_distinguished_from_a_missing_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """"The file is there but empty" is a different fix than "the file is gone"."""
    monkeypatch.delenv(ENV_TOKEN_VAR, raising=False)
    empty = tmp_path / "token"
    empty.write_text("   \n", encoding="utf-8")

    _headers, outcome, reason = resolve_github_auth_detailed(
        _config_with_token_path(str(empty))
    )

    assert outcome == GITHUB_NOT_CONFIGURED
    assert reason == REASON_TOKEN_FILE_EMPTY


def test_no_source_at_all_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither a path nor an environment token: the reason names both."""
    monkeypatch.delenv(ENV_TOKEN_VAR, raising=False)

    _headers, outcome, reason = resolve_github_auth_detailed(
        _config_with_token_path(None)
    )

    assert outcome == GITHUB_NOT_CONFIGURED
    assert reason == REASON_NO_TOKEN_SOURCE


def test_an_env_variable_set_to_blank_is_its_own_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Set-but-empty is a provisioning slip, distinct from never set."""
    monkeypatch.setenv(ENV_TOKEN_VAR, "   ")

    _headers, outcome, reason = resolve_github_auth_detailed(
        _config_with_token_path(None)
    )

    assert outcome == GITHUB_NOT_CONFIGURED
    assert reason == REASON_ENV_TOKEN_EMPTY


def test_describe_reports_ok_when_auth_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The diagnostic helper is usable as a health probe."""
    monkeypatch.setenv(ENV_TOKEN_VAR, _ENV_TOKEN)

    assert describe_github_auth_state({}) == "ok"


def test_no_reason_string_ever_carries_token_material(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Diagnostics name the source, never the secret."""
    token_file = tmp_path / "token"
    token_file.write_text(_FILE_TOKEN, encoding="utf-8")
    monkeypatch.setenv(ENV_TOKEN_VAR, _ENV_TOKEN)

    for config in (
        _config_with_token_path(str(token_file)),
        _config_with_token_path(str(tmp_path / "missing")),
        _config_with_token_path(None),
    ):
        reason = describe_github_auth_state(config)
        assert _FILE_TOKEN not in reason
        assert _ENV_TOKEN not in reason
