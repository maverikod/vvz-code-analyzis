"""
GitHub token authentication for the GitHub command block.

Resolves the server's personal access token from configuration and builds
the HTTP headers used by every GitHub API operation. The configuration
section ``code_analysis.github`` stores only a filesystem path to the
token file (key ``token_path``); token bytes never live in configuration.
The token value is never logged, echoed, or embedded in any outcome; it
appears only in the returned Authorization header. This module is the
whole token-handling surface of the GitHub block and is separate from the
SSH identity used by plain git remote operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from code_analysis.core.storage_paths import load_raw_config

CONFIG_SECTION_CODE_ANALYSIS = "code_analysis"
CONFIG_SECTION_GITHUB = "github"
CONFIG_KEY_TOKEN_PATH = "token_path"

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
    data = config_data if config_data is not None else _load_config_data()
    if not isinstance(data, dict):
        return (None, GITHUB_NOT_CONFIGURED)
    ca = data.get(CONFIG_SECTION_CODE_ANALYSIS)
    if not isinstance(ca, dict):
        return (None, GITHUB_NOT_CONFIGURED)
    github_cfg = ca.get(CONFIG_SECTION_GITHUB)
    if not isinstance(github_cfg, dict):
        return (None, GITHUB_NOT_CONFIGURED)
    token_path = github_cfg.get(CONFIG_KEY_TOKEN_PATH)
    if not isinstance(token_path, str) or not token_path.strip():
        return (None, GITHUB_NOT_CONFIGURED)
    token = _read_token_file(token_path)
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
