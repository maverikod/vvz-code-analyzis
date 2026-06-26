"""get_worker_status JSON schema: optional worker_type, examples for all / per-type."""

import inspect

from code_analysis.commands.worker_status_mcp_commands.get_worker_status import (
    GetWorkerStatusMCPCommand,
)
from code_analysis.commands.worker_status_mcp_commands.get_worker_status_metadata import (
    get_metadata,
)


def test_get_worker_status_schema_worker_type_optional_and_examples() -> None:
    """Verify test get worker status schema worker type optional and examples."""
    schema = GetWorkerStatusMCPCommand.get_schema()
    assert schema.get("required") in (None, [], ())
    props = schema.get("properties") or {}
    assert "worker_type" in props
    wt = props["worker_type"]
    assert "all" in (wt.get("enum") or [])
    examples = schema.get("examples")
    assert isinstance(examples, list) and len(examples) >= 1
    assert any(isinstance(ex, dict) and "worker_type" not in ex for ex in examples)
    assert any(
        isinstance(ex, dict) and ex.get("worker_type") == "all" for ex in examples
    )
    desc = schema.get("description") or ""
    assert "worker_type" in desc.lower() or "omit" in desc.lower()


def test_get_worker_status_metadata_parameter_keys_and_enums_match_schema() -> None:
    """Verify test get worker status metadata parameter keys and enums match schema."""
    schema = GetWorkerStatusMCPCommand.get_schema()
    props = schema.get("properties") or {}
    meta = get_metadata(GetWorkerStatusMCPCommand)
    mparams = meta.get("parameters") or {}
    assert set(mparams.keys()) == set(props.keys())
    for name, spec in props.items():
        assert mparams[name].get("type") == spec.get("type"), name
        schema_enum = spec.get("enum")
        if schema_enum is not None:
            assert mparams[name].get("enum") == list(schema_enum), name


def test_get_worker_status_execute_accepts_schema_property_names() -> None:
    """execute() kwargs from MCP must align with get_schema() property keys."""
    schema_props = set(
        (GetWorkerStatusMCPCommand.get_schema().get("properties") or {}).keys()
    )
    sig = inspect.signature(GetWorkerStatusMCPCommand.execute)
    execute_params = {p for p in sig.parameters if p != "self"}
    # **kwargs absorbs transport extras; declared names must cover schema keys
    assert schema_props <= execute_params, (
        schema_props - execute_params,
        execute_params,
    )
