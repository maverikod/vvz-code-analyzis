"""
GitHub read-only command group for the live-server all-commands verifier.

Targets the public ``octocat/hello-world`` repository — no auth/rate-limit
guarantee is assumed; whatever the live server returns (success, rate-limit
error, or no-token error) is recorded as a genuine outcome with the real
server error text, never a "no fixture" skip.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Dict

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import CommandOutcome
from _verify_client_all_commands_fixtures import FixtureContext
from _verify_client_all_commands_lifecycle_common import call_step

_OWNER = "octocat"
_REPO = "hello-world"


async def run_github_lifecycle(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Call every ``github_*`` read command with real public-repo fixtures.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run (unused
            here; every ``github_*`` read is project-independent).

    Returns:
        Mapping of every command name this lifecycle covers to its outcome.
    """
    _ = fixtures
    outcomes: Dict[str, CommandOutcome] = {}
    outcomes["github_repo_get"] = await call_step(
        client, "github_repo_get", {"owner": _OWNER, "repo": _REPO}
    )
    outcomes["github_repo_list"] = await call_step(
        client, "github_repo_list", {"owner": _OWNER}
    )
    outcomes["github_pr_list"] = await call_step(
        client, "github_pr_list", {"owner": _OWNER, "repo": _REPO}
    )
    outcomes["github_pr_get"] = await call_step(
        client, "github_pr_get", {"owner": _OWNER, "repo": _REPO, "pr_number": 1}
    )
    outcomes["github_issue_list"] = await call_step(
        client, "github_issue_list", {"owner": _OWNER, "repo": _REPO}
    )
    return outcomes
