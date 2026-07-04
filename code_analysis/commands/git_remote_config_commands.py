"""MCP commands for local git remote configuration management.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type, cast
from urllib.parse import urlparse

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.command_metadata_helpers import (
    build_command_metadata,
    parameters_from_schema,
    simple_success_return,
)
from code_analysis.core.git_integration import is_git_available, is_git_repository
from code_analysis.core.git_remote_ops import (
    GIT_NOT_A_REPO,
    GIT_NOT_AVAILABLE,
    git_remote_error_result,
    run_git_subprocess,
)

LOCAL_GIT_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class RemoteConfigOperation:
    """The local git remote operation to execute."""

    operation: str
    args: List[str]
    remote: str
    url: Optional[str] = None
    old_name: Optional[str] = None
    new_name: Optional[str] = None


def _validate_remote_name(name: str, field: str = "name") -> Optional[ErrorResult]:
    """Validate a remote name accepted by the MCP surface."""
    if not name.strip():
        return ErrorResult(
            message="Remote name must not be empty",
            code=cast(Any, "VALIDATION_ERROR"),
            details={"field": field},
        )
    if name.startswith("-") or any(part in name for part in ("..", "/", "\\")):
        return ErrorResult(
            message="Remote name must not start with '-' or contain path separators",
            code=cast(Any, "VALIDATION_ERROR"),
            details={"field": field},
        )
    return None


def _validate_remote_url(url: str) -> Optional[ErrorResult]:
    """Reject empty URLs and URLs carrying inline credentials."""
    if not url.strip():
        return ErrorResult(
            message="Remote URL must not be empty",
            code=cast(Any, "VALIDATION_ERROR"),
            details={"field": "url"},
        )

    parsed = urlparse(url)
    if parsed.scheme in {"http", "https", "ssh", "git"} and parsed.netloc:
        if parsed.password is not None:
            return ErrorResult(
                message="Remote URL must not contain inline credentials",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "url"},
            )
        if parsed.scheme in {"http", "https"} and parsed.username is not None:
            return ErrorResult(
                message="HTTP remote URL must not contain inline user info",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "url"},
            )
    return None


def _list_remotes(root: Any) -> List[Dict[str, str]]:
    """Return the configured remotes from git remote --verbose."""
    returncode, stdout, _stderr, _timed_out = run_git_subprocess(
        ["git", "remote", "--verbose"],
        cwd=root,
        env=None,
        timeout_seconds=LOCAL_GIT_TIMEOUT_SECONDS,
    )
    if returncode != 0:
        return []

    seen: set[tuple[str, str, str]] = set()
    remotes: List[Dict[str, str]] = []
    for line in stdout.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name = parts[0]
        rest = parts[1].strip()
        if rest.endswith(")") and "(" in rest:
            url_part, _, kind_part = rest.rpartition("(")
            url = url_part.strip()
            kind = kind_part.rstrip(")").strip()
        else:
            url = rest
            kind = ""
        key = (name, url, kind)
        if key in seen:
            continue
        seen.add(key)
        remotes.append({"name": name, "url": url, "kind": kind})
    return remotes


class _BaseGitRemoteConfigCommand(BaseMCPCommand):
    """Base class for local remote configuration mutating commands."""

    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    version = "1.0.0"
    use_queue = True

    @classmethod
    def _schema_properties(cls) -> Dict[str, Any]:
        return {
            "project_id": {
                "type": "string",
                "description": (
                    "Project UUID. Use list_projects to discover valid project_id "
                    "values."
                ),
            },
            "name": {
                "type": "string",
                "description": (
                    "Remote name to add or update, for example origin or upstream. "
                    "Must not be empty, start with '-', or contain path separators."
                ),
            },
            "url": {
                "type": "string",
                "description": (
                    "Remote repository URL. Inline HTTP credentials are rejected; "
                    "use the server's configured authentication flow instead."
                ),
            },
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": (
                    "If true, return the git command that would run and the current "
                    "remote list without mutating .git/config."
                ),
            },
        }

    async def _execute_operation(
        self,
        project_id: str,
        remote_operation: RemoteConfigOperation,
        dry_run: bool,
    ) -> SuccessResult | ErrorResult:
        root = self._resolve_project_root(project_id)
        if not is_git_available():
            return git_remote_error_result(
                GIT_NOT_AVAILABLE, "git executable is not available", {}
            )
        if not is_git_repository(root):
            return git_remote_error_result(
                GIT_NOT_A_REPO,
                f"{root} is not a git repository",
                {"root": str(root)},
            )

        before = _list_remotes(root)
        if dry_run:
            return SuccessResult(
                data=cast(
                    Dict[str, Any],
                    {
                        "success": True,
                        "dry_run": True,
                        "operation": remote_operation.operation,
                        "remote": remote_operation.remote,
                        "url": remote_operation.url,
                        "old_name": remote_operation.old_name,
                        "new_name": remote_operation.new_name,
                        "would_run": ["git", *remote_operation.args],
                        "before": before,
                    },
                )
            )

        returncode, stdout, stderr, timed_out = run_git_subprocess(
            ["git", *remote_operation.args],
            cwd=root,
            env=None,
            timeout_seconds=LOCAL_GIT_TIMEOUT_SECONDS,
        )
        if timed_out:
            return git_remote_error_result(
                "GIT_REMOTE_CONFIG_TIMEOUT",
                f"git remote {remote_operation.operation} exceeded timeout of 30 seconds",
                {
                    "operation": remote_operation.operation,
                    "remote": remote_operation.remote,
                },
            )
        if returncode != 0:
            return git_remote_error_result(
                "GIT_REMOTE_CONFIG_FAILED",
                (
                    f"git remote {remote_operation.operation} failed with "
                    f"exit code {returncode}"
                ),
                {
                    "operation": remote_operation.operation,
                    "remote": remote_operation.remote,
                    "stderr": stderr.strip(),
                },
            )

        payload: Dict[str, Any] = {
            "success": True,
            "dry_run": False,
            "operation": remote_operation.operation,
            "remote": remote_operation.remote,
            "url": remote_operation.url,
            "old_name": remote_operation.old_name,
            "new_name": remote_operation.new_name,
            "before": before,
            "after": _list_remotes(root),
            "output": stdout.strip(),
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))


def _remote_config_metadata(
    cls: Type[Any],
    *,
    action: str,
    git_command: str,
    usage_examples: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build rich metadata for git remote configuration commands."""
    return build_command_metadata(
        cls,
        detailed_description=(
            f"{cls.name} performs local git remote configuration for one registered "
            f"project by running `{git_command}` in the resolved project repository. "
            "It changes the repository's .git/config only; it does not fetch, pull, "
            "push, contact the network, or use the remote SSH authentication guard. "
            "Use git_remote before and after the command when an agent needs an "
            "audit trail of the configured remotes. The command is queued because it "
            "mutates repository configuration, is project-scoped through project_id, "
            "and refuses remote names that could be interpreted as paths or options. "
            "The dry_run mode is the safe preview path: it reports the exact argv "
            "that would be executed and leaves the repository unchanged. URLs with "
            "inline HTTP credentials are rejected so credentials stay in the server "
            "configuration or SSH setup instead of command parameters."
        ),
        parameters=parameters_from_schema(cls.get_schema()),
        return_value=simple_success_return(
            description=f"{action} completed or was previewed successfully.",
            data_fields={
                "success": "True when the command succeeds.",
                "dry_run": "Whether the repository was left unchanged.",
                "operation": "Remote configuration operation name.",
                "remote": "Remote name affected by the operation.",
                "before": "Remote list before the operation.",
                "after": "Remote list after the operation when not dry_run.",
                "would_run": "Preview argv emitted only for dry_run=true.",
                "output": "Trimmed stdout from git.",
            },
            example={
                "success": True,
                "dry_run": False,
                "operation": action,
                "remote": "origin",
            },
        ),
        usage_examples=usage_examples,
        error_cases={
            "VALIDATION_ERROR": {
                "description": (
                    "Required parameter is empty or invalid, or the URL contains "
                    "inline credentials."
                ),
                "solution": "Fix the parameter according to get_schema() and retry.",
            },
            "GIT_NOT_AVAILABLE": {
                "description": "The git executable is not available to the server.",
                "solution": "Install git or fix the server PATH.",
            },
            "GIT_NOT_A_REPO": {
                "description": "The resolved project root is not a git repository.",
                "solution": "Use a registered project whose root contains a git repo.",
            },
            "GIT_REMOTE_CONFIG_FAILED": {
                "description": "git remote returned a non-zero exit code.",
                "solution": (
                    "Inspect stderr in details; common causes are duplicate remote "
                    "names or missing remotes."
                ),
            },
            "GIT_REMOTE_CONFIG_TIMEOUT": {
                "description": "The local git remote command exceeded the timeout.",
                "solution": "Retry after checking repository health.",
            },
        },
        best_practices=[
            "Call git_remote first when changing an existing repository configuration.",
            "Use dry_run=true before destructive remove or rename operations.",
            "Do not pass tokens or passwords in remote URLs.",
            "Use git_fetch, git_pull, or git_push only after remote configuration is correct.",
        ],
    )


