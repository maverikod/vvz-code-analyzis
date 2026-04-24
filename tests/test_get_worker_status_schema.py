"""get_worker_status JSON schema must advertise required worker_type for clients/LLMs."""

from code_analysis.commands.worker_status_mcp_commands.get_worker_status import (
    GetWorkerStatusMCPCommand,
)


def test_get_worker_status_schema_requires_worker_type_and_examples() -> None:
    schema = GetWorkerStatusMCPCommand.get_schema()
    assert schema.get("required") == ["worker_type"]
    assert "worker_type" in (schema.get("properties") or {})
    examples = schema.get("examples")
    assert isinstance(examples, list) and len(examples) >= 1
    assert all("worker_type" in ex for ex in examples if isinstance(ex, dict))
    desc = schema.get("description") or ""
    assert "worker_type" in desc.lower() or "params" in desc.lower()
