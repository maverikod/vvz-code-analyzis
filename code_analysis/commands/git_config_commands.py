"""Git config and identity MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.git_config_metadata import (
    get_git_config_get_metadata,
    get_git_config_list_metadata,
    get_git_identity_get_metadata,
    get_git_identity_set_metadata,
)
from code_analysis.commands.git_worktree_base import (
    GitWorktreeCommand,
    validation_error,
)

_READ_SCOPES = {"local", "global", "system", "effective"}
_WRITE_SCOPES = {"local", "global"}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")


def _scope_args(scope: str) -> List[str]:
    """Return git config CLI args for a logical scope."""
    if scope == "effective":
        return []
    return [f"--{scope}"]


def _normalize_scope(scope: str, allowed: set[str]) -> Optional[str]:
    """Normalize and validate a scope value."""
    normalized = (scope or "local").strip().lower()
    return normalized if normalized in allowed else None


class _GitConfigCommand(GitWorktreeCommand):
    """Shared helpers for git config commands."""

    def _config_get(
        self,
        project_id: str,
        key: str,
        scope: str,
    ) -> tuple[Optional[str], Optional[ErrorResult]]:
        """Read one git config key; missing keys return (None, None)."""
        result, error = self._run_local_git(
            project_id,
            ["config", *_scope_args(scope), "--get", key],
            error_code="GIT_CONFIG_GET_FAILED",
            action="git config get",
            details={"key": key, "scope": scope},
        )
        if error is None:
            stdout, _stderr = result or ("", "")
            return stdout.rstrip("\n"), None
        details = getattr(error, "details", None) or {}
        if isinstance(details, dict) and details.get("stderr", "") == "":
            return None, None
        return None, error

    def _config_set(
        self,
        project_id: str,
        key: str,
        value: str,
        scope: str,
    ) -> Optional[ErrorResult]:
        """Set one git config key."""
        _result, error = self._run_local_git(
            project_id,
            ["config", *_scope_args(scope), key, value],
            error_code="GIT_CONFIG_SET_FAILED",
            action="git config set",
            details={"key": key, "scope": scope},
        )
        return error

    def _identity_payload(
        self, project_id: str
    ) -> tuple[Dict[str, Any], Optional[ErrorResult]]:
        """Return local and effective identity payload."""
        local_name, error = self._config_get(project_id, "user.name", "local")
        if error is not None:
            return {}, error
        local_email, error = self._config_get(project_id, "user.email", "local")
        if error is not None:
            return {}, error
        effective_name, error = self._config_get(project_id, "user.name", "effective")
        if error is not None:
            return {}, error
        effective_email, error = self._config_get(project_id, "user.email", "effective")
        if error is not None:
            return {}, error
        payload: Dict[str, Any] = {
            "success": True,
            "configured": bool(effective_name and effective_email),
            "local": {
                "name": local_name,
                "email": local_email,
                "configured": bool(local_name and local_email),
            },
            "effective": {
                "name": effective_name,
                "email": effective_email,
                "configured": bool(effective_name and effective_email),
            },
        }
        return payload, None


class GitConfigGetCommand(_GitConfigCommand):
    """Read one git config value."""

    name = "git_config_get"
    version = "1.0.0"
    descr = "Read one git config value for a project's repository."
    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_config_get"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID. Use list_projects to discover valid project_id values.",
                },
                "key": {
                    "type": "string",
                    "description": "Git config key to read, for example user.name or user.email.",
                },
                "scope": {
                    "type": "string",
                    "enum": sorted(_READ_SCOPES),
                    "default": "local",
                    "description": "Config scope to read: local, global, system, or effective.",
                },
            },
            "required": ["project_id", "key"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_config_get."""
        return get_git_config_get_metadata(cls)

    async def execute(
        self,
        project_id: str,
        key: str,
        scope: str = "local",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_config_get command."""
        _ = kwargs
        normalized_scope = _normalize_scope(scope, _READ_SCOPES)
        if normalized_scope is None:
            return validation_error(
                "scope must be local, global, system, or effective", "scope"
            )
        if not key.strip():
            return validation_error("key must not be empty", "key")
        value, error = self._config_get(project_id, key.strip(), normalized_scope)
        if error is not None:
            return error
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                {
                    "success": True,
                    "key": key.strip(),
                    "scope": normalized_scope,
                    "configured": value is not None,
                    "value": value,
                },
            )
        )


class GitConfigListCommand(_GitConfigCommand):
    """List git config values."""

    name = "git_config_list"
    version = "1.0.0"
    descr = "List git config values visible to a project's repository."
    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_config_list"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID. Use list_projects to discover valid project_id values.",
                },
                "scope": {
                    "type": "string",
                    "enum": sorted(_READ_SCOPES),
                    "default": "effective",
                    "description": "Config scope to list: local, global, system, or effective.",
                },
                "include_origin": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include git's origin path/scope for each entry.",
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_config_list."""
        return get_git_config_list_metadata(cls)

    async def execute(
        self,
        project_id: str,
        scope: str = "effective",
        include_origin: bool = True,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_config_list command."""
        _ = kwargs
        normalized_scope = _normalize_scope(scope, _READ_SCOPES)
        if normalized_scope is None:
            return validation_error(
                "scope must be local, global, system, or effective", "scope"
            )
        args = ["config", *_scope_args(normalized_scope), "--list"]
        if include_origin:
            args.insert(1, "--show-origin")
        result, error = self._run_local_git(
            project_id,
            args,
            error_code="GIT_CONFIG_LIST_FAILED",
            action="git config list",
            details={"scope": normalized_scope, "include_origin": include_origin},
        )
        if error is not None:
            return error
        stdout, _stderr = result or ("", "")
        entries: List[Dict[str, str]] = []
        for line in stdout.splitlines():
            origin = None
            rest = line
            if include_origin:
                origin, _sep, rest = line.partition("\t")
            key, sep, value = rest.partition("=")
            if sep:
                entry = {"key": key, "value": value}
                if origin is not None:
                    entry["origin"] = origin
                entries.append(entry)
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                {
                    "success": True,
                    "scope": normalized_scope,
                    "include_origin": include_origin,
                    "entries": entries,
                    "count": len(entries),
                },
            )
        )


class GitIdentityGetCommand(_GitConfigCommand):
    """Read git user.name and user.email."""

    name = "git_identity_get"
    version = "1.0.0"
    descr = "Read git commit identity for a project's repository."
    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_identity_get"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID. Use list_projects to discover valid project_id values.",
                }
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_identity_get."""
        return get_git_identity_get_metadata(cls)

    async def execute(
        self,
        project_id: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_identity_get command."""
        _ = kwargs
        payload, error = self._identity_payload(project_id)
        if error is not None:
            return error
        return SuccessResult(data=cast(Dict[str, Any], payload))


class GitIdentitySetCommand(_GitConfigCommand):
    """Set git user.name and user.email."""

    name = "git_identity_set"
    version = "1.0.0"
    descr = "Set git commit identity for a project's repository."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_identity_set"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID. Use list_projects to discover valid project_id values.",
                },
                "name": {
                    "type": "string",
                    "description": "Git author/committer display name to store.",
                },
                "email": {
                    "type": "string",
                    "description": "Git author/committer email to store.",
                },
                "scope": {
                    "type": "string",
                    "enum": sorted(_WRITE_SCOPES),
                    "default": "local",
                    "description": "Write scope. local writes .git/config; global requires allow_global=true.",
                },
                "allow_global": {
                    "type": "boolean",
                    "default": False,
                    "description": "Must be true to permit scope=global.",
                },
            },
            "required": ["project_id", "name", "email"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_identity_set."""
        return get_git_identity_set_metadata(cls)

    async def execute(
        self,
        project_id: str,
        name: str,
        email: str,
        scope: str = "local",
        allow_global: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_identity_set command."""
        _ = kwargs
        normalized_scope = _normalize_scope(scope, _WRITE_SCOPES)
        if normalized_scope is None:
            return validation_error("scope must be local or global", "scope")
        if normalized_scope == "global" and not allow_global:
            return validation_error(
                "scope=global requires allow_global=true", "allow_global"
            )
        if not name.strip():
            return validation_error("name must not be empty", "name")
        if not _EMAIL_RE.match(email.strip()):
            return validation_error(
                "email must contain one @ and no whitespace", "email"
            )
        previous, error = self._identity_payload(project_id)
        if error is not None:
            return error
        error = self._config_set(
            project_id, "user.name", name.strip(), normalized_scope
        )
        if error is not None:
            return error
        error = self._config_set(
            project_id, "user.email", email.strip(), normalized_scope
        )
        if error is not None:
            return error
        current, error = self._identity_payload(project_id)
        if error is not None:
            return error
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                {
                    "success": True,
                    "scope": normalized_scope,
                    "allow_global": allow_global,
                    "previous": previous,
                    "current": current,
                },
            )
        )
