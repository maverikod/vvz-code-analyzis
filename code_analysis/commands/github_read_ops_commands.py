"""
MCP commands: github_repo_get, github_repo_list, github_pr_list, github_pr_get,
github_issue_list

Read-only GitHub API operations for the GitHub command block (C-018
GithubBlock). Each command authenticates via resolve_github_auth() from
code_analysis.core.github_auth and issues one request through
github_api_request() from code_analysis.commands.github_http. None of these
commands mutate remote state.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.core.github_auth import (
    classify_github_auth_error,
    resolve_github_auth,
)

from .base_mcp_command import BaseMCPCommand
from .github_http import github_api_request, github_timeout_seconds_from_config


class GithubRepoGetCommand(BaseMCPCommand):
    """Return repository metadata for one owner/repo from the GitHub API."""

    name = "github_repo_get"
    version = "1.0.0"
    descr = "Return repository metadata for owner/repo via the GitHub REST API."
    category = "github"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the command input schema."""
        return {
            "type": "object",
            "properties": {
                "owner": {
                    "type": "string",
                    "description": "Repository owner login (user or organization).",
                },
                "repo": {"type": "string", "description": "Repository name."},
            },
            "required": ["owner", "repo"],
            "additionalProperties": False,
        }

    async def execute(
        self, owner: str, repo: str, **kwargs: Any
    ) -> SuccessResult | ErrorResult:
        """Fetch repository metadata for owner/repo."""
        config_data = BaseMCPCommand._get_raw_config()
        headers, auth_error = resolve_github_auth(config_data)
        if auth_error is not None:
            return ErrorResult(
                message="GitHub authentication is not configured",
                code=auth_error,
                details={"owner": owner, "repo": repo},
            )
        assert headers is not None
        data, status, error_code = github_api_request(
            "GET",
            f"/repos/{owner}/{repo}",
            headers,
            timeout_seconds=github_timeout_seconds_from_config(config_data),
        )
        if error_code is not None:
            classified = (
                classify_github_auth_error(status) if status is not None else None
            )
            return ErrorResult(
                message=f"GitHub repo_get failed for {owner}/{repo}",
                code=classified or error_code,
                details={"owner": owner, "repo": repo, "status": status},
            )
        return SuccessResult(data={"repository": data})


class GithubRepoListCommand(BaseMCPCommand):
    """List public repositories owned by a user or organization."""

    name = "github_repo_list"
    version = "1.0.0"
    descr = "List public repositories owned by owner via the GitHub REST API."
    category = "github"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the command input schema."""
        return {
            "type": "object",
            "properties": {
                "owner": {
                    "type": "string",
                    "description": (
                        "User or organization login whose repositories are listed."
                    ),
                },
                "per_page": {
                    "type": "integer",
                    "default": 30,
                    "description": (
                        "Maximum number of repositories to return "
                        "(GitHub API per_page)."
                    ),
                },
            },
            "required": ["owner"],
            "additionalProperties": False,
        }

    async def execute(
        self, owner: str, per_page: int = 30, **kwargs: Any
    ) -> SuccessResult | ErrorResult:
        """List public repositories owned by owner."""
        config_data = BaseMCPCommand._get_raw_config()
        headers, auth_error = resolve_github_auth(config_data)
        if auth_error is not None:
            return ErrorResult(
                message="GitHub authentication is not configured",
                code=auth_error,
                details={"owner": owner},
            )
        assert headers is not None
        data, status, error_code = github_api_request(
            "GET",
            f"/users/{owner}/repos",
            headers,
            query={"per_page": str(per_page)},
            timeout_seconds=github_timeout_seconds_from_config(config_data),
        )
        if error_code is not None:
            classified = (
                classify_github_auth_error(status) if status is not None else None
            )
            return ErrorResult(
                message=f"GitHub repo_list failed for {owner}",
                code=classified or error_code,
                details={"owner": owner, "status": status},
            )
        return SuccessResult(data={"repositories": data})


class GithubPrListCommand(BaseMCPCommand):
    """List pull requests for a repository."""

    name = "github_pr_list"
    version = "1.0.0"
    descr = "List pull requests for owner/repo via the GitHub REST API."
    category = "github"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the command input schema."""
        return {
            "type": "object",
            "properties": {
                "owner": {
                    "type": "string",
                    "description": "Repository owner login.",
                },
                "repo": {"type": "string", "description": "Repository name."},
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "default": "open",
                    "description": "Pull request state filter.",
                },
            },
            "required": ["owner", "repo"],
            "additionalProperties": False,
        }

    async def execute(
        self, owner: str, repo: str, state: str = "open", **kwargs: Any
    ) -> SuccessResult | ErrorResult:
        """List pull requests for owner/repo filtered by state."""
        config_data = BaseMCPCommand._get_raw_config()
        headers, auth_error = resolve_github_auth(config_data)
        if auth_error is not None:
            return ErrorResult(
                message="GitHub authentication is not configured",
                code=auth_error,
                details={"owner": owner, "repo": repo},
            )
        assert headers is not None
        data, status, error_code = github_api_request(
            "GET",
            f"/repos/{owner}/{repo}/pulls",
            headers,
            query={"state": state},
            timeout_seconds=github_timeout_seconds_from_config(config_data),
        )
        if error_code is not None:
            classified = (
                classify_github_auth_error(status) if status is not None else None
            )
            return ErrorResult(
                message=f"GitHub pr_list failed for {owner}/{repo}",
                code=classified or error_code,
                details={"owner": owner, "repo": repo, "status": status},
            )
        return SuccessResult(data={"pull_requests": data})


