"""Tests for LogicalWriteProgramV1 metadata and client forwarding (no DB)."""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Tuple
from unittest.mock import Mock

import pytest

from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.client_operations import _ClientOperationsMixin
from code_analysis.core.database_client.protocol.rpc_protocol import RPCResponse


class _RecordingFakeRpc:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, Dict[str, Any]]] = []

    def call(self, method: str, params: Dict[str, Any]) -> RPCResponse:
        self.calls.append((method, params))
        return RPCResponse(result={"success": True, "data": {}})


def _one_batch_program(**extra: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "batches": [
            [
                ("SELECT 1", ()),
            ]
        ],
    }
    base.update(extra)
    return base


def test_program_with_only_batches_preserves_old_behavior() -> None:
    fake = _RecordingFakeRpc()
    client = DatabaseClient(rpc_client=fake)
    program = _one_batch_program()
    client.execute_logical_write_operation(program)  # type: ignore[arg-type]
    assert len(fake.calls) == 1
    _, params = fake.calls[0]
    assert "batches" in params
    assert "operation_name" not in params
    assert "project_id" not in params
    assert "lock_scope" not in params
    assert params.get("defer_constraints") is not True


def test_defer_constraints_is_preserved() -> None:
    fake = _RecordingFakeRpc()
    client = DatabaseClient(rpc_client=fake)
    program = _one_batch_program(defer_constraints=True)
    client.execute_logical_write_operation(program)  # type: ignore[arg-type]
    _, params = fake.calls[0]
    assert params.get("defer_constraints") is True
    assert "batches" in params
    assert isinstance(params["batches"], list)
    assert len(params["batches"]) == 1
    first = params["batches"][0]
    assert isinstance(first, list) and len(first) == 1
    op0 = first[0]
    assert op0.get("sql") == "SELECT 1"
    # Empty program params are sent as list (same as other execute_batch-style paths).
    assert op0.get("params") == []


def test_metadata_fields_are_forwarded() -> None:
    fake = _RecordingFakeRpc()
    client = DatabaseClient(rpc_client=fake)
    program = _one_batch_program(
        operation_name="my_op",
        project_id="proj-uuid-1",
        lock_scope="project_write",
    )
    client.execute_logical_write_operation(program)  # type: ignore[arg-type]
    _, params = fake.calls[0]
    assert params["operation_name"] == "my_op"
    assert params["project_id"] == "proj-uuid-1"
    assert params["lock_scope"] == "project_write"


def test_valid_lock_scope_values() -> None:
    for lock_scope in ("none", "project_write", "project_read"):
        fake = _RecordingFakeRpc()
        client = DatabaseClient(rpc_client=fake)
        program = _one_batch_program(lock_scope=lock_scope)
        client.execute_logical_write_operation(program)  # type: ignore[arg-type]
        assert fake.calls[0][1]["lock_scope"] == lock_scope


def test_invalid_operation_name_type_raises_value_error() -> None:
    fake = _RecordingFakeRpc()
    client = DatabaseClient(rpc_client=fake)
    program = _one_batch_program(operation_name=123)  # type: ignore[dict-item]
    with pytest.raises(ValueError, match="operation_name"):
        client.execute_logical_write_operation(program)  # type: ignore[arg-type]
    assert len(fake.calls) == 0


def test_invalid_project_id_type_raises_value_error() -> None:
    fake = _RecordingFakeRpc()
    client = DatabaseClient(rpc_client=fake)
    program = _one_batch_program(project_id=456)  # type: ignore[dict-item]
    with pytest.raises(ValueError, match="project_id"):
        client.execute_logical_write_operation(program)  # type: ignore[arg-type]
    assert len(fake.calls) == 0


def test_invalid_lock_scope_raises_value_error() -> None:
    fake = _RecordingFakeRpc()
    client = DatabaseClient(rpc_client=fake)
    program = _one_batch_program(lock_scope="invalid")  # type: ignore[dict-item]
    with pytest.raises(ValueError, match="lock_scope"):
        client.execute_logical_write_operation(program)  # type: ignore[arg-type]
    assert len(fake.calls) == 0


def test_metadata_forwarding_does_not_retry_client_side() -> None:
    src = inspect.getsource(
        _ClientOperationsMixin.execute_logical_write_operation,
    )
    assert "time.sleep" not in src
    assert "sqlstate" not in src.lower()
    rpc_call = Mock(
        return_value=RPCResponse(result={"success": True, "data": {}}),
    )
    fake_client = Mock(call=rpc_call)
    client = DatabaseClient(rpc_client=fake_client)
    program = _one_batch_program(
        operation_name="x",
        project_id="p",
        lock_scope="none",
    )
    client.execute_logical_write_operation(program)  # type: ignore[arg-type]
    assert rpc_call.call_count == 1


def test_metadata_forwarding_does_not_acquire_project_activity_locks() -> None:
    mod = inspect.getmodule(_ClientOperationsMixin)
    assert mod is not None
    import code_analysis.core.database_client.client_operations as co

    full = inspect.getsource(co)
    assert "worker_activity" not in full
    assert "activity_coordinator" not in full
    assert "ActivityCoordinator" not in full

    fake = _RecordingFakeRpc()
    client = DatabaseClient(rpc_client=fake)
    program = _one_batch_program(
        project_id="proj-z",
        lock_scope="project_read",
    )
    client.execute_logical_write_operation(program)  # type: ignore[arg-type]
    assert len(fake.calls) == 1
