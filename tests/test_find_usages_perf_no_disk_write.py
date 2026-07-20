"""
Regression: find_usages caches the CST tree per distinct file (not per usage
record) and never writes to disk from the read path (card 4750a3c5).

Before the fix, ``_resolve_cst_node_id_at_line`` called ``load_file_to_tree``
once PER usage record even when several usages share the same file - a full
disk read + libcst parse (+ possible write-back via
``tree_builder._read_logical_py_source_sync_disk`` and the ``.py.tree``
sidecar) per usage. This asserts: (1) the parse layer (``load_file_to_tree``)
is invoked exactly once per distinct file no matter how many usages that file
has, and (2) the source file's mtime is unchanged after find_usages runs.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import uuid
from unittest.mock import patch

import pytest

from tests.sqlite_in_process_legacy_facade import make_sqlite_in_process_legacy_facade

import code_analysis.commands.ast.usages as usages_module
from code_analysis.commands.ast.usages import FindUsagesMCPCommand
from code_analysis.commands.base_mcp_command import BaseMCPCommand
from mcp_proxy_adapter.commands.result import SuccessResult


@pytest.fixture
def test_db(tmp_path):
    """SQLite-backed DatabaseClient facade (in-process RPC)."""
    facade, raw_client = make_sqlite_in_process_legacy_facade(tmp_path)
    try:
        yield facade
    finally:
        raw_client.disconnect()


@pytest.fixture
def project_id():
    """Project UUID."""
    return str(uuid.uuid4())


@pytest.fixture
def many_usages_one_file(test_db, tmp_path, project_id):
    """One file with three distinct call sites of ``helper()``."""
    test_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(tmp_path), tmp_path.name),
    )
    test_db._commit()

    mod_path = tmp_path / "mod.py"
    source = (
        "def helper():\n"
        "    pass\n"
        "\n"
        "\n"
        "def caller_one():\n"
        "    helper()\n"
        "\n"
        "\n"
        "def caller_two():\n"
        "    helper()\n"
        "\n"
        "\n"
        "def caller_three():\n"
        "    helper()\n"
    )
    mod_path.write_text(source, encoding="utf-8")

    file_id = str(uuid.uuid4())
    test_db._execute(
        "INSERT INTO files (id, project_id, path, relative_path, lines, "
        "last_modified, has_docstring) VALUES (?, ?, ?, ?, 0, 0, 0)",
        (file_id, project_id, str(mod_path), "mod.py"),
    )
    test_db._commit()

    for call_line in (6, 10, 14):
        test_db._execute(
            "INSERT INTO usages (id, file_id, line, usage_type, target_type, "
            "target_class, target_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                file_id,
                call_line,
                "call",
                "function",
                None,
                "helper",
            ),
        )
    test_db._commit()

    return {"mod_path": mod_path}


@pytest.mark.asyncio
async def test_find_usages_builds_tree_once_per_distinct_file(
    test_db, tmp_path, project_id, many_usages_one_file
):
    """3 usages in 1 file -> load_file_to_tree is called exactly once."""
    call_count = 0
    real_load_file_to_tree = usages_module.load_file_to_tree

    def counting_load_file_to_tree(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return real_load_file_to_tree(*args, **kwargs)

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=test_db
        ),
        patch.object(BaseMCPCommand, "_resolve_project_root", return_value=tmp_path),
        patch.object(
            usages_module, "load_file_to_tree", side_effect=counting_load_file_to_tree
        ),
    ):
        cmd = FindUsagesMCPCommand()
        result = await cmd.execute(
            project_id=project_id, target_name="helper", target_type="function"
        )

    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    usages = result.data["usages"]
    assert len(usages) == 3, f"expected all 3 call sites resolved, got {usages!r}"
    assert call_count == 1, (
        "expected load_file_to_tree to be called once for the one distinct "
        f"file backing all 3 usages, got {call_count} calls"
    )


@pytest.mark.asyncio
async def test_find_usages_does_not_write_to_disk(
    test_db, tmp_path, project_id, many_usages_one_file
):
    """find_usages must not change the source file's content or mtime."""
    mod_path = many_usages_one_file["mod_path"]
    before_mtime = mod_path.stat().st_mtime_ns
    before_content = mod_path.read_bytes()

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=test_db
        ),
        patch.object(BaseMCPCommand, "_resolve_project_root", return_value=tmp_path),
    ):
        cmd = FindUsagesMCPCommand()
        result = await cmd.execute(
            project_id=project_id, target_name="helper", target_type="function"
        )

    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    assert result.data["usages"], "expected resolved usages"
    assert mod_path.stat().st_mtime_ns == before_mtime
    assert mod_path.read_bytes() == before_content
    assert not mod_path.with_suffix(
        ".py.tree"
    ).exists(), "find_usages (a read) must not write a .py.tree sidecar"
