"""
Remote-branch inspection: ``git_remote_branch_list`` and ``git_remote_branch_prune``.

TODO 487773a8 asked for a remote-branch command group. Most of what it listed
already exists under ``git_branch_*`` names -- publishing a branch is
``git_branch_push``, deleting one on the remote is ``git_branch_delete_remote``,
tracking is ``git_branch_track_remote`` / ``git_branch_set_upstream``, and
comparing two refs is ``git_branch_compare``. Two capabilities genuinely had no
command, and they are the two here.

WHAT WAS MISSING, AND WHY IT MATTERS

``git_branch_list(scope="remote")`` reads ``refs/remotes`` -- the remote-tracking
refs cached by the last fetch. It answers "what did the remote look like when we
last looked", which is a different question from "what is on the remote now", and
it answers nothing at all before the first fetch. The cas/local/main discipline
this project runs on needs the live answer: whether a branch exists on the remote
before deciding to publish or track it.

``git_remote_branch_list`` asks the remote directly (``git ls-remote``). Two
consequences follow, both deliberate:

* It works on a repository with no commits. The shared read gate
  (``check_read_availability``) refuses reads when ``HEAD`` does not resolve,
  which is right for ``git log`` and wrong here -- ls-remote never touches local
  history. This command therefore does its own availability check, requiring a
  repository but not a commit. That is the GIT_NO_COMMITS relaxation the TODO
  anticipated.
* Every entry is annotated with whether a local tracking ref exists for it, so
  the "which remote branches am I not tracking" question is one call, not a diff
  the caller has to compute against a second command's output.

``git_remote_branch_prune`` drops remote-tracking refs whose branch is gone from
the remote. That was previously reachable only as a side effect of
``git_branch_fetch(prune=True)`` -- you could not prune without also fetching.
It only ever removes local refs; nothing on the remote is touched.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.core.exceptions import ValidationError
from code_analysis.core.git_integration import is_git_available, is_git_repository
from code_analysis.core.git_remote_ops import (
    GIT_NOT_A_REPO,
    GIT_NOT_AVAILABLE,
    GIT_REMOTE_NOT_CONFIGURED,
    GIT_REMOTE_TIMEOUT,
    build_full_subprocess_env,
    git_remote_error_result,
    load_git_remote_config,
    run_git_subprocess,
)
from code_analysis.core.git_ssh_auth import GIT_AUTH_FAILED, classify_ssh_auth_stderr

GIT_REMOTE_BRANCH_LIST_FAILED = "GIT_REMOTE_BRANCH_LIST_FAILED"
GIT_REMOTE_BRANCH_PRUNE_FAILED = "GIT_REMOTE_BRANCH_PRUNE_FAILED"

DEFAULT_REMOTE = "origin"
_HEADS_PREFIX = "refs/heads/"


def _prepare_remote_call(
    command: BaseMCPCommand, project_id: str
) -> Tuple[Optional[Path], Optional[Dict[str, Any]], Optional[ErrorResult]]:
    """
    Resolve the repository and remote configuration for a network git call.

    Deliberately does NOT require a resolvable ``HEAD``: these commands talk to
    the remote, and a freshly initialised repository with no commits is a valid
    place to ask what the remote has.

    Args:
        command: The command instance, used to resolve the project root.
        project_id: Registered project identifier.

    Returns:
        ``(root, git_config, error)``. On any failure ``error`` is set and the
        other two are None.
    """
    try:
        root = command._resolve_project_root(project_id)
    except ValidationError as exc:
        return (
            None,
            None,
            ErrorResult(
                message=str(exc),
                code=cast(Any, "VALIDATION_ERROR"),
                details=({"field": exc.field} if getattr(exc, "field", None) else None),
            ),
        )

    if not is_git_available():
        return (
            None,
            None,
            git_remote_error_result(
                GIT_NOT_AVAILABLE, "git executable is not available", {}
            ),
        )
    if not is_git_repository(root):
        return (
            None,
            None,
            git_remote_error_result(
                GIT_NOT_A_REPO,
                f"{root} is not a git repository",
                {"root": str(root)},
            ),
        )

    git_config = load_git_remote_config(command._get_raw_config())
    if not git_config["remote_enabled"]:
        return (
            None,
            None,
            git_remote_error_result(
                GIT_REMOTE_NOT_CONFIGURED,
                "Remote git operations are not enabled in configuration",
                {},
            ),
        )
    return (root, git_config, None)


def _validated_remote(remote: Any) -> Tuple[str, Optional[ErrorResult]]:
    """Return a usable remote name, or the validation error explaining why not."""
    if not isinstance(remote, str) or not remote.strip():
        return (
            "",
            ErrorResult(
                message="remote must be a non-empty string",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "remote"},
            ),
        )
    value = remote.strip()
    if value.startswith("-"):
        # A leading dash would be read by git as an option, not a remote.
        return (
            "",
            ErrorResult(
                message="remote must not start with '-'",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "remote"},
            ),
        )
    return (value, None)


def _local_tracking_refs(root: Path, env: Dict[str, str], remote: str) -> set[str]:
    """Return the short names of remote-tracking refs already held locally."""
    returncode, stdout, _stderr, _timed_out = run_git_subprocess(
        [
            "git",
            "for-each-ref",
            "--format=%(refname:short)",
            f"refs/remotes/{remote}",
        ],
        cwd=root,
        env=env,
        timeout_seconds=30,
    )
    if returncode != 0:
        return set()
    prefix = f"{remote}/"
    names: set[str] = set()
    for line in stdout.splitlines():
        short = line.strip()
        if short.startswith(prefix):
            names.add(short[len(prefix) :])
    return names


def _parse_ls_remote(stdout: str) -> List[Dict[str, Any]]:
    """Parse ``git ls-remote --heads`` output into branch records."""
    branches: List[Dict[str, Any]] = []
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        commit, ref = parts[0].strip(), parts[1].strip()
        if not ref.startswith(_HEADS_PREFIX):
            continue
        branches.append(
            {
                "name": ref[len(_HEADS_PREFIX) :],
                "ref": ref,
                "commit": commit,
            }
        )
    return branches


class GitRemoteBranchListCommand(BaseMCPCommand):
    """MCP command listing the branches that exist on a remote right now."""

    name = "git_remote_branch_list"
    version = "1.0.0"
    descr = "List branches that exist on a remote right now (git ls-remote)."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_remote_branch_list"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "remote": {"type": "string"},
                "pattern": {"type": "string"},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_remote_branch_list."""
        return {
            "name": "git_remote_branch_list",
            "description": (
                "List the branches that exist on a remote AT THIS MOMENT, by "
                "asking the remote (git ls-remote --heads). Distinct from "
                "git_branch_list(scope='remote'), which reads the "
                "remote-tracking refs cached by the last fetch and therefore "
                "answers what the remote looked like when you last looked. "
                "Works on a repository with no commits, so it can be used to "
                "decide what to check out before anything has been fetched. "
                "Read-only: nothing local or remote is modified."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "remote": {
                    "type": "string",
                    "required": False,
                    "description": (
                        "Remote name or URL. Default: origin. A URL works even "
                        "when no remote is configured."
                    ),
                },
                "pattern": {
                    "type": "string",
                    "required": False,
                    "description": (
                        "Optional refspec pattern passed to ls-remote, e.g. "
                        "'feature/*'. Matching happens on the remote."
                    ),
                },
            },
            "return_value": {
                "branches": (
                    "List of {name, ref, commit, tracked_locally}. "
                    "tracked_locally says whether refs/remotes/<remote>/<name> "
                    "already exists here, so 'what am I not tracking' is one call."
                ),
                "count": "Number of branches on the remote.",
                "untracked_count": "How many of them have no local tracking ref.",
                "remote": "Echo of the remote that was queried.",
            },
            "error_cases": {
                GIT_REMOTE_BRANCH_LIST_FAILED: (
                    "ls-remote failed; stderr is included. A missing remote and "
                    "an unreachable host both land here."
                ),
                GIT_REMOTE_NOT_CONFIGURED: (
                    "Remote git operations are disabled in configuration."
                ),
                GIT_REMOTE_TIMEOUT: "The remote did not answer within the timeout.",
                GIT_AUTH_FAILED: "SSH authentication was rejected by the remote.",
            },
            "examples": [
                {"command": {"project_id": "<uuid>"}},
                {"command": {"project_id": "<uuid>", "remote": "origin"}},
                {"command": {"project_id": "<uuid>", "pattern": "feature/*"}},
            ],
            "related_commands": {
                "git_branch_list": "local and cached remote-tracking branches",
                "git_branch_track_remote": "create a local branch tracking one of these",
                "git_branch_push": "publish a local branch to the remote",
                "git_branch_delete_remote": "delete a branch on the remote",
                "git_remote_branch_prune": "drop tracking refs for branches gone from here",
            },
        }

    async def execute(
        self,
        project_id: str,
        remote: str = DEFAULT_REMOTE,
        pattern: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute git_remote_branch_list.

        Args:
            project_id: Registered project identifier.
            remote: Remote name or URL to query. Default ``origin``.
            pattern: Optional refspec pattern matched on the remote.
            **kwargs: Adapter context (ignored).

        Returns:
            SuccessResult with the remote's branches, or an ErrorResult.
        """
        _ = kwargs
        remote_name, remote_error = _validated_remote(remote)
        if remote_error is not None:
            return remote_error
        if pattern is not None and not isinstance(pattern, str):
            return ErrorResult(
                message="pattern must be a string",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "pattern"},
            )

        root, git_config, error = _prepare_remote_call(self, project_id)
        if error is not None:
            return error
        assert root is not None and git_config is not None

        env, auth_error = build_full_subprocess_env(git_config)
        if auth_error is not None:
            return git_remote_error_result(
                GIT_AUTH_FAILED,
                str(
                    auth_error.get(
                        "message", "SSH authentication is not configured correctly"
                    )
                ),
                {},
            )

        args = ["git", "ls-remote", "--heads", remote_name]
        if pattern and pattern.strip():
            args.append(pattern.strip())

        returncode, stdout, stderr, timed_out = run_git_subprocess(
            args,
            cwd=root,
            env=env,
            timeout_seconds=git_config["remote_timeout_seconds"],
        )
        if timed_out:
            return git_remote_error_result(
                GIT_REMOTE_TIMEOUT,
                (
                    "git ls-remote exceeded timeout of "
                    f"{git_config['remote_timeout_seconds']} seconds"
                ),
                {"remote": remote_name},
            )
        if returncode != 0:
            if classify_ssh_auth_stderr(stderr) == GIT_AUTH_FAILED:
                return git_remote_error_result(
                    GIT_AUTH_FAILED,
                    "SSH authentication failed during git ls-remote",
                    {"remote": remote_name},
                )
            return git_remote_error_result(
                GIT_REMOTE_BRANCH_LIST_FAILED,
                f"git ls-remote failed with exit code {returncode}",
                {"remote": remote_name, "stderr": stderr.strip()},
            )

        branches = _parse_ls_remote(stdout)
        tracked = _local_tracking_refs(root, env, remote_name)
        untracked = 0
        for branch in branches:
            is_tracked = branch["name"] in tracked
            branch["tracked_locally"] = is_tracked
            if not is_tracked:
                untracked += 1

        payload: Dict[str, Any] = {
            "success": True,
            "remote": remote_name,
            "pattern": pattern.strip() if isinstance(pattern, str) else None,
            "branches": branches,
            "count": len(branches),
            "untracked_count": untracked,
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))


class GitRemoteBranchPruneCommand(BaseMCPCommand):
    """MCP command dropping tracking refs for branches gone from the remote."""

    name = "git_remote_branch_prune"
    version = "1.0.0"
    descr = "Drop remote-tracking refs whose branch no longer exists on the remote."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_remote_branch_prune"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "remote": {"type": "string"},
                "dry_run": {"type": "boolean"},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_remote_branch_prune."""
        return {
            "name": "git_remote_branch_prune",
            "description": (
                "Remove remote-tracking refs (refs/remotes/<remote>/*) whose "
                "branch no longer exists on the remote. Previously this was "
                "reachable only as a side effect of git_branch_fetch(prune=true), "
                "so pruning meant also fetching. Touches LOCAL refs only: no "
                "branch on the remote and no local branch of your own is ever "
                "deleted by this command."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "remote": {
                    "type": "string",
                    "required": False,
                    "description": "Remote name. Default: origin.",
                },
                "dry_run": {
                    "type": "boolean",
                    "required": False,
                    "description": (
                        "Report what would be pruned and remove nothing. "
                        "Default false."
                    ),
                },
            },
            "return_value": {
                "pruned": "Refs removed (or that would be, under dry_run).",
                "pruned_count": "Length of that list.",
                "dry_run": "Echo of the flag.",
            },
            "error_cases": {
                GIT_REMOTE_BRANCH_PRUNE_FAILED: (
                    "git remote prune failed; stderr is included."
                ),
                GIT_REMOTE_NOT_CONFIGURED: (
                    "Remote git operations are disabled in configuration."
                ),
                GIT_REMOTE_TIMEOUT: "The remote did not answer within the timeout.",
                GIT_AUTH_FAILED: "SSH authentication was rejected by the remote.",
            },
            "examples": [
                {"command": {"project_id": "<uuid>", "dry_run": True}},
                {"command": {"project_id": "<uuid>", "remote": "origin"}},
            ],
            "best_practices": [
                "Run with dry_run=true first; the report lists every ref by name.",
                "Pair with git_remote_branch_list to see what the remote actually has.",
            ],
        }

    async def execute(
        self,
        project_id: str,
        remote: str = DEFAULT_REMOTE,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute git_remote_branch_prune.

        Args:
            project_id: Registered project identifier.
            remote: Remote whose stale tracking refs should be dropped.
            dry_run: Report without removing anything.
            **kwargs: Adapter context (ignored).

        Returns:
            SuccessResult listing the pruned refs, or an ErrorResult.
        """
        _ = kwargs
        remote_name, remote_error = _validated_remote(remote)
        if remote_error is not None:
            return remote_error
        if not isinstance(dry_run, bool):
            return ErrorResult(
                message="dry_run must be a boolean",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "dry_run"},
            )

        root, git_config, error = _prepare_remote_call(self, project_id)
        if error is not None:
            return error
        assert root is not None and git_config is not None

        env, auth_error = build_full_subprocess_env(git_config)
        if auth_error is not None:
            return git_remote_error_result(
                GIT_AUTH_FAILED,
                str(
                    auth_error.get(
                        "message", "SSH authentication is not configured correctly"
                    )
                ),
                {},
            )

        args = ["git", "remote", "prune", remote_name]
        if dry_run:
            args.insert(3, "--dry-run")

        returncode, stdout, stderr, timed_out = run_git_subprocess(
            args,
            cwd=root,
            env=env,
            timeout_seconds=git_config["remote_timeout_seconds"],
        )
        if timed_out:
            return git_remote_error_result(
                GIT_REMOTE_TIMEOUT,
                (
                    "git remote prune exceeded timeout of "
                    f"{git_config['remote_timeout_seconds']} seconds"
                ),
                {"remote": remote_name, "dry_run": dry_run},
            )
        if returncode != 0:
            if classify_ssh_auth_stderr(stderr) == GIT_AUTH_FAILED:
                return git_remote_error_result(
                    GIT_AUTH_FAILED,
                    "SSH authentication failed during git remote prune",
                    {"remote": remote_name},
                )
            return git_remote_error_result(
                GIT_REMOTE_BRANCH_PRUNE_FAILED,
                f"git remote prune failed with exit code {returncode}",
                {
                    "remote": remote_name,
                    "dry_run": dry_run,
                    "stderr": stderr.strip(),
                },
            )

        pruned = parse_pruned_refs(stdout)
        payload: Dict[str, Any] = {
            "success": True,
            "remote": remote_name,
            "dry_run": dry_run,
            "pruned": pruned,
            "pruned_count": len(pruned),
            "output": stdout.strip(),
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))


def parse_pruned_refs(stdout: str) -> List[str]:
    """
    Extract the pruned ref names from ``git remote prune`` output.

    Git prints a ``Pruning <remote>`` header, a ``URL: ...`` line, and then one
    ``* [pruned] <ref>`` (or ``* [would prune] <ref>`` under --dry-run) line per
    ref. Anything else is ignored rather than guessed at.

    Args:
        stdout: Raw command output.

    Returns:
        The ref names, in the order git reported them.
    """
    refs: List[str] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        for marker in ("* [pruned]", "* [would prune]"):
            if stripped.startswith(marker):
                candidate = stripped[len(marker) :].strip()
                if candidate:
                    refs.append(candidate)
                break
    return refs
