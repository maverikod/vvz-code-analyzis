"""
Remote operation timeout bound for git and GitHub remote-contacting operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import subprocess
from typing import Any, List, Mapping, Optional, Tuple

DEFAULT_REMOTE_TIMEOUT_SECONDS = 30
REMOTE_TIMEOUT_OUTCOME = "GIT_REMOTE_TIMEOUT"
CONFIG_SECTION_GIT = "git"
CONFIG_KEY_REMOTE_TIMEOUT_SECONDS = "remote_timeout_seconds"


def get_remote_timeout_seconds_from_config(
    config_data: Optional[Mapping[str, Any]] = None,
) -> int:
    """
    Read the configured remote operation timeout, in seconds, from config.

    Looks at code_analysis.git.remote_timeout_seconds. This bound applies to
    every remote-contacting git operation (fetch, pull, push) and every
    GitHub HTTP API operation. If config_data is None, the code_analysis key
    is missing or not a mapping, the git key is missing or not a mapping, or
    remote_timeout_seconds is missing, not a positive number, or a bool, the
    function falls back to DEFAULT_REMOTE_TIMEOUT_SECONDS.

    Args:
        config_data: Full config dict as returned by
            code_analysis.core.storage_paths.load_raw_config or by
            code_analysis.commands.base_mcp_command.BaseMCPCommand._get_raw_config().
            If None, returns DEFAULT_REMOTE_TIMEOUT_SECONDS.

    Returns:
        The configured timeout in seconds as a positive int, or
        DEFAULT_REMOTE_TIMEOUT_SECONDS when unset or invalid.
    """
    if not config_data:
        return DEFAULT_REMOTE_TIMEOUT_SECONDS

    code_analysis_config = config_data.get("code_analysis")
    if not isinstance(code_analysis_config, Mapping):
        return DEFAULT_REMOTE_TIMEOUT_SECONDS

    git_config = code_analysis_config.get(CONFIG_SECTION_GIT)
    if not isinstance(git_config, Mapping):
        return DEFAULT_REMOTE_TIMEOUT_SECONDS

    value = git_config.get(CONFIG_KEY_REMOTE_TIMEOUT_SECONDS)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return DEFAULT_REMOTE_TIMEOUT_SECONDS

    return int(value)


def run_remote_git_subprocess(
    args: List[str],
    cwd: str,
    timeout_seconds: int,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Run one remote-contacting git subprocess invocation bounded by a timeout.

    Executes args as a single subprocess.run call with timeout_seconds as the
    upper bound applied to that one invocation. Performs exactly one
    invocation; it never retries the command within this call regardless of
    outcome (success, non-zero exit, or timeout). When the invocation exceeds
    timeout_seconds, subprocess.TimeoutExpired is caught and mapped to the
    distinct timeout outcome held in REMOTE_TIMEOUT_OUTCOME
    ("GIT_REMOTE_TIMEOUT"). When the process exits with a non-zero return
    code but did not time out, the captured stderr text is returned as the
    error. On success, the captured stdout text is returned.

    Args:
        args: Full command argument list to execute, e.g.
            ["git", "fetch", "origin"]. The first element is expected to be
            "git", but this function does not validate that; it passes args
            through to subprocess.run unchanged.
        cwd: Working directory (the repository root) the command runs in.
        timeout_seconds: The upper bound, in seconds, applied to this single
            invocation. Expected to be a positive int, typically obtained
            from get_remote_timeout_seconds_from_config.

    Returns:
        A tuple (success, output, outcome). On success:
        (True, stdout_text, None). On non-timeout failure:
        (False, None, stderr_text). On timeout:
        (False, None, "GIT_REMOTE_TIMEOUT").
    """
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return False, None, REMOTE_TIMEOUT_OUTCOME

    if result.returncode != 0:
        return False, None, result.stderr

    return True, result.stdout, None
