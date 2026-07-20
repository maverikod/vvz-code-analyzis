"""
Regression: AST/entity command responses expose project-relative ``file_path``.

A ``files`` row written via ``DatabaseClient.add_file`` stores an ABSOLUTE path
in ``files.path`` and the project-relative POSIX path in ``files.relative_path``
(see ``code_analysis/core/database_client/client_api_files.py:add_file``).
Response builders used to select ``f.path AS file_path`` directly, leaking the
absolute filesystem path to callers. This asserts each command family now
returns the relative value instead (TZ cluster: 9ab2f3ba/cc5d0a23/3540f30e/
ac831d35/4750a3c5).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import uuid
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from tests.sqlite_in_process_legacy_facade import make_sqlite_in_process_legacy_facade

from code_analysis.commands.ast.dependencies import FindDependenciesMCPCommand
from code_analysis.commands.ast.entity_dependencies import (
    GetEntityDependentsMCPCommand,
)
from code_analysis.commands.ast.entity_info import GetCodeEntityInfoMCPCommand
from code_analysis.commands.ast.graph import ExportGraphMCPCommand
from code_analysis.commands.ast.hierarchy import GetClassHierarchyMCPCommand
from code_analysis.commands.ast.list_entities import ListCodeEntitiesMCPCommand
from code_analysis.commands.ast.search_nodes import SearchASTNodesMCPCommand
from code_analysis.commands.ast.usages import FindUsagesMCPCommand
from code_analysis.commands.base_mcp_command import BaseMCPCommand


def _uuid4() -> str:
    """Return a UUID4 string usable as a valid cst_node_id."""
    return str(uuid.uuid4())


@pytest.fixture
def test_db(tmp_path):
    """SQLite-backed DatabaseClient facade (in-process RPC)."""
    facade, raw_client = make_sqlite_in_process_legacy_facade(tmp_path)
    # commands call db.disconnect(); keep facade alive across the test body.
    cast(Any, facade).disconnect = MagicMock()
    try:
        yield facade
    finally:
        raw_client.disconnect()


@pytest.fixture
def project_id():
    """Project UUID."""
    return str(uuid.uuid4())


def _insert_file(test_db, project_id, absolute_path, relative_path):
    """Insert a ``files`` row the way ``DatabaseClient.add_file`` writes it:

    ``path`` holds the absolute filesystem path, ``relative_path`` holds the
    project-relative POSIX path. (Not routed through ``add_file`` itself: that
    call chain needs a fully wired ``projects.root_path``/``watch_dir`` setup
    that this lightweight raw-SQL fixture -- matching the pattern used by
    ``test_class_hierarchy_entity_dependents_inheritance.py`` -- does not
    provide.)
    """
    file_id = str(uuid.uuid4())
    test_db._execute(
        "INSERT INTO files (id, project_id, path, relative_path, lines, "
        "last_modified, has_docstring) VALUES (?, ?, ?, ?, 0, 0, 0)",
        (file_id, project_id, absolute_path, relative_path),
    )
    test_db._commit()
    return file_id


@pytest.fixture
def fixture_data(test_db, tmp_path, project_id):
    """Project rooted at ``tmp_path`` with one file whose row is written absolute.

    ``files.path`` holds the absolute path and ``files.relative_path`` holds
    "pkg/mod.py", the same way ``DatabaseClient.add_file`` writes them; this is
    the "written absolute" half of the regression contract.
    """
    test_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(tmp_path), tmp_path.name),
    )
    test_db._commit()

    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    mod_path = pkg_dir / "mod.py"
    # Real source matching the DB rows below (find_usages resolves cst_node_id
    # by parsing this file with libcst, not from the DB column).
    mod_path.write_text(
        "class Widget:\n    pass\n\n\ndef helper():\n    pass\n", encoding="utf-8"
    )
    relative_file_path = "pkg/mod.py"

    file_id = _insert_file(test_db, project_id, str(mod_path), relative_file_path)

    widget_cst = _uuid4()
    widget_id = str(uuid.uuid4())
    test_db._execute(
        "INSERT INTO classes (id, file_id, name, line, end_line, docstring, bases, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (widget_id, file_id, "Widget", 1, 2, None, "[]", widget_cst),
    )

    helper_cst = _uuid4()
    helper_id = str(uuid.uuid4())
    test_db._execute(
        "INSERT INTO functions (id, file_id, name, line, end_line, docstring, args, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (helper_id, file_id, "helper", 4, 5, None, "", helper_cst),
    )

    run_cst = _uuid4()
    run_id = str(uuid.uuid4())
    test_db._execute(
        "INSERT INTO methods (id, class_id, name, line, end_line, docstring, args, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, widget_id, "run", 2, 2, None, "self", run_cst),
    )

    test_db._execute(
        "INSERT INTO imports (id, file_id, name, module, import_type, line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), file_id, "os", "os", "import", 1),
    )
    test_db._execute(
        "INSERT INTO usages (id, file_id, line, usage_type, target_type, target_class, target_name) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), file_id, 4, "call", "function", None, "helper"),
    )

    # Second file/class: Sub(Widget) - drives the inheritance branches
    # (find_dependencies/find_usages/get_class_hierarchy/get_entity_dependents).
    sub_path = pkg_dir / "sub.py"
    sub_path.write_text("class Sub(Widget):\n    pass\n", encoding="utf-8")
    sub_file_id = _insert_file(test_db, project_id, str(sub_path), "pkg/sub.py")
    sub_cst = _uuid4()
    sub_id = str(uuid.uuid4())
    test_db._execute(
        "INSERT INTO classes (id, file_id, name, line, end_line, docstring, bases, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (sub_id, sub_file_id, "Sub", 1, 2, None, json.dumps(["Widget"]), sub_cst),
    )
    test_db.add_entity_cross_ref(
        caller_class_id=sub_id,
        caller_method_id=None,
        caller_function_id=None,
        callee_class_id=widget_id,
        callee_method_id=None,
        callee_function_id=None,
        ref_type="inherit",
        file_id=sub_file_id,
        line=1,
    )
    test_db._commit()

    return {
        "relative_file_path": relative_file_path,
        "widget_id": widget_id,
    }


def _patched(test_db, tmp_path):
    """Patch BaseMCPCommand DB/root resolution to use the fixture facade."""
    return (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=test_db
        ),
        patch.object(BaseMCPCommand, "_resolve_project_root", return_value=tmp_path),
    )


@pytest.mark.asyncio
async def test_list_code_entities_file_path_is_relative(
    test_db, tmp_path, project_id, fixture_data
):
    """list_code_entities: file_path is project-relative, not the absolute DB path."""
    p1, p2 = _patched(test_db, tmp_path)
    with p1, p2:
        cmd = ListCodeEntitiesMCPCommand()
        result = await cmd.execute(project_id=project_id, entity_type="class")

    entities = result.data["entities"]
    assert entities, "expected at least one class entity"
    for e in entities:
        assert e["file_path"] == fixture_data["relative_file_path"] or e[
            "file_path"
        ] in ("pkg/mod.py", "pkg/sub.py")
        assert not Path(e["file_path"]).is_absolute()


@pytest.mark.asyncio
async def test_get_code_entity_info_file_path_is_relative(
    test_db, tmp_path, project_id, fixture_data
):
    """get_code_entity_info: file_path is project-relative."""
    p1, p2 = _patched(test_db, tmp_path)
    with p1, p2:
        cmd = GetCodeEntityInfoMCPCommand()
        result = await cmd.execute(
            project_id=project_id, entity_type="class", entity_name="Widget"
        )

    assert result.data["success"] is True
    for e in result.data["entities"]:
        assert e["file_path"] == fixture_data["relative_file_path"]
        assert not Path(e["file_path"]).is_absolute()


@pytest.mark.asyncio
async def test_get_class_hierarchy_file_path_is_relative(
    test_db, tmp_path, project_id, fixture_data
):
    """get_class_hierarchy: file_path is project-relative."""
    p1, p2 = _patched(test_db, tmp_path)
    with p1, p2:
        cmd = GetClassHierarchyMCPCommand()
        result = await cmd.execute(project_id=project_id)

    hierarchy = result.data["hierarchy"]
    assert "Widget" in hierarchy
    assert hierarchy["Widget"]["file_path"] == fixture_data["relative_file_path"]
    assert "Sub" in hierarchy["Widget"]["children"]


@pytest.mark.asyncio
async def test_find_dependencies_file_path_is_relative(
    test_db, tmp_path, project_id, fixture_data
):
    """find_dependencies: import/inheritance/usage rows all get relative file_path."""
    p1, p2 = _patched(test_db, tmp_path)
    with p1, p2:
        cmd = FindDependenciesMCPCommand()
        result = await cmd.execute(
            project_id=project_id, entity_name="Widget", entity_type="class"
        )

    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    deps = result.data["dependencies"]
    inheritance_rows = [d for d in deps if d["type"] == "inheritance"]
    assert inheritance_rows, "expected the Sub(Widget) inheritance row"
    for d in deps:
        assert not Path(d["file_path"]).is_absolute()
        assert d["file_path"] in ("pkg/mod.py", "pkg/sub.py")


@pytest.mark.asyncio
async def test_find_usages_file_path_is_relative(
    test_db, tmp_path, project_id, fixture_data
):
    """find_usages: usage/import/inheritance rows all get relative file_path."""
    p1, p2 = _patched(test_db, tmp_path)
    with p1, p2:
        cmd = FindUsagesMCPCommand()
        result = await cmd.execute(
            project_id=project_id, target_name="helper", target_type="function"
        )

    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    usages = result.data["usages"]
    assert usages, "expected the usage of helper() to resolve a cst_node_id"
    for u in usages:
        assert not Path(u["file_path"]).is_absolute()
        assert u["file_path"] == fixture_data["relative_file_path"]


@pytest.mark.asyncio
async def test_get_entity_dependents_file_path_is_relative(
    test_db, tmp_path, project_id, fixture_data
):
    """get_entity_dependents: cross_ref-derived rows get relative file_path."""
    p1, p2 = _patched(test_db, tmp_path)
    with p1, p2:
        cmd = GetEntityDependentsMCPCommand()
        result = await cmd.execute(
            project_id=project_id,
            entity_type="class",
            entity_id=fixture_data["widget_id"],
        )

    dependents = result.data["dependents"]
    assert dependents, "expected Sub as a dependent of Widget"
    for d in dependents:
        assert not Path(d["file_path"]).is_absolute()
        assert d["file_path"] == "pkg/sub.py"


@pytest.mark.asyncio
async def test_search_ast_nodes_file_path_is_relative(
    test_db, tmp_path, project_id, fixture_data
):
    """search_ast_nodes: class/function/method rows get relative file_path."""
    p1, p2 = _patched(test_db, tmp_path)
    with p1, p2:
        cmd = SearchASTNodesMCPCommand()
        result = await cmd.execute(project_id=project_id, node_type="class")

    nodes = result.data["nodes"]
    assert nodes
    for n in nodes:
        assert not Path(n["file_path"]).is_absolute()


@pytest.mark.asyncio
async def test_export_graph_call_graph_nodes_are_relative(
    test_db, tmp_path, project_id, fixture_data
):
    """export_graph(call_graph): usage-derived node identities are relative paths."""
    p1, p2 = _patched(test_db, tmp_path)
    with p1, p2:
        cmd = ExportGraphMCPCommand()
        result = await cmd.execute(
            project_id=project_id, graph_type="call_graph", format="json"
        )

    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    assert result.data["nodes"], "expected at least the usage's source file node"
    for n in result.data["nodes"]:
        assert not Path(n).is_absolute()
    for en in result.data["entity_nodes"]:
        assert not Path(en["file_path"]).is_absolute()
