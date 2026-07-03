"""
MCP commands: github_pr_create, github_issue_create, github_issue_comment,
github_release_create

Write GitHub API operations for the GitHub command block (C-018 GithubBlock)
that are not the pull-request merge operation. Each command authenticates via
resolve_github_auth() from code_analysis.core.github_auth and issues one
request through github_api_request() from code_analysis.commands.github_http.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.core.github_auth import (
    classify_github_auth_error,
    resolve_github_auth,
)

from .base_mcp_command import BaseMCPCommand
from .github_http import github_api_request, github_timeout_seconds_from_config


class GithubPrCreateCommand(BaseMCPCommand):
    """Create a pull request in a repository."""

    name = "github_pr_create"
    version = "1.0.0"
    descr = "Create a pull request in owner/repo via the GitHub REST API."
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
                "title": {"type": "string", "description": "Pull request title."},
                "head": {
                    "type": "string",
                    "description": "Branch containing the changes (source branch).",
                },
                "base": {
                    "type": "string",
                    "description": (
                        "Branch the pull request targets (destination branch)."
                    ),
                },
                "body": {
                    "type": "string",
                    "description": "Pull request description body.",
                },
            },
            "required": ["owner", "repo", "title", "head", "base"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Create a pull request from head into base."""
        config_data = BaseMCPCommand._get_raw_config()
        headers, auth_error = resolve_github_auth(config_data)
        if auth_error is not None:
            return ErrorResult(
                message="GitHub authentication is not configured",
                code=auth_error,
                details={"owner": owner, "repo": repo},
            )
        assert headers is not None
        request_body: Dict[str, Any] = {"title": title, "head": head, "base": base}
        if body is not None:
            request_body["body"] = body
        data, status, error_code = github_api_request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            headers,
            json_body=request_body,
            timeout_seconds=github_timeout_seconds_from_config(config_data),
        )
        if error_code is not None:
            classified = (
                classify_github_auth_error(status) if status is not None else None
            )
            return ErrorResult(
                message=f"GitHub pr_create failed for {owner}/{repo}",
                code=classified or error_code,
                details={"owner": owner, "repo": repo, "status": status},
            )
        return SuccessResult(data={"pull_request": data})


class GithubIssueCreateCommand(BaseMCPCommand):
    """Create an issue in a repository."""

    name = "github_issue_create"
    version = "1.0.0"
    descr = "Create an issue in owner/repo via the GitHub REST API."
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
                "title": {"type": "string", "description": "Issue title."},
                "body": {"type": "string", "description": "Issue description body."},
            },
            "required": ["owner", "repo", "title"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        owner: str,
        repo: str,
        title: str,
        body: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Create an issue with title and optional body."""
        config_data = BaseMCPCommand._get_raw_config()
        headers, auth_error = resolve_github_auth(config_data)
        if auth_error is not None:
            return ErrorResult(
                message="GitHub authentication is not configured",
                code=auth_error,
                details={"owner": owner, "repo": repo},
            )
        assert headers is not None
        request_body: Dict[str, Any] = {"title": title}
        if body is not None:
            request_body["body"] = body
        data, status, error_code = github_api_request(
            "POST",
            f"/repos/{owner}/{repo}/issues",
            headers,
            json_body=request_body,
            timeout_seconds=github_timeout_seconds_from_config(config_data),
        )
        if error_code is not None:
            classified = (
                classify_github_auth_error(status) if status is not None else None
            )
            return ErrorResult(
                message=f"GitHub issue_create failed for {owner}/{repo}",
                code=classified or error_code,
                details={"owner": owner, "repo": repo, "status": status},
            )
        return SuccessResult(data={"issue": data})


class GithubIssueCommentCommand(BaseMCPCommand):
    """Add a comment to an issue or pull request."""

    name = "github_issue_comment"
    version = "1.0.0"
    descr = (
        "Add a comment to an issue (or pull request, which shares the issue "
        "number) via the GitHub REST API."
    )
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
                "issue_number": {
                    "type": "integer",
                    "description": "Issue or pull request number.",
                },
                "body": {"type": "string", "description": "Comment text body."},
            },
            "required": ["owner", "repo", "issue_number", "body"],
            "additionalProperties": False,
        }

    async def execute(
        self, owner: str, repo: str, issue_number: int, body: str, **kwargs: Any
    ) -> SuccessResult | ErrorResult:
        """Add a comment to issue_number."""
        config_data = BaseMCPCommand._get_raw_config()
        headers, auth_error = resolve_github_auth(config_data)
        if auth_error is not None:
            return ErrorResult(
                message="GitHub authentication is not configured",
                code=auth_error,
                details={"owner": owner, "repo": repo, "issue_number": issue_number},
            )
        assert headers is not None
        data, status, error_code = github_api_request(
            "POST",
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            headers,
            json_body={"body": body},
            timeout_seconds=github_timeout_seconds_from_config(config_data),
        )
        if error_code is not None:
            classified = (
                classify_github_auth_error(status) if status is not None else None
            )
            return ErrorResult(
                message=(
                    f"GitHub issue_comment failed for " f"{owner}/{repo}#{issue_number}"
                ),
                code=classified or error_code,
                details={
                    "owner": owner,
                    "repo": repo,
                    "issue_number": issue_number,
                    "status": status,
                },
            )
        return SuccessResult(data={"comment": data})


class GithubReleaseCreateCommand(BaseMCPCommand):
    """Create a release in a repository."""

    name = "github_release_create"
    version = "1.0.0"
    descr = "Create a release in owner/repo via the GitHub REST API."
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
                "tag_name": {
                    "type": "string",
                    "description": "Git tag the release is created from or creates.",
                },
                "name": {"type": "string", "description": "Release title."},
                "body": {"type": "string", "description": "Release notes body."},
                "draft": {
                    "type": "boolean",
                    "default": False,
                    "description": "Create as an unpublished draft release.",
                },
                "prerelease": {
                    "type": "boolean",
                    "default": False,
                    "description": "Mark the release as a prerelease.",
                },
            },
            "required": ["owner", "repo", "tag_name"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        owner: str,
        repo: str,
        tag_name: str,
        name: Optional[str] = None,
        body: Optional[str] = None,
        draft: bool = False,
        prerelease: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Create a release from tag_name."""
        config_data = BaseMCPCommand._get_raw_config()
        headers, auth_error = resolve_github_auth(config_data)
        if auth_error is not None:
            return ErrorResult(
                message="GitHub authentication is not configured",
                code=auth_error,
                details={"owner": owner, "repo": repo},
            )
        assert headers is not None
        request_body: Dict[str, Any] = {
            "tag_name": tag_name,
            "draft": bool(draft),
            "prerelease": bool(prerelease),
        }
        if name is not None:
            request_body["name"] = name
        if body is not None:
            request_body["body"] = body
        data, status, error_code = github_api_request(
            "POST",
            f"/repos/{owner}/{repo}/releases",
            headers,
            json_body=request_body,
            timeout_seconds=github_timeout_seconds_from_config(config_data),
        )
        if error_code is not None:
            classified = (
                classify_github_auth_error(status) if status is not None else None
            )
            return ErrorResult(
                message=f"GitHub release_create failed for {owner}/{repo}",
                code=classified or error_code,
                details={"owner": owner, "repo": repo, "status": status},
            )
        return SuccessResult(data={"release": data})
