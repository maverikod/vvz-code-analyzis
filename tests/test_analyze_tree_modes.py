"""
Unit tests for analyze_tree mode post-processors (R1/R3 at unit level).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.commands.analyze_tree.core_types import CoreData, Edge
from code_analysis.commands.analyze_tree.modes import (
    classify_verdict,
    is_test_path,
    run_mode,
)

ROOTS = ["pkg/sub"]
INTERNAL = ["pkg/sub/a.py", "pkg/sub/b.py"]
PROJECT_FILES = set(INTERNAL) | {"pkg/core/exc.py", "pkg/core/git_integration.py", "pkg/caller.py"}


def _core(edges):
    return CoreData(
        roots=list(ROOTS),
        internal_files=list(INTERNAL),
        internal_set=set(INTERNAL),
        project_files=set(PROJECT_FILES),
        edges=edges,
        staleness={"counts": {}},
    )


EDGES = [
    # a.py → project leak (outbound.project / blocker)
    Edge(src="pkg/sub/a.py", kind="project", module="pkg.core.exc", target_rel="pkg/core/exc.py"),
    # a.py → server-bound leak (verdict keep_in_server)
    Edge(src="pkg/sub/a.py", kind="project", module="pkg.core.git_integration",
         target_rel="pkg/core/git_integration.py"),
    # a.py → stdlib + third party
    Edge(src="pkg/sub/a.py", kind="stdlib", module="os"),
    Edge(src="pkg/sub/a.py", kind="third_party", module="libcst"),
    # intra-subtree edges forming a cycle a <-> b
    Edge(src="pkg/sub/a.py", kind="project", module="pkg.sub.b", target_rel="pkg/sub/b.py"),
    Edge(src="pkg/sub/b.py", kind="project", module="pkg.sub.a", target_rel="pkg/sub/a.py"),
    # external caller importing INTO the sub-tree (inbound)
    Edge(src="pkg/caller.py", kind="project", module="pkg.sub.a", target_rel="pkg/sub/a.py"),
]


def test_package_boundary_blocks_and_inbound():
    data = run_mode("package_boundary", _core(EDGES), with_verdict=True)
    assert data["internal_files"] == INTERNAL

    targets = {b["target"] for b in data["outbound"]["project"]}
    assert "pkg/core/exc.py" in targets
    assert "pkg/core/git_integration.py" in targets
    # intra-subtree edge is NOT outbound
    assert "pkg/sub/b.py" not in targets

    assert data["outbound"]["third_party"] == ["libcst"]
    # stdlib hidden unless include_stdlib
    assert "stdlib" not in data["outbound"]

    inbound = {i["importer"]: i["targets"] for i in data["inbound"]}
    assert inbound == {"pkg/caller.py": ["pkg/sub/a.py"]}

    verdicts = {v["target"]: v["verdict"] for v in data["verdict"]}
    assert verdicts["pkg/core/git_integration.py"] == "keep_in_server"
    assert verdicts["pkg/core/exc.py"] == "pull_in"


def test_package_boundary_include_stdlib():
    data = run_mode("package_boundary", _core(EDGES), include_stdlib=True)
    assert data["outbound"]["stdlib"] == ["os"]


def test_dependencies_has_no_cycle_data():
    data = run_mode("dependencies", _core(EDGES))
    assert "cycles" not in data
    internal_pairs = {(e["from"], e["to"]) for e in data["edges"]["internal"]}
    assert ("pkg/sub/a.py", "pkg/sub/b.py") in internal_pairs
    assert ("pkg/sub/b.py", "pkg/sub/a.py") in internal_pairs
    # stdlib excluded by default
    ext = {e["to"] for e in data["edges"]["external"]}
    assert "libcst" in ext
    assert "os" not in ext


def test_cycles_detects_ring():
    data = run_mode("cycles", _core(EDGES))
    assert data["cycles_found"] == 1
    cycle = set(data["cycles"][0])
    assert cycle == {"pkg/sub/a.py", "pkg/sub/b.py"}


def test_cycles_clean_subtree_is_zero():
    no_cycle = [
        Edge(src="pkg/sub/a.py", kind="project", module="pkg.sub.b", target_rel="pkg/sub/b.py"),
    ]
    data = run_mode("cycles", _core(no_cycle))
    assert data["cycles_found"] == 0
    assert data["cycles"] == []


def test_structure_composition_only():
    core = _core([])
    core.structure_by_file = {
        "pkg/sub/a.py": {
            "classes": [{"name": "Foo", "line": 1, "end_line": 9, "methods": [{"name": "bar", "line": 3}]}],
            "functions": [{"name": "helper", "line": 11, "end_line": 13}],
        },
        "pkg/sub/b.py": {"classes": [], "functions": []},
    }
    data = run_mode("structure", core)
    assert data["summary"]["class_count"] == 1
    assert data["summary"]["function_count"] == 1
    assert data["summary"]["method_count"] == 1
    # composition only: no complexity / size scoring keys
    blob = str(data)
    assert "complexity" not in blob
    assert "size" not in blob


def test_verdict_classification():
    assert classify_verdict("pkg/core/file_lock.py") == "keep_in_server"
    assert classify_verdict("pkg/core/backup_manager.py") == "keep_in_server"
    assert classify_verdict("pkg/core/config.py") == "parameterize"
    assert classify_verdict("pkg/core/exceptions.py") == "pull_in"


def test_is_test_path():
    assert is_test_path("tests/test_x.py") is True
    assert is_test_path("pkg/test/helper.py") is True
    assert is_test_path("pkg/sub/test_markers.py") is True
    assert is_test_path("pkg/sub/markers_test.py") is True
    assert is_test_path("pkg/sub/markers.py") is False
    # 'test' only as a path segment, not substring of a name
    assert is_test_path("pkg/contest/markers.py") is False


def _dead_core(inputs):
    c = _core([])
    c.dead_code_inputs = inputs
    return c


def test_dead_code_classification():
    inputs = {
        "symbols": [
            # D-1 shape: prod import, no prod call, called only by tests
            {"kind": "function", "name": "append_persisted_node_ids",
             "file": "pkg/sub/markers.py", "line": 5, "class_name": None},
            {"kind": "function", "name": "build_marker_path",
             "file": "pkg/sub/markers.py", "line": 20, "class_name": None},
            {"kind": "function", "name": "orphan",
             "file": "pkg/sub/markers.py", "line": 40, "class_name": None},
            {"kind": "function", "name": "imported_never_called",
             "file": "pkg/sub/markers.py", "line": 60, "class_name": None},
        ],
        "usage_by_name": {
            "append_persisted_node_ids": ["tests/test_markers.py"],   # test only
            "build_marker_path": ["pkg/sub/other.py"],                # production
        },
        "import_by_name": {
            "append_persisted_node_ids": ["pkg/sub/tree_modifier.py", "tests/test_markers.py"],
            "imported_never_called": ["pkg/sub/consumer.py"],
        },
    }
    data = run_mode("dead_code", _dead_core(inputs))
    s = data["summary"]
    assert s["total_symbols"] == 4
    assert (s["live"], s["test_only"], s["import_only"], s["unused"]) == (1, 1, 1, 1)
    assert s["removable_count"] == 3

    by_name = {r["name"]: r["classification"] for r in data["symbols"]}
    assert by_name["build_marker_path"] == "live"
    assert by_name["append_persisted_node_ids"] == "test_only"
    assert by_name["imported_never_called"] == "import_only"
    assert by_name["orphan"] == "unused"

    # D-1: its production importer (the dead import) is surfaced
    d1 = next(r for r in data["symbols"] if r["name"] == "append_persisted_node_ids")
    assert "pkg/sub/tree_modifier.py" in d1["importers"]
    assert "build_marker_path" not in {r["name"] for r in data["removable"]}


def test_dead_code_self_file_usage_is_live():
    # A symbol used within its own (production) module is LIVE for a pre-extraction
    # gate — removing it would break the module. Safe direction, no false 'unused'.
    inputs = {
        "symbols": [
            {"kind": "function", "name": "helper", "file": "pkg/sub/a.py",
             "line": 1, "class_name": None},
        ],
        "usage_by_name": {"helper": ["pkg/sub/a.py"]},
        "import_by_name": {},
    }
    data = run_mode("dead_code", _dead_core(inputs))
    assert data["symbols"][0]["classification"] == "live"


def test_unknown_mode_raises():
    import pytest

    with pytest.raises(ValueError):
        run_mode("nope", _core([]))
