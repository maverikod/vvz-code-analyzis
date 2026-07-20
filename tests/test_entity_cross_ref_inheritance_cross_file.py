"""
Regression: entity_cross_ref inheritance edges resolve cross-file, independent
of which file a batch reindex (``update_indexes``) happens to process first
(follow-up to card ac831d35 / commit 3fbfa07d, refuted by live verification
on deployed 1.6.60: get_entity_dependents(class, BaseMCPCommand) stayed empty
after re-analyzing all 17 child files AND base_mcp_command.py on ai-editor).

Mechanism (confirmed by reading entity_cross_ref_builder.py and by direct
reproduction below): ``update_indexes`` walks a project's files in a fixed
SORTED order (``collect_python_files_for_indexing``: "Ordering: sorted merged
set."), not a dependency-aware order. The pre-fix
``_add_inheritance_cross_ref_for_file`` only resolved a class's OWN bases
against whatever already existed in the DB at that instant ("forward"
resolution) - when a child's file was (re)indexed BEFORE its base class
existed in the DB (a real possibility for any of the 17 files sorting before
"base_mcp_command.py"), the edge was silently skipped and nothing ever
revisited that child once the base class was indexed later in the same run.
Note this refutes the literal claim that project-wide cross-file resolution
was impossible: resolve_callee's SQL was already project-scoped (not
file-scoped) and correctly resolves an ALREADY-PRESENT cross-file base (see
test_entity_cross_ref_builder_inheritance.py and
test_cross_file_both_already_indexed_single_build_call below, which already
passed before this fix) - the real defect is the one-directional, order-
dependent nature of the resolution, fixed here by adding a backfill pass.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import uuid

import pytest

from tests.sqlite_in_process_legacy_facade import make_sqlite_in_process_legacy_facade

from code_analysis.commands.ast.entity_dependencies_helpers import (
    get_entity_dependents_via_execute,
)
from code_analysis.core.entity_cross_ref_builder import build_entity_cross_ref_for_file


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


def _insert_project(test_db, tmp_path, project_id):
    """Insert a project row."""
    test_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(tmp_path), tmp_path.name),
    )
    test_db._commit()


def _insert_file(test_db, project_id, tmp_path, name):
    """Insert a files row and return its id."""
    file_id = str(uuid.uuid4())
    test_db._execute(
        """INSERT INTO files (id, project_id, path, relative_path, lines, last_modified, has_docstring)
           VALUES (?, ?, ?, ?, 0, 0, 0)""",
        (file_id, project_id, str(tmp_path / name), name),
    )
    test_db._commit()
    return file_id


def _insert_class(test_db, file_id, name, bases_json):
    """Insert a classes row and return its id."""
    class_id = str(uuid.uuid4())
    test_db._execute(
        "INSERT INTO classes (id, file_id, name, line, end_line, docstring, bases, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (class_id, file_id, name, 1, 2, None, bases_json, str(uuid.uuid4())),
    )
    test_db._commit()
    return class_id


def test_cross_file_child_reindexed_before_base_class_exists_is_backfilled(
    test_db, tmp_path, project_id
):
    """The real production failure mode: child file's cross-ref build runs
    BEFORE its base class file has been indexed (a plausible outcome of
    update_indexes's fixed sorted file order, unrelated to any true topological
    dependency). Once the base class's OWN file is (re)indexed, the child's
    edge must appear WITHOUT re-touching the child's file - this is the
    scenario that reproduces the live get_entity_dependents([]) symptom.
    """
    _insert_project(test_db, tmp_path, project_id)

    # File B: Child(BaseMCPCommand) - processed FIRST; the base class does not
    # exist in the DB yet (matches "sorts before its base file" in a batch run).
    file_b = _insert_file(test_db, project_id, tmp_path, "child_command.py")
    child_id = _insert_class(test_db, file_b, "ChildCommand", '["BaseMCPCommand"]')

    added_first_pass = build_entity_cross_ref_for_file(test_db, file_b, project_id, "")
    assert added_first_pass == 0, "base class does not exist yet - nothing to add"

    # File A: base_mcp_command.py - processed SECOND (later in the same batch).
    file_a = _insert_file(test_db, project_id, tmp_path, "base_mcp_command.py")
    parent_id = _insert_class(test_db, file_a, "BaseMCPCommand", "[]")

    build_entity_cross_ref_for_file(test_db, file_a, project_id, "")

    # Nothing re-touched child_command.py; the edge must still be discoverable.
    dependents = get_entity_dependents_via_execute(test_db, "class", parent_id)
    assert len(dependents) == 1, (
        "expected ChildCommand to surface as a dependent of BaseMCPCommand "
        f"once base_mcp_command.py is indexed, regardless of batch order; got {dependents!r}"
    )
    assert dependents[0]["caller_entity_id"] == child_id
    assert dependents[0]["ref_type"] == "inherit"


def test_cross_file_both_already_indexed_single_build_call(
    test_db, tmp_path, project_id
):
    """Baseline sanity check (already passed before this fix): when the base
    class is ALREADY indexed and only the child's file is (re)built, the edge
    resolves in one pass - project-wide class lookup was never file-scoped.
    """
    _insert_project(test_db, tmp_path, project_id)

    file_a = _insert_file(test_db, project_id, tmp_path, "base_mcp_command.py")
    parent_id = _insert_class(test_db, file_a, "BaseMCPCommand", "[]")

    file_b = _insert_file(test_db, project_id, tmp_path, "child_command.py")
    child_id = _insert_class(test_db, file_b, "ChildCommand", '["BaseMCPCommand"]')

    build_entity_cross_ref_for_file(test_db, file_b, project_id, "")

    dependents = get_entity_dependents_via_execute(test_db, "class", parent_id)
    assert len(dependents) == 1
    assert dependents[0]["caller_entity_id"] == child_id


def test_ambiguous_base_name_across_files_is_skipped_not_guessed(
    test_db, tmp_path, project_id
):
    """Two unrelated classes share the base's simple name in different files -
    resolution must skip (not silently bind to the wrong one), per the
    documented "unique name in project, else skip" convention.
    """
    _insert_project(test_db, tmp_path, project_id)

    file_a = _insert_file(test_db, project_id, tmp_path, "a.py")
    _insert_class(test_db, file_a, "Base", "[]")

    file_c = _insert_file(test_db, project_id, tmp_path, "c.py")
    _insert_class(test_db, file_c, "Base", "[]")  # unrelated same-named class

    file_b = _insert_file(test_db, project_id, tmp_path, "b.py")
    _insert_class(test_db, file_b, "Child", '["Base"]')

    added = build_entity_cross_ref_for_file(test_db, file_b, project_id, "")

    assert added == 0
    rows = test_db._fetchall(
        "SELECT * FROM entity_cross_ref WHERE ref_type = 'inherit'", ()
    )
    assert rows == []
