"""
The ``git_remote_branch_*`` command group (TODO 487773a8).

Six commands that treat a branch ON THE REMOTE as the thing being operated on,
rather than a local branch that happens to have a remote counterpart. The
``git_branch_*`` family covers the local view well; this group covers the other
side, and each member here does something its nearest ``git_branch_*`` relative
cannot:

``git_remote_branch_list`` asks the remote what it has RIGHT NOW
(``git ls-remote``). ``git_branch_list(scope="remote")`` reads ``refs/remotes``
-- the refs cached by the last fetch -- so it answers what the remote looked like
when we last looked, and answers nothing at all before the first fetch. Two
consequences here are deliberate: it works on a repository with NO COMMITS,
because the shared read gate (``check_read_availability``) refuses reads when
``HEAD`` does not resolve and that is the wrong test for a command that reads no
local history (the GIT_NO_COMMITS relaxation the TODO anticipated); and every
entry carries ``tracked_locally``, so "which remote branches am I not tracking"
is one call rather than a diff against a second command's output.

``git_remote_branch_create`` publishes a local branch UNDER A GIVEN NAME on the
remote, via an explicit push refspec. ``git_branch_push`` can only push a branch
to its own name. It also applies the protected-branch guard to the name being
written on the remote rather than to the local name -- publishing local ``tmp``
as remote ``main`` is a write to ``main``, and guarding the source name would
miss it.

``git_remote_branch_delete`` deletes a branch on the remote behind the same
protected-branch guard plus an explicit ``force_confirm``.

``git_remote_branch_track`` binds a local branch to a remote one without the
caller first having to work out which of two commands applies: it creates a
tracking branch when the local branch does not exist, and sets the upstream when
it does.

``git_remote_branch_compare`` reports ahead/behind against the remote branch and,
by default, refreshes that single ref first. ``git_branch_compare`` compares
whatever is in the local cache, which is why its counts go stale (defect
d05492ef) -- a comparison against a week-old remote-tracking ref is a confident
wrong answer.

``git_remote_branch_prune`` drops remote-tracking refs whose branch is gone from
the remote. Previously reachable only as a side effect of
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
    evaluate_push_guards,
    git_remote_error_result,
    load_git_remote_config,
    run_git_subprocess,
)
from code_analysis.core.git_ssh_auth import GIT_AUTH_FAILED, classify_ssh_auth_stderr

GIT_REMOTE_BRANCH_LIST_FAILED = "GIT_REMOTE_BRANCH_LIST_FAILED"
GIT_REMOTE_BRANCH_PRUNE_FAILED = "GIT_REMOTE_BRANCH_PRUNE_FAILED"
GIT_REMOTE_BRANCH_CREATE_FAILED = "GIT_REMOTE_BRANCH_CREATE_FAILED"
GIT_REMOTE_BRANCH_DELETE_FAILED = "GIT_REMOTE_BRANCH_DELETE_FAILED"
GIT_REMOTE_BRANCH_TRACK_FAILED = "GIT_REMOTE_BRANCH_TRACK_FAILED"
GIT_REMOTE_BRANCH_COMPARE_FAILED = "GIT_REMOTE_BRANCH_COMPARE_FAILED"
GIT_REMOTE_BRANCH_NOT_FOUND = "GIT_REMOTE_BRANCH_NOT_FOUND"
GIT_CONFIRMATION_REQUIRED = "GIT_CONFIRMATION_REQUIRED"

DEFAULT_REMOTE = "origin"
_HEADS_PREFIX = "refs/heads/"
_LOCAL_GIT_TIMEOUT_SECONDS = 30


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


def _validated_branch(value: Any, field: str) -> Tuple[str, Optional[ErrorResult]]:
    """Return a usable branch name, or the validation error explaining why not."""
    if not isinstance(value, str) or not value.strip():
        return (
            "",
            ErrorResult(
                message=f"{field} must be a non-empty string",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": field},
            ),
        )
    name = value.strip()
    if name.startswith("-"):
        return (
            "",
            ErrorResult(
                message=f"{field} must not start with '-'",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": field},
            ),
        )
    return (name, None)


def _run_local(root: Path, args: List[str]) -> Tuple[int, str, str]:
    """Run a local (non-network) git command and return rc/stdout/stderr."""
    returncode, stdout, stderr, _timed_out = run_git_subprocess(
        args,
        cwd=root,
        env=None,
        timeout_seconds=_LOCAL_GIT_TIMEOUT_SECONDS,
    )
    return (returncode, stdout, stderr)


def current_branch_name(root: Path) -> Optional[str]:
    """Return the checked-out branch, or None when HEAD is detached."""
    returncode, stdout, _stderr = _run_local(root, ["git", "branch", "--show-current"])
    if returncode != 0:
        return None
    return stdout.strip() or None


def local_branch_exists(root: Path, branch: str) -> bool:
    """Return whether ``refs/heads/<branch>`` exists."""
    returncode, _stdout, _stderr = _run_local(
        root, ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"]
    )
    return returncode == 0


def remote_tracking_ref_exists(root: Path, ref: str) -> bool:
    """Return whether a remote-tracking ref such as ``origin/main`` exists."""
    returncode, _stdout, _stderr = _run_local(
        root, ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/{ref}"]
    )
    return returncode == 0


def configured_remotes(root: Path) -> set[str]:
    """Return the names of the remotes configured in this repository."""
    returncode, stdout, _stderr = _run_local(root, ["git", "remote"])
    if returncode != 0:
        return set()
    return {line.strip() for line in stdout.splitlines() if line.strip()}


def split_remote_branch(
    value: str, default_remote: str, known_remotes: set[str]
) -> Tuple[str, str]:
    """
    Split ``origin/feature/x`` into ``("origin", "feature/x")``.

    The first segment counts as a remote ONLY when it is actually a configured
    remote. Splitting on the first slash unconditionally would read the ordinary
    branch name ``feature/x`` as branch ``x`` on a remote called ``feature`` --
    harmless when no such remote exists and quietly destructive when one does,
    since this helper feeds a delete.

    Args:
        value: Remote-qualified or bare branch name.
        default_remote: Remote to assume when the value carries none.
        known_remotes: Names of the repository's configured remotes.

    Returns:
        Tuple of (remote, branch).
    """
    if "/" in value:
        candidate_remote, candidate_branch = value.split("/", 1)
        if candidate_remote in known_remotes and candidate_branch:
            return (candidate_remote, candidate_branch)
    return (default_remote, value)


def parse_ahead_behind(stdout: str) -> Optional[Tuple[int, int]]:
    """
    Parse ``git rev-list --left-right --count A...B`` output.

    Args:
        stdout: Raw command output, expected as two tab-separated integers.

    Returns:
        ``(ahead, behind)`` or None when the output is not the expected shape.
        Left is the first ref given, so with ``local...remote`` left is "ahead".
    """
    parts = stdout.split()
    if len(parts) != 2:
        return None
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        return None


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


class GitRemoteBranchCreateCommand(BaseMCPCommand):
    """MCP command publishing a local branch to a remote under a chosen name."""

    name = "git_remote_branch_create"
    version = "1.0.0"
    descr = "Publish a local branch to a remote, optionally under a different name."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_remote_branch_create"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "branch": {"type": "string"},
                "remote": {"type": "string"},
                "remote_branch": {"type": "string"},
                "set_upstream": {"type": "boolean", "default": True},
                "force": {"type": "boolean", "default": False},
                "protected_override": {"type": "boolean", "default": False},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_remote_branch_create."""
        return {
            "name": "git_remote_branch_create",
            "description": (
                "Publish a local branch to a remote using an explicit push "
                "refspec, so it can be created there under a DIFFERENT name. "
                "git_branch_push can only push a branch to its own name. The "
                "protected-branch guard is applied to the name being written on "
                "the remote, not to the local source name: publishing local "
                "'tmp' as remote 'main' is a write to main, and checking the "
                "source name would miss it."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "branch": {
                    "type": "string",
                    "required": False,
                    "description": "Local branch to publish. Default: current branch.",
                },
                "remote": {
                    "type": "string",
                    "required": False,
                    "description": "Remote name. Default: origin.",
                },
                "remote_branch": {
                    "type": "string",
                    "required": False,
                    "description": (
                        "Name to create on the remote. Default: same as branch."
                    ),
                },
                "set_upstream": {
                    "type": "boolean",
                    "required": False,
                    "description": (
                        "Bind the local branch to the published one. Default true "
                        "-- publishing without tracking is rarely what is meant."
                    ),
                },
                "force": {
                    "type": "boolean",
                    "required": False,
                    "description": (
                        "Overwrite a diverged remote branch. Still subject to "
                        "allow_force_push in configuration."
                    ),
                },
                "protected_override": {
                    "type": "boolean",
                    "required": False,
                    "description": (
                        "Required to write a remote branch named in "
                        "protected_branches."
                    ),
                },
            },
            "return_value": {
                "branch": "Local branch that was pushed.",
                "remote_branch": "Name created on the remote.",
                "refspec": "The refspec git was given.",
                "set_upstream": "Whether tracking was configured.",
            },
            "error_cases": {
                GIT_REMOTE_BRANCH_CREATE_FAILED: "The push failed; stderr is included.",
                "GIT_PROTECTED_BRANCH": (
                    "The remote branch name is protected and no "
                    "protected_override was supplied."
                ),
                "GIT_FORCE_PUSH_DISABLED": (
                    "force was requested but allow_force_push is off."
                ),
                GIT_REMOTE_NOT_CONFIGURED: "Remote git operations are disabled.",
                GIT_REMOTE_TIMEOUT: "The remote did not answer within the timeout.",
                GIT_AUTH_FAILED: "SSH authentication was rejected by the remote.",
            },
            "examples": [
                {"command": {"project_id": "<uuid>", "branch": "feature/x"}},
                {
                    "command": {
                        "project_id": "<uuid>",
                        "branch": "local",
                        "remote_branch": "review/local",
                    }
                },
            ],
            "related_commands": {
                "git_branch_push": "push a branch to its own name on the remote",
                "git_remote_branch_delete": "remove it again",
                "git_remote_branch_list": "check what the remote already has",
            },
        }

    async def execute(
        self,
        project_id: str,
        branch: Optional[str] = None,
        remote: str = DEFAULT_REMOTE,
        remote_branch: Optional[str] = None,
        set_upstream: bool = True,
        force: bool = False,
        protected_override: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute git_remote_branch_create.

        Args:
            project_id: Registered project identifier.
            branch: Local branch to publish; defaults to the current branch.
            remote: Remote to publish to.
            remote_branch: Name to create on the remote; defaults to ``branch``.
            set_upstream: Bind the local branch to the published one.
            force: Overwrite a diverged remote branch.
            protected_override: Permit writing a protected remote branch name.
            **kwargs: Adapter context (ignored).

        Returns:
            SuccessResult describing the published branch, or an ErrorResult.
        """
        _ = kwargs
        remote_name, remote_error = _validated_remote(remote)
        if remote_error is not None:
            return remote_error

        root, git_config, error = _prepare_remote_call(self, project_id)
        if error is not None:
            return error
        assert root is not None and git_config is not None

        source = branch if branch is not None else current_branch_name(root)
        if not source:
            return ErrorResult(
                message="branch is required when HEAD is detached",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "branch"},
            )
        source_name, branch_error = _validated_branch(source, "branch")
        if branch_error is not None:
            return branch_error

        target = remote_branch if remote_branch is not None else source_name
        target_name, target_error = _validated_branch(target, "remote_branch")
        if target_error is not None:
            return target_error

        # Guard the name being WRITTEN on the remote. git_branch_push guards the
        # local name, which is the same thing only when they match -- and this
        # command exists precisely because they need not.
        guard = evaluate_push_guards(
            target_name,
            protected_branches=git_config["protected_branches"],
            protected_override=protected_override,
            force=force,
            allow_force_push_config=git_config["allow_force_push"],
        )
        if guard is not None:
            code, message = guard
            return git_remote_error_result(
                code,
                message,
                {"branch": source_name, "remote_branch": target_name},
            )

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

        refspec = f"{source_name}:{_HEADS_PREFIX}{target_name}"
        args = ["git", "push"]
        if force:
            args.append("--force")
        if set_upstream:
            args.append("--set-upstream")
        args.extend([remote_name, refspec])

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
                    "git push exceeded timeout of "
                    f"{git_config['remote_timeout_seconds']} seconds"
                ),
                {"remote": remote_name, "refspec": refspec},
            )
        if returncode != 0:
            if classify_ssh_auth_stderr(stderr) == GIT_AUTH_FAILED:
                return git_remote_error_result(
                    GIT_AUTH_FAILED,
                    "SSH authentication failed during git push",
                    {"remote": remote_name, "refspec": refspec},
                )
            return git_remote_error_result(
                GIT_REMOTE_BRANCH_CREATE_FAILED,
                f"git push failed with exit code {returncode}",
                {
                    "remote": remote_name,
                    "branch": source_name,
                    "remote_branch": target_name,
                    "refspec": refspec,
                    "stderr": stderr.strip(),
                },
            )

        payload: Dict[str, Any] = {
            "success": True,
            "remote": remote_name,
            "branch": source_name,
            "remote_branch": target_name,
            "refspec": refspec,
            "set_upstream": set_upstream,
            "forced": force,
            "output": (stdout + stderr).strip(),
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))


class GitRemoteBranchDeleteCommand(BaseMCPCommand):
    """MCP command deleting a branch on the remote."""

    name = "git_remote_branch_delete"
    version = "1.0.0"
    descr = "Delete a branch on a remote, behind a protected-branch guard."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_remote_branch_delete"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "remote_branch": {"type": "string"},
                "remote": {"type": "string"},
                "force_confirm": {"type": "boolean"},
                "protected_override": {"type": "boolean", "default": False},
            },
            "required": ["project_id", "remote_branch", "force_confirm"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_remote_branch_delete."""
        return {
            "name": "git_remote_branch_delete",
            "description": (
                "Delete a branch on a remote (git push --delete). Deleting a "
                "remote branch destroys work for everyone using it, so this "
                "command carries two independent guards: force_confirm must be "
                "true, and a name listed in protected_branches additionally "
                "needs protected_override. Nothing local is touched -- the "
                "local branch and its tracking ref both survive; use "
                "git_remote_branch_prune to clean the stale tracking ref up "
                "afterwards."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "remote_branch": {
                    "type": "string",
                    "required": True,
                    "description": (
                        "Branch to delete on the remote. Accepts 'origin/x' or "
                        "a bare 'x'."
                    ),
                },
                "remote": {
                    "type": "string",
                    "required": False,
                    "description": (
                        "Remote name. Default: origin, or the prefix of "
                        "remote_branch when it carries one."
                    ),
                },
                "force_confirm": {
                    "type": "boolean",
                    "required": True,
                    "description": (
                        "Must be true. An explicit acknowledgement that this "
                        "removes the branch for everyone."
                    ),
                },
                "protected_override": {
                    "type": "boolean",
                    "required": False,
                    "description": "Required for a name in protected_branches.",
                },
            },
            "return_value": {
                "remote_branch": "The branch that was deleted.",
                "remote": "The remote it was deleted from.",
            },
            "error_cases": {
                GIT_CONFIRMATION_REQUIRED: "force_confirm was not true.",
                GIT_REMOTE_BRANCH_DELETE_FAILED: (
                    "The delete failed; stderr is included. A branch that does "
                    "not exist on the remote lands here."
                ),
                "GIT_PROTECTED_BRANCH": "The branch is protected by configuration.",
                GIT_REMOTE_NOT_CONFIGURED: "Remote git operations are disabled.",
                GIT_REMOTE_TIMEOUT: "The remote did not answer within the timeout.",
                GIT_AUTH_FAILED: "SSH authentication was rejected by the remote.",
            },
            "examples": [
                {
                    "command": {
                        "project_id": "<uuid>",
                        "remote_branch": "feature/done",
                        "force_confirm": True,
                    }
                }
            ],
            "related_commands": {
                "git_branch_delete_remote": "the original single-remote form",
                "git_remote_branch_prune": "clean up tracking refs afterwards",
                "git_remote_branch_list": "confirm what is actually there first",
            },
        }

    async def execute(
        self,
        project_id: str,
        remote_branch: str,
        remote: Optional[str] = None,
        force_confirm: bool = False,
        protected_override: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute git_remote_branch_delete.

        Args:
            project_id: Registered project identifier.
            remote_branch: Branch to delete, bare or remote-qualified.
            remote: Remote name; inferred from ``remote_branch`` when omitted.
            force_confirm: Must be true; an explicit acknowledgement.
            protected_override: Required for a protected branch name.
            **kwargs: Adapter context (ignored).

        Returns:
            SuccessResult naming the deleted branch, or an ErrorResult.
        """
        _ = kwargs
        raw_name, name_error = _validated_branch(remote_branch, "remote_branch")
        if name_error is not None:
            return name_error

        root, git_config, error = _prepare_remote_call(self, project_id)
        if error is not None:
            return error
        assert root is not None and git_config is not None

        # Resolving the remote needs the repository: only a CONFIGURED remote may
        # claim the prefix of "feature/x", or an ordinary branch name would be
        # read as a branch on a remote called "feature".
        if remote is None:
            inferred_remote, branch_name = split_remote_branch(
                raw_name, DEFAULT_REMOTE, configured_remotes(root)
            )
        else:
            inferred_remote, branch_name = (remote, raw_name)
        remote_name, remote_error = _validated_remote(inferred_remote)
        if remote_error is not None:
            return remote_error

        if force_confirm is not True:
            return git_remote_error_result(
                GIT_CONFIRMATION_REQUIRED,
                (
                    f"Deleting {branch_name!r} on {remote_name!r} removes it for "
                    "everyone; pass force_confirm=true to proceed"
                ),
                {"remote": remote_name, "remote_branch": branch_name},
            )

        guard = evaluate_push_guards(
            branch_name,
            protected_branches=git_config["protected_branches"],
            protected_override=protected_override,
            force=False,
            allow_force_push_config=git_config["allow_force_push"],
        )
        if guard is not None:
            code, message = guard
            return git_remote_error_result(
                code, message, {"remote": remote_name, "remote_branch": branch_name}
            )

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

        returncode, stdout, stderr, timed_out = run_git_subprocess(
            ["git", "push", remote_name, "--delete", branch_name],
            cwd=root,
            env=env,
            timeout_seconds=git_config["remote_timeout_seconds"],
        )
        if timed_out:
            return git_remote_error_result(
                GIT_REMOTE_TIMEOUT,
                (
                    "git push --delete exceeded timeout of "
                    f"{git_config['remote_timeout_seconds']} seconds"
                ),
                {"remote": remote_name, "remote_branch": branch_name},
            )
        if returncode != 0:
            if classify_ssh_auth_stderr(stderr) == GIT_AUTH_FAILED:
                return git_remote_error_result(
                    GIT_AUTH_FAILED,
                    "SSH authentication failed during git push --delete",
                    {"remote": remote_name, "remote_branch": branch_name},
                )
            return git_remote_error_result(
                GIT_REMOTE_BRANCH_DELETE_FAILED,
                f"git push --delete failed with exit code {returncode}",
                {
                    "remote": remote_name,
                    "remote_branch": branch_name,
                    "stderr": stderr.strip(),
                },
            )

        payload: Dict[str, Any] = {
            "success": True,
            "remote": remote_name,
            "remote_branch": branch_name,
            "deleted": True,
            "output": (stdout + stderr).strip(),
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))


class GitRemoteBranchTrackCommand(BaseMCPCommand):
    """MCP command binding a local branch to a remote one."""

    name = "git_remote_branch_track"
    version = "1.0.0"
    descr = "Track a remote branch: create the local branch or set its upstream."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_remote_branch_track"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "remote_branch": {"type": "string"},
                "local_branch": {"type": "string"},
                "remote": {"type": "string"},
                "checkout": {"type": "boolean", "default": False},
            },
            "required": ["project_id", "remote_branch"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_remote_branch_track."""
        return {
            "name": "git_remote_branch_track",
            "description": (
                "Bind a local branch to a remote one, whether or not the local "
                "branch already exists. Previously the caller had to know which "
                "case they were in and pick between git_branch_track_remote "
                "(creates, fails if the branch exists) and "
                "git_branch_set_upstream (sets upstream, fails if it does not). "
                "This does the right one and reports which in 'action'. Local "
                "operation: it uses the remote-tracking ref already on disk and "
                "opens no network connection, so fetch first (or check with "
                "git_remote_branch_list) if the ref may be missing."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "remote_branch": {
                    "type": "string",
                    "required": True,
                    "description": (
                        "Remote branch to track. Accepts 'origin/x' or a bare 'x'."
                    ),
                },
                "local_branch": {
                    "type": "string",
                    "required": False,
                    "description": (
                        "Local branch name. Default: the remote branch name "
                        "without its remote prefix."
                    ),
                },
                "remote": {
                    "type": "string",
                    "required": False,
                    "description": "Remote name when remote_branch carries none.",
                },
                "checkout": {
                    "type": "boolean",
                    "required": False,
                    "description": (
                        "Check the branch out afterwards. Default FALSE: moving "
                        "the working tree is a side effect nobody asked for when "
                        "they asked to track a branch."
                    ),
                },
            },
            "return_value": {
                "action": "'created' or 'upstream_set' -- which case applied.",
                "local_branch": "The local branch now tracking.",
                "upstream": "The remote-tracking ref it follows.",
                "checked_out": "Whether the working tree was moved.",
            },
            "error_cases": {
                GIT_REMOTE_BRANCH_NOT_FOUND: (
                    "No refs/remotes/<remote>/<branch> on disk. Fetch first; "
                    "this command does not reach the network."
                ),
                GIT_REMOTE_BRANCH_TRACK_FAILED: "The git call failed; stderr included.",
            },
            "examples": [
                {"command": {"project_id": "<uuid>", "remote_branch": "origin/cas"}},
                {
                    "command": {
                        "project_id": "<uuid>",
                        "remote_branch": "origin/main",
                        "local_branch": "main",
                    }
                },
            ],
            "related_commands": {
                "git_branch_track_remote": "create-only form",
                "git_branch_set_upstream": "set-upstream-only form",
                "git_remote_branch_list": "see what the remote has to track",
            },
        }

    async def execute(
        self,
        project_id: str,
        remote_branch: str,
        local_branch: Optional[str] = None,
        remote: Optional[str] = None,
        checkout: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute git_remote_branch_track.

        Args:
            project_id: Registered project identifier.
            remote_branch: Remote branch, bare or remote-qualified.
            local_branch: Local branch name; defaults to the remote branch name.
            remote: Remote name when ``remote_branch`` carries none.
            checkout: Check the resulting branch out.
            **kwargs: Adapter context (ignored).

        Returns:
            SuccessResult naming the action taken, or an ErrorResult.
        """
        _ = kwargs
        raw_name, name_error = _validated_branch(remote_branch, "remote_branch")
        if name_error is not None:
            return name_error

        if not isinstance(checkout, bool):
            return ErrorResult(
                message="checkout must be a boolean",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "checkout"},
            )

        try:
            root = self._resolve_project_root(project_id)
        except ValidationError as exc:
            return ErrorResult(
                message=str(exc),
                code=cast(Any, "VALIDATION_ERROR"),
                details=({"field": exc.field} if getattr(exc, "field", None) else None),
            )
        if not is_git_available():
            return git_remote_error_result(
                GIT_NOT_AVAILABLE, "git executable is not available", {}
            )
        if not is_git_repository(root):
            return git_remote_error_result(
                GIT_NOT_A_REPO, f"{root} is not a git repository", {"root": str(root)}
            )

        # Same rule as delete: the prefix of "feature/x" is a remote only when a
        # remote by that name actually exists.
        if remote is None:
            remote_name, branch_name = split_remote_branch(
                raw_name, DEFAULT_REMOTE, configured_remotes(root)
            )
        else:
            remote_name, branch_name = (remote, raw_name)
        remote_name, remote_error = _validated_remote(remote_name)
        if remote_error is not None:
            return remote_error

        target_local = local_branch if local_branch is not None else branch_name
        local_name, local_error = _validated_branch(target_local, "local_branch")
        if local_error is not None:
            return local_error

        upstream = f"{remote_name}/{branch_name}"
        if not remote_tracking_ref_exists(root, upstream):
            return git_remote_error_result(
                GIT_REMOTE_BRANCH_NOT_FOUND,
                (
                    f"No remote-tracking ref {upstream!r} on disk. This command "
                    "reads local refs only -- fetch the remote first, or check "
                    "git_remote_branch_list to see whether the branch exists."
                ),
                {"remote": remote_name, "remote_branch": branch_name},
            )

        if local_branch_exists(root, local_name):
            action = "upstream_set"
            args = ["git", "branch", f"--set-upstream-to={upstream}", local_name]
        else:
            action = "created"
            args = ["git", "branch", "--track", local_name, upstream]

        returncode, stdout, stderr = _run_local(root, args)
        if returncode != 0:
            return git_remote_error_result(
                GIT_REMOTE_BRANCH_TRACK_FAILED,
                f"git branch failed with exit code {returncode}",
                {
                    "action": action,
                    "local_branch": local_name,
                    "upstream": upstream,
                    "stderr": stderr.strip(),
                },
            )

        checked_out = False
        if checkout:
            rc_checkout, _out, err_checkout = _run_local(
                root, ["git", "checkout", local_name]
            )
            if rc_checkout != 0:
                return git_remote_error_result(
                    GIT_REMOTE_BRANCH_TRACK_FAILED,
                    (
                        f"tracking was configured ({action}) but checkout failed "
                        f"with exit code {rc_checkout}"
                    ),
                    {
                        "action": action,
                        "local_branch": local_name,
                        "upstream": upstream,
                        "stderr": err_checkout.strip(),
                    },
                )
            checked_out = True

        payload: Dict[str, Any] = {
            "success": True,
            "action": action,
            "remote": remote_name,
            "remote_branch": branch_name,
            "local_branch": local_name,
            "upstream": upstream,
            "checked_out": checked_out,
            "output": (stdout + stderr).strip(),
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))


class GitRemoteBranchCompareCommand(BaseMCPCommand):
    """MCP command comparing a local branch against its remote counterpart."""

    name = "git_remote_branch_compare"
    version = "1.0.0"
    descr = "Compare a local branch with a remote one, refreshing the ref first."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_remote_branch_compare"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "branch": {"type": "string"},
                "remote": {"type": "string"},
                "remote_branch": {"type": "string"},
                "fetch_first": {"type": "boolean", "default": True},
                "max_commits": {"type": "integer", "minimum": 0, "default": 20},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_remote_branch_compare."""
        return {
            "name": "git_remote_branch_compare",
            "description": (
                "Report how far a local branch is ahead of and behind its remote "
                "counterpart, refreshing that one ref first by default. "
                "git_branch_compare compares whatever is in the local cache, so "
                "its counts silently go stale as soon as the remote moves "
                "(defect d05492ef) -- a comparison against a week-old "
                "remote-tracking ref is a confident wrong answer. The refresh is "
                "scoped to the single ref being compared, not a full fetch. Pass "
                "fetch_first=false to compare the cache deliberately; the "
                "response always says which you got."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "branch": {
                    "type": "string",
                    "required": False,
                    "description": "Local branch. Default: current branch.",
                },
                "remote": {
                    "type": "string",
                    "required": False,
                    "description": "Remote name. Default: origin.",
                },
                "remote_branch": {
                    "type": "string",
                    "required": False,
                    "description": "Remote branch name. Default: same as branch.",
                },
                "fetch_first": {
                    "type": "boolean",
                    "required": False,
                    "description": (
                        "Refresh the remote ref before comparing. Default true."
                    ),
                },
                "max_commits": {
                    "type": "integer",
                    "required": False,
                    "description": "Commits to list per side. 0 for counts only.",
                },
            },
            "return_value": {
                "ahead": "Commits the local branch has that the remote does not.",
                "behind": "Commits the remote has that the local branch does not.",
                "fetched": "Whether the remote ref was refreshed for this answer.",
                "ahead_commits": "Up to max_commits local-only commits.",
                "behind_commits": "Up to max_commits remote-only commits.",
                "in_sync": "True when both counts are zero.",
            },
            "error_cases": {
                GIT_REMOTE_BRANCH_NOT_FOUND: (
                    "The local branch or the remote-tracking ref does not exist; "
                    "which one is named in the details."
                ),
                GIT_REMOTE_BRANCH_COMPARE_FAILED: "The comparison failed.",
                GIT_REMOTE_NOT_CONFIGURED: (
                    "Remote git operations are disabled, so fetch_first cannot run."
                ),
                GIT_REMOTE_TIMEOUT: "The remote did not answer within the timeout.",
            },
            "examples": [
                {"command": {"project_id": "<uuid>"}},
                {
                    "command": {
                        "project_id": "<uuid>",
                        "branch": "local",
                        "remote_branch": "main",
                    }
                },
                {"command": {"project_id": "<uuid>", "fetch_first": False}},
            ],
            "related_commands": {
                "git_branch_compare": "compare any two refs from the local cache",
                "git_branch_sync_status": "the same question for every branch",
                "git_remote_branch_list": "what the remote has at all",
            },
        }

    async def execute(
        self,
        project_id: str,
        branch: Optional[str] = None,
        remote: str = DEFAULT_REMOTE,
        remote_branch: Optional[str] = None,
        fetch_first: bool = True,
        max_commits: int = 20,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute git_remote_branch_compare.

        Args:
            project_id: Registered project identifier.
            branch: Local branch; defaults to the current branch.
            remote: Remote name.
            remote_branch: Remote branch name; defaults to ``branch``.
            fetch_first: Refresh the single remote ref before comparing.
            max_commits: Commits to list per side; 0 for counts only.
            **kwargs: Adapter context (ignored).

        Returns:
            SuccessResult with ahead/behind and commit lists, or an ErrorResult.
        """
        _ = kwargs
        remote_name, remote_error = _validated_remote(remote)
        if remote_error is not None:
            return remote_error
        if isinstance(max_commits, bool) or not isinstance(max_commits, int):
            return ErrorResult(
                message="max_commits must be an integer",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "max_commits"},
            )
        if max_commits < 0:
            return ErrorResult(
                message="max_commits must not be negative",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "max_commits"},
            )

        root, git_config, error = _prepare_remote_call(self, project_id)
        if error is not None:
            return error
        assert root is not None and git_config is not None

        source = branch if branch is not None else current_branch_name(root)
        if not source:
            return ErrorResult(
                message="branch is required when HEAD is detached",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "branch"},
            )
        local_name, branch_error = _validated_branch(source, "branch")
        if branch_error is not None:
            return branch_error

        target = remote_branch if remote_branch is not None else local_name
        target_name, target_error = _validated_branch(target, "remote_branch")
        if target_error is not None:
            return target_error

        if not local_branch_exists(root, local_name):
            return git_remote_error_result(
                GIT_REMOTE_BRANCH_NOT_FOUND,
                f"Local branch {local_name!r} does not exist",
                {"missing": "local", "branch": local_name},
            )

        fetched = False
        if fetch_first:
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
            returncode, _stdout, stderr, timed_out = run_git_subprocess(
                ["git", "fetch", remote_name, target_name],
                cwd=root,
                env=env,
                timeout_seconds=git_config["remote_timeout_seconds"],
            )
            if timed_out:
                return git_remote_error_result(
                    GIT_REMOTE_TIMEOUT,
                    (
                        "git fetch exceeded timeout of "
                        f"{git_config['remote_timeout_seconds']} seconds"
                    ),
                    {"remote": remote_name, "remote_branch": target_name},
                )
            if returncode != 0:
                return git_remote_error_result(
                    GIT_REMOTE_BRANCH_COMPARE_FAILED,
                    (
                        "could not refresh the remote ref before comparing; "
                        "pass fetch_first=false to compare the local cache "
                        "deliberately"
                    ),
                    {
                        "remote": remote_name,
                        "remote_branch": target_name,
                        "stderr": stderr.strip(),
                    },
                )
            fetched = True

        upstream = f"{remote_name}/{target_name}"
        if not remote_tracking_ref_exists(root, upstream):
            return git_remote_error_result(
                GIT_REMOTE_BRANCH_NOT_FOUND,
                f"No remote-tracking ref {upstream!r}",
                {"missing": "remote", "remote_branch": target_name},
            )

        returncode, stdout, stderr = _run_local(
            root,
            [
                "git",
                "rev-list",
                "--left-right",
                "--count",
                f"{local_name}...{upstream}",
            ],
        )
        counts = parse_ahead_behind(stdout) if returncode == 0 else None
        if counts is None:
            return git_remote_error_result(
                GIT_REMOTE_BRANCH_COMPARE_FAILED,
                f"could not count commits between {local_name!r} and {upstream!r}",
                {"stderr": stderr.strip(), "stdout": stdout.strip()},
            )
        ahead, behind = counts

        ahead_commits: List[str] = []
        behind_commits: List[str] = []
        if max_commits > 0:
            for spec, sink in (
                (f"{upstream}..{local_name}", ahead_commits),
                (f"{local_name}..{upstream}", behind_commits),
            ):
                rc_log, out_log, _err_log = _run_local(
                    root,
                    ["git", "log", "--oneline", f"--max-count={max_commits}", spec],
                )
                if rc_log == 0:
                    sink.extend(
                        line.strip() for line in out_log.splitlines() if line.strip()
                    )

        payload: Dict[str, Any] = {
            "success": True,
            "branch": local_name,
            "remote": remote_name,
            "remote_branch": target_name,
            "upstream": upstream,
            "fetched": fetched,
            "ahead": ahead,
            "behind": behind,
            "in_sync": ahead == 0 and behind == 0,
            "ahead_commits": ahead_commits,
            "behind_commits": behind_commits,
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))
