"""
Per-operation SSH authentication environment for git remote operations.

Builds a git subprocess environment for fetch, pull, and push using exactly
one configured private key, pinned known-hosts, strict host-key checking, and
non-interactive batch mode. Also classifies git remote-operation stderr text
as an SSH authentication or host-key failure.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

# Single distinct authentication-failure outcome for SSH key and host-key issues.
GIT_AUTH_FAILED = "GIT_AUTH_FAILED"


def build_git_ssh_environment(
    git_config: Mapping[str, Any],
) -> Tuple[Optional[Dict[str, str]], Optional[Dict[str, Any]]]:
    """
    Build a per-operation SSH environment for git remote commands.

    Args:
        git_config: The extracted code_analysis.git configuration section.
            It contains ssh_key_path, a path to exactly one private key, and
            known_hosts_path, a path to the pinned known-hosts file. The
            configuration stores paths only, never key bytes.

    Returns:
        On success, a tuple (ssh_environment_dict, None). On failure, a tuple
        (None, error_dict), where error_dict has keys "code" and "message".
    """
    ssh_key_path = git_config.get("ssh_key_path")
    if not ssh_key_path:
        return (
            None,
            {
                "code": GIT_AUTH_FAILED,
                "message": (
                    "Git SSH authentication failed: 'ssh_key_path' is missing "
                    "or empty in git configuration."
                ),
            },
        )

    if not Path(ssh_key_path).is_file():
        return (
            None,
            {
                "code": GIT_AUTH_FAILED,
                "message": (
                    "Git SSH authentication failed: ssh_key_path "
                    f"{ssh_key_path!r} does not exist or is not a regular file."
                ),
            },
        )

    known_hosts_path = git_config.get("known_hosts_path")
    if not known_hosts_path:
        return (
            None,
            {
                "code": GIT_AUTH_FAILED,
                "message": (
                    "Git SSH authentication failed: 'known_hosts_path' is missing "
                    "or empty in git configuration."
                ),
            },
        )

    if not Path(known_hosts_path).exists():
        return (
            None,
            {
                "code": GIT_AUTH_FAILED,
                "message": (
                    "Git SSH authentication failed: known_hosts_path "
                    f"{known_hosts_path!r} does not exist."
                ),
            },
        )

    ssh_command = (
        f"ssh -i {ssh_key_path} -o IdentitiesOnly=yes "
        f"-o UserKnownHostsFile={known_hosts_path} "
        "-o StrictHostKeyChecking=yes -o BatchMode=yes"
    )
    return ({"GIT_SSH_COMMAND": ssh_command}, None)


def classify_ssh_auth_stderr(stderr: str) -> Optional[str]:
    """
    Classify git remote stderr as an SSH authentication outcome.

    Args:
        stderr: The stderr text captured from a git remote operation.

    Returns:
        GIT_AUTH_FAILED when stderr indicates an SSH authentication or
        host-key failure, otherwise None.
    """
    if not stderr:
        return None
    lowered = stderr.lower()
    indicators = [
        "permission denied (publickey",
        "host key verification failed",
        "no matching host key type",
        "authentication failed",
    ]
    if any(indicator in lowered for indicator in indicators):
        return GIT_AUTH_FAILED
    if "could not read from remote repository" in lowered and "publickey" in lowered:
        return GIT_AUTH_FAILED
    return None