class GithubPrGetCommand(BaseMCPCommand):
    """Return one pull request's details."""

    name = "github_pr_get"
    version = "1.0.0"
    descr = "Return one pull request's details via the GitHub REST API."
    category = "github"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the command input schema."""
        return {
            "type": "object",
            "properties": {
                "owner": {
                    "type": "string",
                    "description": "Repository owner login.",
                },
                "repo": {"type": "string", "description": "Repository name."},
                "pr_number": {
                    "type": "integer",
                    "description": "Pull request number.",
                },
            },
            "required": ["owner", "repo", "pr_number"],
            "additionalProperties": False,
        }

    async def execute(
        self, owner: str, repo: str, pr_number: int, **kwargs: Any
    ) -> SuccessResult | ErrorResult:
        """Fetch one pull request's details."""
        config_data = BaseMCPCommand._get_raw_config()
        headers, auth_error = resolve_github_auth(config_data)
        if auth_error is not None:
            return ErrorResult(
                message="GitHub authentication is not configured",
                code=auth_error,
                details={"owner": owner, "repo": repo, "pr_number": pr_number},
            )
        assert headers is not None
        data, status, error_code = github_api_request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
            headers,
            timeout_seconds=github_timeout_seconds_from_config(config_data),
        )
        if error_code is not None:
            classified = (
                classify_github_auth_error(status) if status is not None else None
            )
            return ErrorResult(
                message=f"GitHub pr_get failed for {owner}/{repo}#{pr_number}",
                code=classified or error_code,
                details={
                    "owner": owner,
                    "repo": repo,
                    "pr_number": pr_number,
                    "status": status,
                },
            )
        return SuccessResult(data={"pull_request": data})


class GithubIssueListCommand(BaseMCPCommand):
    """List issues for a repository."""

    name = "github_issue_list"
    version = "1.0.0"
    descr = "List issues for owner/repo via the GitHub REST API."
    category = "github"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the command input schema."""
        return {
            "type": "object",
            "properties": {
                "owner": {
                    "type": "string",
                    "description": "Repository owner login.",
                },
                "repo": {"type": "string", "description": "Repository name."},
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "default": "open",
                    "description": "Issue state filter.",
                },
            },
            "required": ["owner", "repo"],
            "additionalProperties": False,
        }

    async def execute(
        self, owner: str, repo: str, state: str = "open", **kwargs: Any
    ) -> SuccessResult | ErrorResult:
        """List issues for owner/repo filtered by state."""
        config_data = BaseMCPCommand._get_raw_config()
        headers, auth_error = resolve_github_auth(config_data)
        if auth_error is not None:
            return ErrorResult(
                message="GitHub authentication is not configured",
                code=auth_error,
                details={"owner": owner, "repo": repo},
            )
        assert headers is not None
        data, status, error_code = github_api_request(
            "GET",
            f"/repos/{owner}/{repo}/issues",
            headers,
            query={"state": state},
            timeout_seconds=github_timeout_seconds_from_config(config_data),
        )
        if error_code is not None:
            classified = (
                classify_github_auth_error(status) if status is not None else None
            )
            return ErrorResult(
                message=f"GitHub issue_list failed for {owner}/{repo}",
                code=classified or error_code,
                details={"owner": owner, "repo": repo, "status": status},
            )
        return SuccessResult(data={"issues": data})