class GitRemoteAddCommand(_BaseGitRemoteConfigCommand):
    """MCP command adding a configured git remote."""

    name = "git_remote_add"
    descr = "Add a configured remote to a project's git repository."

    @staticmethod
    def get_name() -> str:
        return "git_remote_add"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": cls._schema_properties(),
            "required": ["project_id", "name", "url"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["GitRemoteAddCommand"]) -> Dict[str, Any]:
        return _remote_config_metadata(
            cls,
            action="add",
            git_command="git remote add <name> <url>",
            usage_examples=[
                {
                    "description": "Add an SSH remote named origin.",
                    "command": {
                        "project_id": "<uuid>",
                        "name": "origin",
                        "url": "git@github.com:owner/repo.git",
                    },
                    "explanation": "Creates a local remote entry without contacting GitHub.",
                }
            ],
        )

    async def execute(
        self,
        project_id: str,
        name: str,
        url: str,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = kwargs
        validation_error = _validate_remote_name(name) or _validate_remote_url(url)
        if validation_error is not None:
            return validation_error
        return await self._execute_operation(
            project_id,
            RemoteConfigOperation("add", ["remote", "add", name, url], name, url),
            dry_run,
        )


class GitRemoteSetUrlCommand(_BaseGitRemoteConfigCommand):
    """MCP command changing a configured git remote URL."""

    name = "git_remote_set_url"
    descr = "Change a configured remote URL in a project's git repository."

    @staticmethod
    def get_name() -> str:
        return "git_remote_set_url"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": cls._schema_properties(),
            "required": ["project_id", "name", "url"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["GitRemoteSetUrlCommand"]) -> Dict[str, Any]:
        return _remote_config_metadata(
            cls,
            action="set-url",
            git_command="git remote set-url <name> <url>",
            usage_examples=[
                {
                    "description": "Replace the fetch URL for origin.",
                    "command": {
                        "project_id": "<uuid>",
                        "name": "origin",
                        "url": "git@github.com:owner/new-repo.git",
                    },
                    "explanation": "Updates the configured fetch URL for an existing remote.",
                }
            ],
        )

    async def execute(
        self,
        project_id: str,
        name: str,
        url: str,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = kwargs
        validation_error = _validate_remote_name(name) or _validate_remote_url(url)
        if validation_error is not None:
            return validation_error
        return await self._execute_operation(
            project_id,
            RemoteConfigOperation(
                "set-url", ["remote", "set-url", name, url], name, url
            ),
            dry_run,
        )


class GitRemoteSetPushUrlCommand(_BaseGitRemoteConfigCommand):
    """MCP command changing a configured git remote push URL."""

    name = "git_remote_set_push_url"
    descr = "Change a configured remote push URL in a project's git repository."

    @staticmethod
    def get_name() -> str:
        return "git_remote_set_push_url"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": cls._schema_properties(),
            "required": ["project_id", "name", "url"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["GitRemoteSetPushUrlCommand"]) -> Dict[str, Any]:
        return _remote_config_metadata(
            cls,
            action="set-push-url",
            git_command="git remote set-url --push <name> <url>",
            usage_examples=[
                {
                    "description": "Set a dedicated push URL for origin.",
                    "command": {
                        "project_id": "<uuid>",
                        "name": "origin",
                        "url": "git@github.com:owner/write-repo.git",
                    },
                    "explanation": "Leaves the fetch URL unchanged and updates pushurl.",
                }
            ],
        )

    async def execute(
        self,
        project_id: str,
        name: str,
        url: str,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = kwargs
        validation_error = _validate_remote_name(name) or _validate_remote_url(url)
        if validation_error is not None:
            return validation_error
        return await self._execute_operation(
            project_id,
            RemoteConfigOperation(
                "set-push-url",
                ["remote", "set-url", "--push", name, url],
                name,
                url,
            ),
            dry_run,
        )


class GitRemoteRemoveCommand(_BaseGitRemoteConfigCommand):
    """MCP command removing a configured git remote."""

    name = "git_remote_remove"
    descr = "Remove a configured remote from a project's git repository."

    @staticmethod
    def get_name() -> str:
        return "git_remote_remove"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": cls._schema_properties()["project_id"],
                "name": cls._schema_properties()["name"],
                "dry_run": cls._schema_properties()["dry_run"],
            },
            "required": ["project_id", "name"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["GitRemoteRemoveCommand"]) -> Dict[str, Any]:
        return _remote_config_metadata(
            cls,
            action="remove",
            git_command="git remote remove <name>",
            usage_examples=[
                {
                    "description": "Preview removal of origin.",
                    "command": {
                        "project_id": "<uuid>",
                        "name": "origin",
                        "dry_run": True,
                    },
                    "explanation": "Shows the argv and current remotes without editing .git/config.",
                }
            ],
        )

    async def execute(
        self,
        project_id: str,
        name: str,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = kwargs
        validation_error = _validate_remote_name(name)
        if validation_error is not None:
            return validation_error
        return await self._execute_operation(
            project_id,
            RemoteConfigOperation("remove", ["remote", "remove", name], name),
            dry_run,
        )


class GitRemoteRenameCommand(_BaseGitRemoteConfigCommand):
    """MCP command renaming a configured git remote."""

    name = "git_remote_rename"
    descr = "Rename a configured remote in a project's git repository."

    @staticmethod
    def get_name() -> str:
        return "git_remote_rename"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": cls._schema_properties()["project_id"],
                "old_name": {
                    "type": "string",
                    "description": (
                        "Existing remote name to rename. Must not be empty, start "
                        "with '-', or contain path separators."
                    ),
                },
                "new_name": {
                    "type": "string",
                    "description": (
                        "New remote name. Must not be empty, start with '-', or "
                        "contain path separators."
                    ),
                },
                "dry_run": cls._schema_properties()["dry_run"],
            },
            "required": ["project_id", "old_name", "new_name"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["GitRemoteRenameCommand"]) -> Dict[str, Any]:
        return _remote_config_metadata(
            cls,
            action="rename",
            git_command="git remote rename <old_name> <new_name>",
            usage_examples=[
                {
                    "description": "Rename origin to upstream.",
                    "command": {
                        "project_id": "<uuid>",
                        "old_name": "origin",
                        "new_name": "upstream",
                    },
                    "explanation": "Renames the local remote configuration entry.",
                }
            ],
        )

    async def execute(
        self,
        project_id: str,
        old_name: str,
        new_name: str,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = kwargs
        validation_error = _validate_remote_name(
            old_name, "old_name"
        ) or _validate_remote_name(new_name, "new_name")
        if validation_error is not None:
            return validation_error
        return await self._execute_operation(
            project_id,
            RemoteConfigOperation(
                "rename",
                ["remote", "rename", old_name, new_name],
                new_name,
                old_name=old_name,
                new_name=new_name,
            ),
            dry_run,
        )
