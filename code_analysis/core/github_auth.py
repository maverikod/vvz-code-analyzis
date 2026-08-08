"""
GitHub token authentication for the GitHub command block.

Resolves the server's personal access token and builds the HTTP headers used
by every GitHub API operation.

Two sources, in this order:

1. ``code_analysis.github.token_path`` -- a filesystem path to a file holding
   the token. Configuration stores only the PATH; token bytes never live in
   configuration. An explicit path always wins, and if it yields no token that
   is reported as the operator error it is, not quietly bypassed.
2. the ``CODE_ANALYSIS_GITHUB_TOKEN`` environment variable, which the casmgr
   deployment already provisions via ``/var/casmgr/secrets/.env``.

Source 2 was missing until bug d23e819a: the package shipped the token in the
environment while this module read only a token file, so every GitHub command
answered GITHUB_NOT_CONFIGURED on a server that had a valid token the whole
time, and nothing in the error said which half was absent.

The token value is never logged, echoed, or embedded in any outcome; it
appears only in the returned Authorization header. The ``REASON_*`` diagnostics
name which SOURCE failed and never carry token material. This module is the
whole token-handling surface of the GitHub block and is separate from the
SSH identity used by plain git remote operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from code_analysis.core.storage_paths import load_raw_config

CONFIG_SECTION_CODE_ANALYSIS = "code_analysis"
CONFIG_SECTION_GITHUB = "github"
CONFIG_KEY_TOKEN_PATH = "token_path"

# Environment variable the deployment already provisions (bug d23e819a). The
# casmgr package writes CODE_ANALYSIS_GITHUB_TOKEN into
# /var/casmgr/secrets/.env and the container receives it, but this module only
# ever read a token FILE named by config, so the two halves never met and every
# GitHub command reported GITHUB_NOT_CONFIGURED on a server that had the token
# all along. Reading the variable uses the secret where it already lives
# instead of copying it to a second place on disk.
ENV_TOKEN_VAR = "CODE_ANALYSIS_GITHUB_TOKEN"

GITHUB_NOT_CONFIGURED = "GITHUB_NOT_CONFIGURED"

# Precise reasons behind the single GITHUB_NOT_CONFIGURED code. The code itself
# is part of the command contract and does not change; these travel alongside it
# so an operator can tell "nobody configured it" from "the file you pointed me
# at is unreadable" from "the file is there but empty" -- four situations that
# used to be indistinguishable from outside, which is why this bug sat unfixed
# for weeks. None of them ever carries token material.
REASON_NO_CONFIG = "config_unavailable"
REASON_NO_TOKEN_SOURCE = "no_token_path_and_no_env_token"
REASON_TOKEN_FILE_UNREADABLE = "token_file_unreadable"
REASON_TOKEN_FILE_EMPTY = "token_file_empty"
REASON_ENV_TOKEN_EMPTY = "env_token_empty"

GITHUB_API_ACCEPT = "application/vnd.github+json"
GITHUB_API_VERSION = "2022-11-28"


def _resolve_config_path() -> Path:
    """
    Resolve the active server config path.

    Priority: the mcp_proxy_adapter global config path when available,
    otherwise config.json in the current working directory.

    Returns:
        Absolute path to the active server config file.
    """
    try:
        from mcp_proxy_adapter.config import get_config

        cfg = get_config()
        cfg_path = getattr(cfg, "config_path", None)
        if isinstance(cfg_path, str) and cfg_path.strip():
            return Path(cfg_path).expanduser().resolve()
    except Exception:
        pass
    return (Path.cwd() / "config.json").resolve()


def _load_config_data() -> Optional[Dict[str, Any]]:
    """
    Load the raw server config dict from the active config path.

    Returns:
        Parsed config dict, or None when the config cannot be loaded.
    """
    try:
        return load_raw_config(_resolve_config_path())
    except Exception:
        return None


def _read_token_file(token_path: str) -> Optional[str]:
    """
    Read the token file and return the stripped token value.

    Args:
        token_path: Filesystem path to the token file from configuration.

    Returns:
        Token with surrounding whitespace stripped, or None when the file
        is unreadable or its content is empty after stripping.
    """
    try:
        raw = Path(token_path).expanduser().read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    token = raw.strip()
    return token if token else None


def resolve_github_auth(
    config_data: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """
    Resolve GitHub API authentication headers from server configuration.

    Locates the code_analysis.github config section, reads the token file
    referenced by its token_path key, and builds the HTTP headers for the
    GitHub API. The token value appears only in the Authorization header,
    never in logs, error strings, or outcomes.

    Args:
        config_data: Full config dict. When None, the active server config
            is loaded from disk.

    Returns:
        Tuple of (headers, outcome). On success, headers carries
        Authorization, Accept, and X-GitHub-Api-Version and outcome is
        None. When the github section is absent, token_path is missing,
        the token file is unreadable, or its content is empty after
        stripping, returns (None, "GITHUB_NOT_CONFIGURED").
    """
    headers, outcome, _reason = resolve_github_auth_detailed(config_data)
    return (headers, outcome)


def describe_github_auth_state(
    config_data: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Return the machine-readable reason behind the current auth state.

    Diagnostics only, and safe to surface: the reasons name WHICH source was
    missing or unusable, never any token material.

    Args:
        config_data: Full config dict, or None to load the active config.

    Returns:
        One of the ``REASON_*`` constants, or ``"ok"`` when auth resolves.
    """
    _headers, outcome, reason = resolve_github_auth_detailed(config_data)
    return "ok" if outcome is None else reason


