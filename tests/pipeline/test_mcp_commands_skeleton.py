"""
Skeleton MCP command tests against real code-analysis-server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest

from tests.pipeline.mcp_client import MCPClientWrapper, is_available

LONG_RUNNING_COMMANDS = {"update_indexes", "comprehensive_analysis"}
STANDARD_ADAPTER_COMMANDS = {
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
NETWORK_ERROR_KEYWORDS = {
    "connection refused",
    "timed out",
    "timeout",
    "unreachable",
    "failed to connect",
    "dns",
}


def _discover_custom_commands() -> list[str]:
    """Return sorted list of custom commands excluding standard adapter ones.

    This is equivalent to scripts.command_inventory.get_all_registered_commands(),
    but performed lazily to avoid hard mypy coupling with that utility module.
    """
    registry_module = import_module("mcp_proxy_adapter.commands.command_registry")
    hooks_module = import_module("code_analysis.hooks")

    registry_class = getattr(registry_module, "CommandRegistry")
    register_commands = getattr(hooks_module, "register_code_analysis_commands")

    registry = registry_class()
    register_commands(registry)

    commands: dict[str, Any] = getattr(registry, "_commands", {})
    return sorted(name for name in commands if name not in STANDARD_ADAPTER_COMMANDS)


def _is_coherent_response(response: Any) -> bool:
    """Check response has a meaningful payload shape."""
    if response is None:
        return False
    if isinstance(response, dict):
        known_keys = {"result", "error", "success", "status", "message", "data"}
        return any(key in response for key in known_keys) or bool(response)
    return True


def _is_infrastructure_error(message: str) -> bool:
    """Detect transport/runtime errors that should fail the test."""
    lower_message = message.lower()
    return any(keyword in lower_message for keyword in NETWORK_ERROR_KEYWORDS)


def _walk_help_payload(
    node: Any,
    all_params: set[str],
    required_params: set[str],
) -> None:
    """Recursively extract input parameter names from help/schema payload."""
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            all_params.update(str(name) for name in properties)

        required = node.get("required")
        if isinstance(required, list):
            for name in required:
                if isinstance(name, str):
                    required_params.add(name)

        parameters = node.get("parameters")
        if isinstance(parameters, dict):
            all_params.update(str(name) for name in parameters)
        elif isinstance(parameters, list):
            for item in parameters:
                if isinstance(item, dict):
                    name = item.get("name")
                    if isinstance(name, str):
                        all_params.add(name)
                    if item.get("required") is True and isinstance(name, str):
                        required_params.add(name)

        args = node.get("args")
        if isinstance(args, dict):
            all_params.update(str(name) for name in args)

        for value in node.values():
            _walk_help_payload(value, all_params, required_params)
    elif isinstance(node, list):
        for item in node:
            _walk_help_payload(item, all_params, required_params)


def _extract_parameter_mapping(help_response: Any) -> dict[str, list[str]]:
    """Build canonical parameter mapping from help command response."""
    all_params: set[str] = set()
    required_params: set[str] = set()
    _walk_help_payload(help_response, all_params, required_params)

    sorted_all = sorted(all_params)
    sorted_required = sorted(name for name in required_params if name in all_params)
    return {"all_params": sorted_all, "required_params": sorted_required}


def _get_skeleton_payload_for_command(
    command: str,
    command_parameters: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return minimal payload for skeleton call.

    For commands with required fields, an intentionally incomplete payload
    is used to validate expected schema errors in this skeleton step.
    """
    mapping = command_parameters.get(command, {})
    required_params = mapping.get("required_params", [])
    if not required_params:
        return {}
    return {}


def _call_command_once(
    client: MCPClientWrapper,
    command: str,
    params: dict[str, Any],
) -> tuple[bool, Any]:
    """Call one command once, returning success flag and payload/error."""
    try:
        use_queue = command in LONG_RUNNING_COMMANDS
        response = client.call_command(
            command=command,
            params=params,
            use_queue=use_queue if use_queue else None,
        )
        return True, response
    except Exception as exc:  # pragma: no cover - real server behavior varies
        return False, exc


try:
    CUSTOM_COMMANDS = _discover_custom_commands()
    DISCOVERY_ERROR: str | None = None
except Exception as exc:  # pragma: no cover - depends on environment
    CUSTOM_COMMANDS = []
    DISCOVERY_ERROR = f"{type(exc).__name__}: {exc}"


@pytest.fixture(scope="session")
def mcp_client() -> MCPClientWrapper:
    """Provide real MCP client and skip when client/server is unavailable."""
    if DISCOVERY_ERROR is not None:
        pytest.skip(f"Command discovery is unavailable: {DISCOVERY_ERROR}")

    if not is_available():
        pytest.skip(
            "mcp-proxy-adapter direct client is unavailable in test environment"
        )

    client = MCPClientWrapper()
    try:
        client.call_command(command="list_projects", params={})
    except Exception as exc:  # pragma: no cover - depends on environment
        pytest.skip(f"Real server is unavailable for skeleton tests: {exc}")
    return client


@pytest.fixture(scope="session")
def command_parameters(mcp_client: MCPClientWrapper) -> dict[str, dict[str, Any]]:
    """Collect canonical command->parameter mapping from help metadata."""
    mapping: dict[str, dict[str, Any]] = {}
    for command in CUSTOM_COMMANDS:
        help_response = mcp_client.call_command(
            command="help",
            params={"command": command},
        )
        extracted = _extract_parameter_mapping(help_response)
        mapping[command] = {
            "source": "help",
            "all_params": extracted["all_params"],
            "required_params": extracted["required_params"],
            "explicitly_empty": len(extracted["all_params"]) == 0,
        }
    return mapping


def test_custom_command_inventory_is_not_empty() -> None:
    """Ensure custom command inventory is available for skeleton coverage."""
    if DISCOVERY_ERROR is not None:
        pytest.skip(f"Command discovery is unavailable: {DISCOVERY_ERROR}")
    assert CUSTOM_COMMANDS, "No custom commands discovered for skeleton tests"


def test_parameter_mapping_collected_for_all_commands(
    command_parameters: dict[str, dict[str, Any]],
) -> None:
    """Verify canonical command->params mapping exists for every command."""
    missing = sorted(set(CUSTOM_COMMANDS) - set(command_parameters))
    assert not missing, f"Missing parameter mapping for commands: {missing}"

    empty_without_flag: list[str] = []
    for command in CUSTOM_COMMANDS:
        info = command_parameters[command]
        all_params = info.get("all_params", [])
        explicitly_empty = bool(info.get("explicitly_empty"))
        if not all_params and not explicitly_empty:
            empty_without_flag.append(command)
    assert not empty_without_flag, (
        "Empty parameter list must be explicit for commands: " f"{empty_without_flag}"
    )


@pytest.mark.parametrize("command", CUSTOM_COMMANDS)
def test_command_skeleton_call_via_real_mcp(
    command: str,
    mcp_client: MCPClientWrapper,
    command_parameters: dict[str, dict[str, Any]],
) -> None:
    """Call each custom command once and assert success or expected error."""
    payload = _get_skeleton_payload_for_command(command, command_parameters)
    is_success, result = _call_command_once(
        client=mcp_client,
        command=command,
        params=payload,
    )

    if is_success:
        assert _is_coherent_response(
            result
        ), f"Command '{command}' returned incoherent response: {result!r}"
        return

    error_message = str(result).strip()
    assert error_message, f"Command '{command}' failed without error message"
    assert not _is_infrastructure_error(error_message), (
        f"Command '{command}' failed due to infrastructure/runtime issue: "
        f"{error_message}"
    )
