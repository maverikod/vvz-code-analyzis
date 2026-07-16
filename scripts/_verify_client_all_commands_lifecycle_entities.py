"""
Code-entity lookup command group for the live-server all-commands verifier.

All of these need a real class/function name from the seeded project rather
than a generic value — ``fixtures.class_name`` / ``fixtures.function_name``
name the ``SampleClass`` / ``greet`` fixture seeded by
``_verify_client_all_commands_fixtures._PY_FIXTURE_CONTENT``, where
``SampleClass.sample_method`` calls ``greet()`` so dependency/usage lookups
have a real edge to report.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Any, Dict

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import CommandOutcome
from _verify_client_all_commands_fixtures import FixtureContext
from _verify_client_all_commands_lifecycle_common import call_step


def _stringify_uuids(value: Any) -> Any:
    """Recursively replace ``uuid.UUID`` instances with ``str(...)``.

    Defensive measure for ``read_only_batch``: the server's batch aggregator
    (``code_analysis/commands/read_only_batch_command.py::_json_safe``) only
    sanitizes a value's own top-level type, not values nested inside a dict or
    list, so any UUID object nested in the request ``params`` (or echoed back
    in a nested result) trips a "Object of type UUID is not JSON serializable"
    failure. Ensures every id-shaped value crossing that boundary from this
    script is already a plain string.

    Args:
        value: Any JSON-shaped value that may contain nested ``uuid.UUID``
            instances.

    Returns:
        The same structure with every ``uuid.UUID`` replaced by its string form.
    """
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _stringify_uuids(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_stringify_uuids(item) for item in value]
    return value


async def run_entity_lifecycle(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Call every entity-lookup command against the seeded ``SampleClass``.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        Mapping of every command name this lifecycle covers to its outcome.
    """
    outcomes: Dict[str, CommandOutcome] = {}
    project_id = fixtures.project_id

    outcomes["get_code_entity_info"] = await call_step(
        client,
        "get_code_entity_info",
        {
            "project_id": project_id,
            "entity_type": "class",
            "entity_name": fixtures.class_name,
        },
    )
    outcomes["get_entity_dependencies"] = await call_step(
        client,
        "get_entity_dependencies",
        {
            "project_id": project_id,
            "entity_type": "class",
            "entity_name": fixtures.class_name,
        },
    )
    outcomes["get_entity_dependents"] = await call_step(
        client,
        "get_entity_dependents",
        {
            "project_id": project_id,
            "entity_type": "function",
            "entity_name": fixtures.function_name,
        },
    )
    outcomes["find_dependencies"] = await call_step(
        client,
        "find_dependencies",
        {
            "project_id": project_id,
            "entity_name": fixtures.class_name,
            "entity_type": "class",
        },
    )
    outcomes["find_usages"] = await call_step(
        client,
        "find_usages",
        {
            "project_id": project_id,
            "target_name": fixtures.function_name,
            "target_type": "function",
        },
    )
    outcomes["list_class_methods"] = await call_step(
        client,
        "list_class_methods",
        {"project_id": project_id, "class_name": fixtures.class_name},
    )
    outcomes["analyze_tree"] = await call_step(
        client,
        "analyze_tree",
        {"project_id": project_id, "roots": ["."], "mode": "structure"},
    )
    outcomes["read_only_batch"] = await call_step(
        client,
        "read_only_batch",
        _stringify_uuids(
            {
                "invocations": [
                    {
                        "command": "list_code_entities",
                        "params": {"project_id": project_id},
                    }
                ]
            }
        ),
        ok_reason="whitelisted list_code_entities invocation executed via read_only_batch",
    )
    return outcomes
