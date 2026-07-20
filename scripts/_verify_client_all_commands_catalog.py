"""
Static classification catalog for the live-server all-commands verifier.

Holds the enums/dataclass used to record a per-command verification outcome,
the fixed safety lists (Bucket B, outage-risk commands, standard adapter
commands), and a small generic parameter-value provider table used by the
sweep engine (``_verify_client_all_commands_sweep.py``) to synthesize
required-parameter values for commands it has never seen before.

This module intentionally holds **only** static data and pure helper
functions (schema inspection, string classification, value synthesis) — no
network calls and no fixture lifecycle. See
``_verify_client_all_commands_fixtures.py`` for the disposable project/git
fixture that supplies the values referenced here, and
``_verify_client_all_commands_sweep.py`` for the engine that ties both
together against a live server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, FrozenSet

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a runtime import cycle
    from _verify_client_all_commands_fixtures import FixtureContext


class Bucket(str, Enum):
    """Classification of *why* a command was (or was not) invoked.

    Attributes:
        BUCKET_A: Project-scoped command, executed against the disposable project.
        BUCKET_B: Fixed verify-only safety list, never invoked.
        ADAPTER: Standard ``mcp_proxy_adapter`` infra command.
        REMOVED: Listed in one of the client's ``*_REMOVED_COMMANDS`` sets.
    """

    BUCKET_A = "bucket_a"
    BUCKET_B = "bucket_b"
    ADAPTER = "adapter"
    REMOVED = "removed"


class Status(str, Enum):
    """Outcome of attempting to classify/execute a single command.

    Attributes:
        EXECUTED_OK: The command was called and returned ``success: true``.
        EXPECTED_ERROR: A well-formed rejection (bad input, not-found, etc.)
            or a deliberate decision not to call the command.
        VERIFY_ONLY: Classified without ever invoking the command (safety list,
            adapter-infra, removed-command cross-check, or a failed safety gate).
        FAILED: A tooling problem — network error, exception, unexpected shape.
    """

    EXECUTED_OK = "executed-ok"
    EXPECTED_ERROR = "expected-error"
    VERIFY_ONLY = "verify-only"
    FAILED = "FAILED"


@dataclass
class CommandOutcome:
    """Result of classifying/exercising one live command.

    Attributes:
        name: Command name as reported by the live server.
        bucket: Why the command was routed the way it was.
        status: What happened when it was (or was not) invoked.
        reason: Human-readable explanation, error text, or safety-list reason.
    """

    name: str
    bucket: Bucket
    status: Status
    reason: str


# Reused verbatim from scripts/command_inventory.py::get_standard_adapter_commands().
# Kept in sync manually; do not re-derive from the live registry.
STANDARD_ADAPTER_COMMANDS: FrozenSet[str] = frozenset(
    {
        "echo",
        "long_task",
        "job_status",
        "help",
        "health",
        "config",
        "reload",
        "settings",
        "load",
        "unload",
        "plugins",
        "transport_management",
        "proxy_registration",
        "roletest",
        "queue_add_job",
        "queue_start_job",
        "queue_stop_job",
        "queue_delete_job",
        "queue_get_job_status",
        "queue_get_job_logs",
        "queue_list_jobs",
        "queue_health",
    }
)

# Standard-adapter commands safe to execute plainly with no parameters.
# Everything else in STANDARD_ADAPTER_COMMANDS is classified verify-only, except
# long_task/job_status/queue_add_job/queue_get_job_status/queue_get_job_logs/
# queue_stop_job/queue_delete_job, which the queue lifecycle
# (_verify_client_all_commands_lifecycle_queue.py) executes as an ordered chain
# via the precomputed-outcomes table classify_command consults first.
ADAPTER_SAFE_TO_EXECUTE: FrozenSet[str] = frozenset(
    {"echo", "health", "help", "queue_health", "queue_list_jobs", "plugins", "roletest"}
)

# Fixed Bucket B list (26 entries) — NEVER invoked. Schema fetch only.
BUCKET_B_REASONS: Dict[str, str] = {
    "reload": "process-wide adapter control command, out of project scope",
    "load": "process-wide adapter module lifecycle command",
    "unload": "process-wide adapter module lifecycle command",
    "settings": "process-wide adapter settings command",
    "config": "process-wide adapter config command",
    "transport_management": "process-wide transport control command",
    "proxy_registration": "process-wide proxy registration control command",
    "start_repair_worker": "global worker lifecycle control",
    "stop_repair_worker": "global worker lifecycle control",
    "restore_database": "database-wide integrity operation risk",
    "repair_sqlite_database": "database-wide integrity operation risk",
    "run_uuid_identity_migration": "one-time global DB migration, irreversible risk",
    "delete_unwatched_projects": (
        "global bulk purge across all projects on the shared server"
    ),
    "clear_trash": (
        "global bulk purge across all projects' trash on the shared server"
    ),
    "rotate_all_logs": "global log rotation, side effect on shared server logs",
    "rotate_worker_logs": (
        "global worker log rotation, side effect on shared server logs"
    ),
    "project_set_mark_del": (
        "destroys the shared disposable fixture project mid-run (trash + DB "
        "clear); invoked exactly once by teardown instead"
    ),
    "git_push": "mutates a remote repository outside disposable sandbox control",
    "git_branch_push": (
        "mutates a remote repository outside disposable sandbox control"
    ),
    "git_branch_delete_remote": (
        "mutates a remote repository outside disposable sandbox control"
    ),
    "git_clone": (
        "creates project/workspace tree outside disposable-project scope "
        "(fixed Bucket B list)"
    ),
    "github_pr_create": "mutates real external GitHub repository state",
    "github_issue_create": "mutates real external GitHub repository state",
    "github_issue_comment": "mutates real external GitHub repository state",
    "github_pr_merge": "mutates real external GitHub repository state",
    "github_release_create": "mutates real external GitHub repository state",
}

# Background: docs/bugreports/2026-07-06-jsonrpc-empty-body-after-sync-cap-fallback.md
# documents a real process-wide outage on this exact server triggered by
# `revectorize force=true` on a large project timing out the sync cap.
OUTAGE_RISK_COMMANDS: FrozenSet[str] = frozenset(
    {"revectorize", "rebuild_faiss", "update_indexes"}
)

# General teardown/purge scoping gate: any live command (not already handled by
# Bucket B / REMOVED) whose name matches this pattern must have its schema
# checked for a `project_id` property before it may be invoked.
_PURGE_LIKE_PATTERN = re.compile(r"delete|purge|trash|mark_del|clear", re.IGNORECASE)


def is_purge_like(name: str) -> bool:
    """Return True if ``name`` looks like a delete/purge/trash/clear command.

    Args:
        name: Live command name.

    Returns:
        True when the name matches the case-insensitive purge-scoping pattern.
    """
    return bool(_PURGE_LIKE_PATTERN.search(name))


def schema_has_project_id(schema: Dict[str, Any]) -> bool:
    """Return True if ``project_id`` appears in the schema's properties.

    Args:
        schema: A ``get_schema()``-style dict (``properties``/``required``).

    Returns:
        True when ``project_id`` is a declared property of the command.
    """
    props = schema.get("properties") or {}
    required = schema.get("required") or []
    return "project_id" in props or "project_id" in required


def schema_has_force(schema: Dict[str, Any]) -> bool:
    """Return True if the schema declares a boolean ``force`` property.

    Args:
        schema: A ``get_schema()``-style dict.

    Returns:
        True when ``force`` is present among the schema's properties.
    """
    props = schema.get("properties") or {}
    return "force" in props


class _Missing:
    """Sentinel type for "no generic provider available for this property"."""

    def __repr__(self) -> str:
        """Return a short debug representation.

        Returns:
            The literal string ``"<MISSING>"``.
        """
        return "<MISSING>"


MISSING = _Missing()

# Per-command overrides for one required property, checked before the
# generic-by-property-name providers in fixture_value_for(). Needed when a
# command's required property name doesn't hint at the right fixture value
# (list_yaml_blocks requires "file_path" but only accepts .yaml/.yml — the
# generic "file_path" provider defaults to the seeded .py fixture) or needs a
# value no generic provider covers (get_file_lines' start_line/end_line pair).
_PER_COMMAND_PROPERTY_OVERRIDES: Dict[
    str, Dict[str, Callable[["FixtureContext"], Any]]
] = {
    "list_yaml_blocks": {
        "file_path": lambda fixtures: fixtures.yaml_file_path,
    },
    "get_file_lines": {
        "start_line": lambda fixtures: 1,
        "end_line": lambda fixtures: 10,
    },
}


def _generic_providers(
    fixtures: "FixtureContext",
) -> Dict[str, Callable[[], Any]]:
    """Build the exact-name provider table for the given fixture context.

    Args:
        fixtures: The disposable project/session fixture for this run.

    Returns:
        Mapping of schema property name to a zero-argument value provider.
    """
    return {
        "project_id": lambda: fixtures.project_id,
        "file_path": lambda: fixtures.py_file_path,
        "session_id": lambda: fixtures.session_id,
        "query": lambda: "def ",
        "pattern": lambda: "def ",
        "text": lambda: "def ",
        "content": lambda: "# verify sweep\n",
        "message": lambda: "verify sweep commit",
        "branch": lambda: "main",
        "branch_name": lambda: "main",
        "ref": lambda: "main",
        "limit": lambda: 5,
        "page": lambda: 1,
        "page_size": lambda: 5,
        "max_results": lambda: 5,
        "name": lambda: fixtures.project_name,
    }


def fixture_value_for(
    prop_name: str, fixtures: "FixtureContext", command_name: str = ""
) -> Any:
    """Synthesize a value for one required schema property, or return MISSING.

    Checks :data:`_PER_COMMAND_PROPERTY_OVERRIDES` for ``command_name`` first.
    Otherwise, property names hinting at a specific fixture file override the
    generic ``file_path`` default: names containing ``"yaml"`` map to the
    seeded YAML fixture; names containing ``"markdown"`` or a ``md`` word
    (``foo_md``, ``md_path``) map to the seeded Markdown fixture.

    Args:
        prop_name: Name of the required schema property.
        fixtures: The disposable project/session fixture for this run.
        command_name: Live command name the property belongs to, used only to
            look up a per-command override; empty string skips that lookup.

    Returns:
        A synthesized value, or the module-level :data:`MISSING` sentinel when
        no generic provider exists for ``prop_name``.
    """
    overrides = _PER_COMMAND_PROPERTY_OVERRIDES.get(command_name)
    if overrides and prop_name in overrides:
        return overrides[prop_name](fixtures)
    lower = prop_name.lower()
    if "yaml" in lower:
        return fixtures.yaml_file_path
    if "markdown" in lower or re.search(r"(^|_)md(_|$)", lower):
        return fixtures.md_file_path
    providers = _generic_providers(fixtures)
    if prop_name in providers:
        return providers[prop_name]()
    return MISSING


def is_seeded_file_value(value: Any, fixtures: "FixtureContext") -> bool:
    """Return True if ``value`` is one of the three seeded fixture file paths.

    Used to detect commands that depend on fixture files which may not have
    been successfully written to disk during setup.

    Args:
        value: A synthesized parameter value.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        True when ``value`` equals the py/yaml/md fixture file path.
    """
    return value in (
        fixtures.py_file_path,
        fixtures.yaml_file_path,
        fixtures.md_file_path,
    )


def truncate(text: str, limit: int = 200) -> str:
    """Truncate an error/reason string to a bounded, readable length.

    Args:
        text: Text to truncate.
        limit: Maximum length before truncation (default 200).

    Returns:
        ``text`` unchanged if short enough, else truncated with an ellipsis.
    """
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