def resolve_github_auth_detailed(
    config_data: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, str]], Optional[str], str]:
    """
    Resolve GitHub auth and report precisely why it failed when it did.

    Token sources, in order:
    1. ``code_analysis.github.token_path`` -- a file holding the token. Kept
       first so an explicit configuration always wins over the ambient
       environment.
    2. the ``CODE_ANALYSIS_GITHUB_TOKEN`` environment variable, which the
       deployment already provisions (bug d23e819a).

    Args:
        config_data: Full config dict, or None to load the active config.

    Returns:
        ``(headers, outcome, reason)``. On success ``outcome`` is None and
        ``reason`` is ``"ok"``. Otherwise ``outcome`` is
        ``GITHUB_NOT_CONFIGURED`` -- unchanged, it is part of the command
        contract -- and ``reason`` is one of the ``REASON_*`` constants.
    """
    data = config_data if config_data is not None else _load_config_data()

    token_path: Optional[str] = None
    if isinstance(data, dict):
        ca = data.get(CONFIG_SECTION_CODE_ANALYSIS)
        if isinstance(ca, dict):
            github_cfg = ca.get(CONFIG_SECTION_GITHUB)
            if isinstance(github_cfg, dict):
                raw_path = github_cfg.get(CONFIG_KEY_TOKEN_PATH)
                if isinstance(raw_path, str) and raw_path.strip():
                    token_path = raw_path.strip()

    if token_path is not None:
        token = _read_token_file(token_path)
        if token:
            return (_headers_for(token), None, "ok")
        # An explicitly configured path that does not yield a token is an
        # operator error worth naming exactly, not something to paper over by
        # silently falling through to the environment.
        reason = (
            REASON_TOKEN_FILE_EMPTY
            if Path(token_path).expanduser().is_file()
            else REASON_TOKEN_FILE_UNREADABLE
        )
        return (None, GITHUB_NOT_CONFIGURED, reason)

    env_token = (os.environ.get(ENV_TOKEN_VAR) or "").strip()
    if env_token:
        return (_headers_for(env_token), None, "ok")
    if ENV_TOKEN_VAR in os.environ:
        return (None, GITHUB_NOT_CONFIGURED, REASON_ENV_TOKEN_EMPTY)

    if not isinstance(data, dict):
        return (None, GITHUB_NOT_CONFIGURED, REASON_NO_CONFIG)
    return (None, GITHUB_NOT_CONFIGURED, REASON_NO_TOKEN_SOURCE)


def _headers_for(token: str) -> Dict[str, str]:
    """
    Build the GitHub API headers for a resolved token.

    Args:
        token: The token value; it appears only in the Authorization header.

    Returns:
        Authorization, Accept and X-GitHub-Api-Version headers.
    """
    return {
        "Authorization": "Bearer " + token,
        "Accept": GITHUB_API_ACCEPT,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


GITHUB_AUTH_FAILED = "GITHUB_AUTH_FAILED"
GITHUB_INSUFFICIENT_SCOPE = "GITHUB_INSUFFICIENT_SCOPE"


def classify_github_auth_error(status_code: int) -> Optional[str]:
    """
    Classify a GitHub API HTTP status code as an authentication outcome.

    Pure function: performs no I/O, emits no log, and carries no secret
    material.

    Args:
        status_code: HTTP status code returned by the GitHub API.

    Returns:
        "GITHUB_AUTH_FAILED" for status 401 (rejected token),
        "GITHUB_INSUFFICIENT_SCOPE" for status 403 (under-scoped token),
        None for any other status code.
    """
    if status_code == 401:
        return GITHUB_AUTH_FAILED
    if status_code == 403:
        return GITHUB_INSUFFICIENT_SCOPE
    return None
