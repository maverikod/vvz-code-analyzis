"""
Tests for list_projects pagination (bug 03da8ecd, TODO cc999a7d).

Covers the cheap no-walk candidate pipeline in
``code_analysis.core.project_discovery.discover_project_candidates_in_directory``
and the paginated envelope returned by ``ListProjectsMCPCommand``.

User decision (2026-07-23): validity = immediate child of a watched directory
+ a correct ``projectid`` file, nothing else -- ``validate_no_nested_projects``
(the recursive ``os.walk``) is NOT called anywhere on this path. Directories
with no ``projectid`` file, or an unparseable one, are simply skipped -- never
an error, never noise.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List

import pytest

from code_analysis.commands.project_management_mcp_commands.list_projects import (
    ListProjectsMCPCommand,
)
from code_analysis.core import project_discovery as project_discovery_module
from code_analysis.core.project_discovery import (
    discover_project_candidates_in_directory,
    discover_projects_in_directory,
)
from mcp_proxy_adapter.commands.result import SuccessResult

_N_PLAIN_PROJECTS = 27  # + 1 "special"/pipeline + 1 deleted == 29 valid candidates


def _write_config(config_path: Path, *, mount_root: Path) -> None:
    """Write a minimal config pointing at ``mount_root`` (runtime mount-only mode)."""
    data = {
        "code_analysis": {
            "file_watcher": {"watch_mount_root": str(mount_root)},
        }
    }
    config_path.write_text(json.dumps(data), encoding="utf-8")


def _write_projectid(project_dir: Path, project_id: str, **extra: Any) -> None:
    """Create ``project_dir`` with a valid ``projectid`` file."""
    project_dir.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {"id": project_id, "description": "plain project", **extra}
    (project_dir / "projectid").write_text(
        json.dumps(payload, indent=4) + "\n", encoding="utf-8"
    )


def _build_catalog(watch_dir: Path) -> Dict[str, str]:
    """Populate ``watch_dir`` with a mixed fixture tree; return name -> project_id."""
    ids: Dict[str, str] = {}

    for i in range(_N_PLAIN_PROJECTS):
        name = f"proj_{i:02d}"
        pid = str(uuid.uuid4())
        _write_projectid(watch_dir / name, pid, description="plain project")
        ids[name] = pid

    # comment_contains fixture
    pid = str(uuid.uuid4())
    _write_projectid(
        watch_dir / "special_pipeline_project", pid, description="runs the pipeline"
    )
    ids["special_pipeline_project"] = pid

    # include_deleted fixture
    pid = str(uuid.uuid4())
    _write_projectid(
        watch_dir / "zz_deleted_project", pid, description="gone", deleted=True
    )
    ids["zz_deleted_project"] = pid

    # foreign directory with no projectid file at all -- must be silently skipped
    (watch_dir / "not_a_project").mkdir(parents=True, exist_ok=True)
    (watch_dir / "not_a_project" / "some_file.txt").write_text("x", encoding="utf-8")

    # directory with a corrupt/unparseable projectid file -- must be silently skipped
    corrupt_dir = watch_dir / "corrupt_projectid_project"
    corrupt_dir.mkdir(parents=True, exist_ok=True)
    (corrupt_dir / "projectid").write_text("{not valid json", encoding="utf-8")

    # nested projectid two levels under a valid project's own tree -- not a
    # separate project (deeper than one segment below watch_dir); used by the
    # parity test to prove no membership drift from dropping the walk.
    nested_dir = watch_dir / "proj_00" / "vendor" / "nested_pkg"
    nested_dir.mkdir(parents=True, exist_ok=True)
    (nested_dir / "projectid").write_text(
        json.dumps({"id": str(uuid.uuid4()), "description": "nested, not a project"}),
        encoding="utf-8",
    )

    return ids


@pytest.fixture()
def catalog(tmp_path: Path) -> Dict[str, Any]:
    """Build a mount-root watch dir with the mixed fixture tree; return command + ids."""
    mount = tmp_path / "watched"
    mount.mkdir()
    wid = str(uuid.uuid4())
    watch_dir = mount / wid
    watch_dir.mkdir()
    ids = _build_catalog(watch_dir)

    config_path = tmp_path / "config.json"
    _write_config(config_path, mount_root=mount)

    cmd = ListProjectsMCPCommand()
    cmd._resolve_config_path = lambda: config_path  # type: ignore[method-assign]

    return {
        "cmd": cmd,
        "watch_dir": watch_dir,
        "watch_dir_id": wid,
        "ids": ids,
        "config_path": config_path,
    }


def _all_valid_ids(ids: Dict[str, str], *, include_deleted: bool) -> set:
    """Return valid ``project_id`` set expected in listing output."""
    result = set(ids.values())
    if not include_deleted:
        result.discard(ids["zz_deleted_project"])
    return result


@pytest.mark.asyncio
async def test_default_call_returns_first_page_of_20(catalog: Dict[str, Any]) -> None:
    """Verify test default call returns first page of 20."""
    cmd = catalog["cmd"]
    result = await cmd.execute()
    assert isinstance(result, SuccessResult)
    data = result.data
    assert data["paginated"] is True
    assert data["page_size"] == 20
    assert data["block_position"] == 1
    assert len(data["projects"]) == 20
    expected_total = len(_all_valid_ids(catalog["ids"], include_deleted=False))
    assert data["total"] == expected_total
    assert data["count"] == 20
    assert data["has_more"] is True
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_page_traversal_covers_all_without_dupes_or_omissions(
    catalog: Dict[str, Any],
) -> None:
    """Verify test page traversal covers all without dupes or omissions."""
    cmd = catalog["cmd"]
    expected = _all_valid_ids(catalog["ids"], include_deleted=False)

    seen_ids: List[str] = []
    block_position = 1
    total_reported = None
    while True:
        result = await cmd.execute(page_size=20, block_position=block_position)
        assert isinstance(result, SuccessResult)
        data = result.data
        if total_reported is None:
            total_reported = data["total"]
        else:
            assert data["total"] == total_reported
        page_ids = [p["id"] for p in data["projects"]]
        seen_ids.extend(page_ids)
        if not data["has_more"]:
            break
        block_position += 1
        assert block_position < 100, "pagination did not terminate"

    assert len(seen_ids) == len(expected)
    assert set(seen_ids) == expected
    assert len(seen_ids) == len(set(seen_ids)), "duplicate project across pages"


@pytest.mark.asyncio
async def test_second_page_has_different_items_than_first(
    catalog: Dict[str, Any],
) -> None:
    """Verify test second page has different items than first."""
    cmd = catalog["cmd"]
    page1 = await cmd.execute(page_size=20, block_position=1)
    page2 = await cmd.execute(page_size=20, block_position=2)
    ids1 = {p["id"] for p in page1.data["projects"]}
    ids2 = {p["id"] for p in page2.data["projects"]}
    assert ids1.isdisjoint(ids2)
    assert len(ids2) > 0


@pytest.mark.asyncio
async def test_name_contains_filter_applies_before_pagination(
    catalog: Dict[str, Any],
) -> None:
    """Verify test name contains filter applies before pagination."""
    cmd = catalog["cmd"]
    result = await cmd.execute(name_contains="special_pipeline", page_size=5)
    assert isinstance(result, SuccessResult)
    data = result.data
    assert data["total"] == 1
    assert data["count"] == 1
    assert data["has_more"] is False
    assert data["projects"][0]["id"] == catalog["ids"]["special_pipeline_project"]


@pytest.mark.asyncio
async def test_comment_contains_filter_applies_before_pagination(
    catalog: Dict[str, Any],
) -> None:
    """Verify test comment contains filter applies before pagination."""
    cmd = catalog["cmd"]
    result = await cmd.execute(comment_contains="pipeline")
    assert isinstance(result, SuccessResult)
    data = result.data
    assert data["total"] == 1
    assert data["projects"][0]["id"] == catalog["ids"]["special_pipeline_project"]


@pytest.mark.asyncio
async def test_include_deleted_changes_total_across_pages(
    catalog: Dict[str, Any],
) -> None:
    """Verify test include deleted changes total across pages."""
    cmd = catalog["cmd"]
    without = await cmd.execute(page_size=1)
    with_deleted = await cmd.execute(page_size=1, include_deleted=True)
    assert with_deleted.data["total"] == without.data["total"] + 1


@pytest.mark.asyncio
async def test_foreign_and_corrupt_directories_are_silently_skipped(
    catalog: Dict[str, Any],
) -> None:
    """Directories without projectid, or with a corrupt one, never appear or error."""
    cmd = catalog["cmd"]
    result = await cmd.execute(include_deleted=True, page_size=200)
    assert isinstance(result, SuccessResult)
    names = {p["name"] for p in result.data["projects"]}
    assert "not_a_project" not in names
    assert "corrupt_projectid_project" not in names
    # every valid id (including deleted) is present, catalog membership unaffected
    assert {p["id"] for p in result.data["projects"]} == set(catalog["ids"].values())


@pytest.mark.asyncio
async def test_no_recursive_nested_validation_runs_on_any_page(
    catalog: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """validate_no_nested_projects (the recursive os.walk) must never be called."""
    calls: List[Any] = []
    original = project_discovery_module.validate_no_nested_projects

    def _counting(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(
        project_discovery_module, "validate_no_nested_projects", _counting
    )

    cmd = catalog["cmd"]
    await cmd.execute(page_size=20, block_position=1)
    await cmd.execute(page_size=20, block_position=2)
    await cmd.execute(include_deleted=True, page_size=200)

    assert len(calls) == 0, (
        "list_projects must never invoke the recursive nested-project walk "
        f"(user decision 2026-07-23); got {len(calls)} call(s)"
    )


@pytest.mark.asyncio
async def test_load_project_info_called_at_most_once_per_candidate(
    catalog: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cheap pass must not double-read any candidate's projectid file."""
    from code_analysis.core import project_resolution as project_resolution_module

    calls: List[str] = []
    original = project_resolution_module.load_project_info

    def _counting(root_dir: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(str(root_dir))
        return original(root_dir, *args, **kwargs)

    monkeypatch.setattr(project_resolution_module, "load_project_info", _counting)

    cmd = catalog["cmd"]
    result = await cmd.execute(include_deleted=True, page_size=200)
    assert isinstance(result, SuccessResult)

    # One read per real projectid file (valid ones only; corrupt one is read once
    # too, to discover it is invalid, then skipped). Never more than once each.
    from collections import Counter

    counts = Counter(calls)
    assert all(c <= 1 for c in counts.values()), (
        f"duplicate load_project_info reads detected: "
        f"{[k for k, v in counts.items() if v > 1]}"
    )


@pytest.mark.asyncio
async def test_envelope_shape_mirrors_list_files(catalog: Dict[str, Any]) -> None:
    """Verify test envelope shape mirrors list files."""
    cmd = catalog["cmd"]
    result = await cmd.execute(page_size=5)
    data = result.data
    expected_keys = {
        "success",
        "paginated",
        "items",
        "projects",
        "count",
        "total",
        "page_size",
        "block_position",
        "has_more",
        "offset",
    }
    assert expected_keys <= set(data.keys())
    assert data["items"] == data["projects"]


@pytest.mark.asyncio
async def test_legacy_no_param_call_still_has_projects_key(
    catalog: Dict[str, Any],
) -> None:
    """Verify test legacy no param call still has projects key."""
    cmd = catalog["cmd"]
    result = await cmd.execute()
    assert "projects" in result.data
    assert isinstance(result.data["projects"], list)


def test_candidate_discovery_matches_full_walker_membership(
    catalog: Dict[str, Any],
) -> None:
    """Parity: the cheap candidate pass and the full walker-facing discovery
    (still used unchanged by watcher startup reconciliation /
    delete_unwatched_projects_command) must agree on which project_ids are
    members of the watch dir.

    Proves dropping ``validate_no_nested_projects`` from the listing path does
    not add previously-excluded entries nor drop previously-included ones: the
    nested ``projectid`` planted two levels inside ``proj_00`` is excluded by
    BOTH functions (it is not an immediate child of the watch dir), and every
    other membership rule (foreign dir skipped, corrupt projectid skipped)
    behaves identically in both.
    """
    watch_dir = catalog["watch_dir"]

    candidates = discover_project_candidates_in_directory(watch_dir)
    full = discover_projects_in_directory(watch_dir)

    candidate_ids = {p.project_id for p in candidates}
    full_ids = {p.project_id for p in full}

    assert candidate_ids == full_ids
    assert candidate_ids == set(catalog["ids"].values())

    nested_id_path = watch_dir / "proj_00" / "vendor" / "nested_pkg" / "projectid"
    nested_id = json.loads(nested_id_path.read_text(encoding="utf-8"))["id"]
    assert nested_id not in candidate_ids
    assert nested_id not in full_ids
