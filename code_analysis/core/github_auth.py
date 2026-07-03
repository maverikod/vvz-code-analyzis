"""
GitHub token authentication for the GitHub command block.

Resolves the server's personal access token from environment variables and
builds the HTTP headers used by every GitHub API operation. Token bytes live
in the process environment (normally loaded from /var/casmgr/secrets/.env),
never in config.json. The token value is never logged, echoed, or embedded
in any outcome; it appears only in the returned Authorization header. This
module is the whole token-handling surface of the GitHub block and is
separate from the SSH identity used by plain git remote operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from code_analysis.core.storage_paths import load_raw_config

CONFIG_SECTION_CODE_ANALYSIS = "code_analysis"
CONFIG_SECTION_GITHUB = "github"
CONFIG_KEY_TOKEN_ENV = "token_env"
DEFAULT_GITHUB_TOKEN_ENV = "CODE_ANALYSIS_GITHUB_TOKEN"
FALLBACK_GITHUB_TOKEN_ENV = "GITHUB_TOKEN"

GITHUB_NOT_CONFIGURED = "GITHUB_NOT_CONFIGURED"

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
        return (Path.cwd() / "config.json").resolve()
    return (Path.cwd() / "config.json").resolve()


def _load_config_data() -> Optional[Dict[str, Any]]:
    """
    Load the raw server config dict from the active config path.

    Returns:
        Parsed config dict, or None when the config cannot be loaded.
    """
    try:
        config_data: Dict[str, Any] = load_raw_config(_resolve_config_path())
        return config_data
    except Exception:
        return None


def _read_token_from_environment(env_name: str) -> Optional[str]:
    """Read a GitHub token from one environment variable.

    Args:
        env_name: Environment variable name.

    Returns:
        Token with surrounding whitespace stripped, or None when the variable
        is absent or empty after stripping.
    """
    if not env_name.strip():
        return None
    raw = os.environ.get(env_name.strip())
    if raw is None:
        return None
    token = raw.strip()
    return token if token else None


def resolve_github_auth(
    config_data: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """
    Resolve GitHub API authentication headers from server configuration.

    Reads the GitHub token from the environment and builds the HTTP headers
    for the GitHub API. The default variable is CODE_ANALYSIS_GITHUB_TOKEN,
    normally loaded from /var/casmgr/secrets/.env by systemd. If
    code_analysis.github.token_env is set to a string, that variable name is
    used instead. GITHUB_TOKEN is accepted as a compatibility fallback. The
    token value appears only in the Authorization header, never in logs,
    error strings, or outcomes.

    Args:
        config_data: Full config dict. When None, the active server config
            is loaded from disk.

    Returns:
        Tuple of (headers, outcome). On success, headers carries
        Authorization, Accept, and X-GitHub-Api-Version and outcome is
        None. When the selected environment variable is absent or empty,
        returns (None, "GITHUB_NOT_CONFIGURED").
    """
    data = config_data if config_data is not None else _load_config_data()
    env_names = [DEFAULT_GITHUB_TOKEN_ENV]
    if isinstance(data, dict):
        ca = data.get(CONFIG_SECTION_CODE_ANALYSIS)
        if isinstance(ca, dict):
            github_cfg = ca.get(CONFIG_SECTION_GITHUB)
            if isinstance(github_cfg, dict):
                token_env = github_cfg.get(CONFIG_KEY_TOKEN_ENV)
                if isinstance(token_env, str) and token_env.strip():
                    env_names.insert(0, token_env.strip())
    env_names.append(FALLBACK_GITHUB_TOKEN_ENV)

    token = None
    seen = set()
    for env_name in env_names:
        if env_name in seen:
            continue
        seen.add(env_name)
        token = _read_token_from_environment(env_name)
        if token is not None:
            break
    if token is None:
        return (None, GITHUB_NOT_CONFIGURED)
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": GITHUB_API_ACCEPT,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    return (headers, None)


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
