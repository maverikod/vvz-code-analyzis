"""
MCP command: github_pr_merge

Merge a GitHub pull request, gated by the pull-request merge guard (C-019
GithubPrMergeGuard). Authenticates via resolve_github_auth() from
code_analysis.core.github_auth and issues one request through
github_api_request() from code_analysis.commands.github_http.

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


def evaluate_github_pr_merge_guard(
    *,
    allow_pr_merge: bool,
    is_protected_base: bool,
    protected_base_override: bool,
    allow_protected_base_merge: bool,
) -> Optional[str]:
    """
    Decide whether a pull-request merge is permitted before any API call.

    Implements C-019 GithubPrMergeGuard: merging bypasses the local
    protected-branch restriction and is independently gated. A merge
    proceeds only when merging is permitted by configuration; a merge
    whose pull request targets a protected base branch additionally
    requires an explicit override supplied by the caller together with
    the policy config flag permitting a protected-base merge.

    Args:
        allow_pr_merge: The code_analysis.github.allow_pr_merge config flag.
            When false, merging is refused regardless of other flags.
        is_protected_base: Whether the pull request's base branch is a
            member of the code_analysis.git.protected_branches set.
        protected_base_override: The caller-supplied explicit override
            for a protected-base merge.
        allow_protected_base_merge: The code_analysis.github.allow_protected_base_merge
            config flag permitting a protected-base merge when the caller
            also supplies protected_base_override.

    Returns:
        None when the merge is permitted to proceed. Otherwise one of:
        "GITHUB_PR_MERGE_DISABLED" when allow_pr_merge is false.
        "GITHUB_PROTECTED_BRANCH" when the base is protected and the
        override plus policy condition is not fully satisfied.
    """
    if not allow_pr_merge:
        return "GITHUB_PR_MERGE_DISABLED"
    if is_protected_base and not (
        protected_base_override and allow_protected_base_merge
    ):
        return "GITHUB_PROTECTED_BRANCH"
    return None


class GithubPrMergeCommand(BaseMCPCommand):
    """Merge a GitHub pull request, gated by the pull-request merge guard."""

    name = "github_pr_merge"
    version = "1.0.0"
    descr = (
        "Merge a pull request via the GitHub API. Requires the "
        "code_analysis.github.allow_pr_merge config permission; a pull request "
        "targeting a protected base branch additionally requires "
        "protected_base_override together with the "
        "code_analysis.github.allow_protected_base_merge config flag."
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
                "pr_number": {
                    "type": "integer",
                    "description": "Pull request number.",
                },
                "base_branch": {
                    "type": "string",
                    "description": (
                        "Base branch the pull request targets, checked against "
                        "code_analysis.git.protected_branches."
                    ),
                },
                "protected_base_override": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Explicit override required when base_branch is protected."
                    ),
                },
            },
            "required": ["owner", "repo", "pr_number", "base_branch"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        base_branch: str,
        protected_base_override: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Merge a pull request after evaluating the merge guard."""
        config_data = BaseMCPCommand._get_raw_config()
        github_cfg: Dict[str, Any] = {}
        git_cfg: Dict[str, Any] = {}
        if isinstance(config_data, dict):
            code_analysis_cfg = config_data.get("code_analysis", {})
            if isinstance(code_analysis_cfg, dict):
                github_section = code_analysis_cfg.get("github", {})
                git_section = code_analysis_cfg.get("git", {})
                if isinstance(github_section, dict):
                    github_cfg = github_section
                if isinstance(git_section, dict):
                    git_cfg = git_section
        allow_pr_merge = bool(github_cfg.get("allow_pr_merge", False))
        allow_protected_base_merge = bool(
            github_cfg.get("allow_protected_base_merge", False)
        )
        protected_branches = git_cfg.get("protected_branches", [])
        is_protected_base = (
            isinstance(protected_branches, list) and base_branch in protected_branches
        )

        guard_code = evaluate_github_pr_merge_guard(
            allow_pr_merge=allow_pr_merge,
            is_protected_base=is_protected_base,
            protected_base_override=bool(protected_base_override),
            allow_protected_base_merge=allow_protected_base_merge,
        )
        if guard_code is not None:
            return ErrorResult(
                message=f"GitHub pull request merge refused: {guard_code}",
                code=guard_code,
                details={
                    "owner": owner,
                    "repo": repo,
                    "pr_number": pr_number,
                    "base_branch": base_branch,
                },
            )

        headers, auth_error = resolve_github_auth(config_data)
        if auth_error is not None:
            return ErrorResult(
                message="GitHub authentication is not configured",
                code=auth_error,
                details={"owner": owner, "repo": repo, "pr_number": pr_number},
            )
        assert headers is not None
        timeout_seconds = github_timeout_seconds_from_config(config_data)
        data, status, error_code = github_api_request(
            "PUT",
            f"/repos/{owner}/{repo}/pulls/{pr_number}/merge",
            headers,
            timeout_seconds=timeout_seconds,
        )
        if error_code is not None:
            classified = (
                classify_github_auth_error(status) if status is not None else None
            )
            return ErrorResult(
                message=(
                    f"GitHub pull request merge failed for "
                    f"{owner}/{repo}#{pr_number}"
                ),
                code=classified or error_code,
                details={
                    "owner": owner,
                    "repo": repo,
                    "pr_number": pr_number,
                    "status": status,
                },
            )
        return SuccessResult(data={"merge_result": data})
