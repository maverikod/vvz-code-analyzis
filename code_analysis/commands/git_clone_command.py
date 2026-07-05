"""git_clone MCP command: clone a remote repository into a watch directory and
register the resulting working tree as a new project.

Clones into ``<watch_dir_path>/<target_name>`` (a depth-1 child of the watch
directory, matching the invariant that a ``projectid`` file is only recognized
at ``watch_dir/<subdir>/projectid`` — see ``code_analysis/core/project_discovery.py``).
After a successful clone, registers the new directory as a project by reusing
``code_analysis.commands.project_creation.CreateProjectCommand`` with
``use_existing_dir=True`` — the same mechanism ``create_project`` uses — so no
projectid-writing or DB-registration logic is duplicated here.

Requires remote operations to be enabled in configuration
(code_analysis.git.remote_enabled); when absent, fails fast with
GIT_REMOTE_NOT_CONFIGURED.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.git_worktree_base import validation_error
from code_analysis.core.git_integration import is_git_available
from code_analysis.core.git_remote_ops import (
    GIT_NOT_AVAILABLE,
    GIT_REMOTE_NOT_CONFIGURED,
    GIT_REMOTE_TIMEOUT,
    build_full_subprocess_env,
    git_remote_error_result,
    load_git_remote_config,
    run_git_subprocess,
)
from code_analysis.core.git_ssh_auth import GIT_AUTH_FAILED, classify_ssh_auth_stderr

GIT_CLONE_WATCH_DIR_NOT_FOUND = "GIT_CLONE_WATCH_DIR_NOT_FOUND"
GIT_CLONE_TARGET_EXISTS = "GIT_CLONE_TARGET_EXISTS"
GIT_CLONE_FAILED = "GIT_CLONE_FAILED"


def _validate_target_name(target_name: str) -> Optional[ErrorResult]:
    """Validate target_name: non-empty, no separators, no '.'/'..' , no leading '/'."""
    if not target_name or not target_name.strip():
        return validation_error("target_name must not be empty", "target_name")
    if target_name in (".", ".."):
        return validation_error("target_name must not be '.' or '..'", "target_name")
    if target_name.startswith("/"):
        return validation_error("target_name must not start with '/'", "target_name")
    if "/" in target_name or "\\" in target_name:
        return validation_error(
            "target_name must not contain path separators", "target_name"
        )
    return None


def _is_local_clone_url(url: str) -> bool:
    """True when url is a local filesystem path (file:// or plain path).

    Local clone URLs need no SSH authentication environment. This is a small
    accommodation so tests (and legitimate local mirrors) can clone via
    ``file://`` without requiring ssh_key_path/known_hosts_path to be
    configured.
    """
    if url.startswith("file://"):
        return True
    return "://" not in url and "@" not in url


class GitCloneCommand(BaseMCPCommand):
    """MCP command cloning a remote repository into a watch directory and
    registering the result as a new project."""

    name = "git_clone"
    version = "1.0.0"
    descr = (
        "Clone a remote repository into a watch directory and register the "
        "resulting working tree as a new project."
    )
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_clone"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": (
                        "Remote repository URL to clone from (SSH form, e.g. "
                        "git@host:group/repo.git), matching the existing git "
                        "remote authentication model. A local file:// URL is "
                        "also accepted (e.g. for local mirrors or tests) and "
                        "skips SSH authentication."
                    ),
                },
                "watch_dir_id": {
                    "type": "string",
                    "description": (
                        "UUID4 of the watch directory (a direct child of the "
                        "effective watch mount root, /var/casmgr/watched) to "
                        "clone the repository into. Must exist in the "
                        "watch_dirs table."
                    ),
                },
                "target_name": {
                    "type": "string",
                    "description": (
                        "Name of the new folder created inside the watch "
                        "directory; this becomes the project directory at "
                        "depth-1 under the watch dir, where a projectid file "
                        "is expected. Must be non-empty, must not contain "
                        "path separators, must not be '.' or '..', and must "
                        "not start with '/' (path traversal is rejected)."
                    ),
                },
                "branch": {
                    "type": "string",
                    "description": (
                        "Optional branch to check out after cloning "
                        "(passed as git clone --branch)."
                    ),
                },
                "depth": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "Optional shallow clone depth, must be a positive "
                        "integer (passed as git clone --depth)."
                    ),
                },
            },
            "required": ["url", "watch_dir_id", "target_name"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["GitCloneCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_clone."""
        return {
            "name": "git_clone",
            "description": cls.descr,
            "version": cls.version,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The git_clone command clones a remote git repository into a "
                "watch directory and registers the resulting working tree as "
                "a new project, in one step. It is the counterpart to "
                "create_project for repositories that already exist "
                "remotely: instead of creating an empty project directory, "
                "it materializes one from a remote clone.\n\n"
                "Operation flow:\n"
                "1. Validates target_name (non-empty, no path separators, "
                "not '.'/'..' , no leading '/').\n"
                "2. Verifies the git executable is available.\n"
                "3. Resolves watch_dir_id to its absolute path via the "
                "watch_dirs database table; fails with "
                "GIT_CLONE_WATCH_DIR_NOT_FOUND if the id is unknown or its "
                "path does not exist on disk.\n"
                "4. Computes dest = <watch_dir_path>/<target_name>; fails "
                "with GIT_CLONE_TARGET_EXISTS if dest already exists and is "
                "a non-empty directory or a file.\n"
                "5. Verifies remote git operations are enabled in "
                "configuration (code_analysis.git.remote_enabled); fails "
                "with GIT_REMOTE_NOT_CONFIGURED otherwise.\n"
                "6. Builds the SSH authentication environment from "
                "code_analysis.git (ssh_key_path/known_hosts_path); fails "
                "with GIT_AUTH_FAILED if misconfigured. Local file:// URLs "
                "skip this step.\n"
                "7. Runs git clone with optional --branch/--depth, bounded "
                "by remote_timeout_seconds; timeout yields GIT_REMOTE_TIMEOUT, "
                "SSH failures yield GIT_AUTH_FAILED, other non-zero exits "
                "yield GIT_CLONE_FAILED.\n"
                "8. On success, registers the cloned directory as a project "
                "by reusing CreateProjectCommand (use_existing_dir=True, "
                "scaffold=False, create_venv=False) — the same mechanism "
                "create_project uses — writing a projectid file at "
                "dest/projectid and inserting the projects row.\n\n"
                "Ownership note: the clone runs as the daemon user (root "
                "inside the all-in-one container deployment), so the new "
                "tree is root-owned. This is the accepted trade-off from the "
                "containerization work; this command does not chown."
            ),
            "parameters": {
                "url": {
                    "description": (
                        "Remote repository URL (SSH form) or a local "
                        "file:// URL for testing/local mirrors."
                    ),
                    "type": "string",
                    "required": True,
                },
                "watch_dir_id": {
                    "description": (
                        "Watch directory UUID4 to clone into; must exist in "
                        "the watch_dirs table and resolve to an existing "
                        "path on disk."
                    ),
                    "type": "string",
                    "required": True,
                },
                "target_name": {
                    "description": (
                        "New folder name inside the watch directory; "
                        "rejects path separators and traversal ('.', '..', "
                        "leading '/')."
                    ),
                    "type": "string",
                    "required": True,
                },
                "branch": {
                    "description": "Branch to check out after cloning.",
                    "type": "string",
                    "required": False,
                },
                "depth": {
                    "description": "Shallow clone depth (>= 1).",
                    "type": "integer",
                    "required": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Clone a repository into a watch directory",
                    "command": {
                        "url": "git@github.com:example/repo.git",
                        "watch_dir_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "target_name": "repo",
                    },
                    "explanation": (
                        "Clones the repository into "
                        "<watch_dir_path>/repo and registers it as a new "
                        "project."
                    ),
                },
                {
                    "description": "Shallow clone of a specific branch",
                    "command": {
                        "url": "git@github.com:example/repo.git",
                        "watch_dir_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "target_name": "repo",
                        "branch": "develop",
                        "depth": 1,
                    },
                    "explanation": (
                        "Clones only the develop branch with history depth 1."
                    ),
                },
            ],
            "error_cases": {
                "GIT_NOT_AVAILABLE": {
                    "description": "git executable is not available to the server process.",
                    "solution": "Install git or fix PATH for the service process.",
                },
                "GIT_CLONE_WATCH_DIR_NOT_FOUND": {
                    "description": "watch_dir_id is unknown or its path does not exist on disk.",
                    "solution": "Use list_watch_dirs to get a valid watch_dir_id.",
                },
                "GIT_CLONE_TARGET_EXISTS": {
                    "description": "dest already exists and is a non-empty directory or a file.",
                    "solution": "Choose a different target_name or remove the existing path.",
                },
                "GIT_REMOTE_NOT_CONFIGURED": {
                    "description": "Remote git operations are not enabled in configuration.",
                    "solution": "Set code_analysis.git.remote_enabled=true.",
                },
                "GIT_AUTH_FAILED": {
                    "description": "SSH authentication is misconfigured or was rejected by the remote.",
                    "solution": "Verify ssh_key_path/known_hosts_path and remote access.",
                },
                "GIT_REMOTE_TIMEOUT": {
                    "description": "git clone exceeded remote_timeout_seconds.",
                    "solution": "Retry, or raise code_analysis.git.remote_timeout_seconds.",
                },
                "GIT_CLONE_FAILED": {
                    "description": "git clone exited non-zero for a reason other than SSH auth.",
                    "solution": "Inspect the returned stderr for the underlying git error.",
                },
            },
            "return_value": {
                "success": {
                    "description": "Repository was cloned and registered as a project.",
                    "data": {
                        "project_id": "UUID4 identifier of the newly registered project.",
                        "path": "Absolute path to the cloned project directory.",
                        "url": "Remote URL that was cloned.",
                        "branch": "Resolved checked-out branch name.",
                        "head_sha": "HEAD commit sha of the clone, when resolvable.",
                    },
                },
                "error": {
                    "description": "Validation, watch-dir resolution, git availability, remote configuration, authentication, timeout, or clone failure.",
                },
            },
            "best_practices": [
                "Use list_watch_dirs to discover a valid watch_dir_id before cloning.",
                "Prefer depth=1 for large repositories when full history is not needed.",
                "Expect the cloned tree to be owned by the daemon user (root in the "
                "all-in-one container deployment); no chown is performed.",
                "Check GIT_CLONE_TARGET_EXISTS and choose a different target_name rather than retrying blindly.",
            ],
        }

    async def execute(
        self,
        url: str,
        watch_dir_id: str,
        target_name: str,
        branch: Optional[str] = None,
        depth: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_clone command."""
        _ = kwargs
        name_error = _validate_target_name(target_name)
        if name_error is not None:
            return name_error
        if not is_git_available():
            return git_remote_error_result(
                GIT_NOT_AVAILABLE, "git executable is not available", {}
            )

        database = self._open_database_from_config(auto_analyze=False)
        try:
            watch_dir_path_str = database.get_watch_dir_absolute_path(
                str(watch_dir_id or "")
            )
            if not watch_dir_path_str:
                return git_remote_error_result(
                    GIT_CLONE_WATCH_DIR_NOT_FOUND,
                    f"Watch directory {watch_dir_id!r} not found in database "
                    "or has no path set",
                    {"watch_dir_id": watch_dir_id},
                )
            watch_dir_path = Path(watch_dir_path_str)
            if not watch_dir_path.is_dir():
                return git_remote_error_result(
                    GIT_CLONE_WATCH_DIR_NOT_FOUND,
                    f"Watch directory path does not exist: {watch_dir_path}",
                    {"watch_dir_id": watch_dir_id, "path": str(watch_dir_path)},
                )

            dest = watch_dir_path / target_name
            if dest.exists():
                if dest.is_dir():
                    if any(dest.iterdir()):
                        return git_remote_error_result(
                            GIT_CLONE_TARGET_EXISTS,
                            f"Target directory already exists and is not empty: {dest}",
                            {"path": str(dest)},
                        )
                else:
                    return git_remote_error_result(
                        GIT_CLONE_TARGET_EXISTS,
                        f"Target path already exists and is not a directory: {dest}",
                        {"path": str(dest)},
                    )

            config_data = self._get_raw_config()
            git_config = load_git_remote_config(config_data)
            if not git_config["remote_enabled"]:
                return git_remote_error_result(
                    GIT_REMOTE_NOT_CONFIGURED,
                    "Remote git operations are not enabled in configuration",
                    {},
                )

            env: Optional[Dict[str, str]]
            if _is_local_clone_url(url):
                env = dict(os.environ)
            else:
                env, auth_error = build_full_subprocess_env(git_config)
                if auth_error is not None:
                    return git_remote_error_result(
                        GIT_AUTH_FAILED,
                        str(
                            auth_error.get(
                                "message",
                                "SSH authentication is not configured correctly",
                            )
                        ),
                        {},
                    )

            args = ["git", "clone"]
            if branch:
                args += ["--branch", branch]
            if depth is not None:
                args += ["--depth", str(depth)]
            args += [url, str(dest)]

            returncode, stdout, stderr, timed_out = run_git_subprocess(
                args,
                cwd=watch_dir_path,
                env=env,
                timeout_seconds=git_config["remote_timeout_seconds"],
            )
            if timed_out:
                return git_remote_error_result(
                    GIT_REMOTE_TIMEOUT,
                    (
                        "git clone exceeded timeout of "
                        f"{git_config['remote_timeout_seconds']} seconds"
                    ),
                    {"url": url, "target_name": target_name},
                )
            if returncode != 0:
                auth_code = classify_ssh_auth_stderr(stderr)
                if auth_code == GIT_AUTH_FAILED:
                    return git_remote_error_result(
                        GIT_AUTH_FAILED,
                        "SSH authentication failed during git clone",
                        {"url": url},
                    )
                return git_remote_error_result(
                    GIT_CLONE_FAILED,
                    f"git clone failed with exit code {returncode}",
                    {
                        "url": url,
                        "target_name": target_name,
                        "stderr": stderr.strip(),
                    },
                )

            head_sha: Optional[str] = None
            resolved_branch = branch
            rc_sha, out_sha, _err_sha, _to_sha = run_git_subprocess(
                ["git", "rev-parse", "HEAD"],
                cwd=dest,
                env=env,
                timeout_seconds=10.0,
            )
            if rc_sha == 0:
                head_sha = out_sha.strip()
            rc_branch, out_branch, _err_branch, _to_branch = run_git_subprocess(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=dest,
                env=env,
                timeout_seconds=10.0,
            )
            if rc_branch == 0 and out_branch.strip():
                resolved_branch = out_branch.strip()

            from .project_creation import CreateProjectCommand

            create_cmd = CreateProjectCommand(
                database=database,
                watch_dir_id=watch_dir_id,
                project_name=target_name,
                description=f"Cloned from {url}",
                use_existing_dir=True,
                scaffold=False,
                create_venv=False,
            )
            create_result = await create_cmd.execute()
            if not create_result.get("success"):
                return git_remote_error_result(
                    str(create_result.get("error", "GIT_CLONE_REGISTER_FAILED")),
                    create_result.get("message", "Failed to register cloned project"),
                    {"path": str(dest)},
                )

            payload: Dict[str, Any] = {
                "success": True,
                "project_id": create_result.get("project_id"),
                "path": str(dest),
                "url": url,
                "branch": resolved_branch,
                "head_sha": head_sha,
            }
            return SuccessResult(data=cast(Dict[str, Any], payload))
        finally:
            database.disconnect()
