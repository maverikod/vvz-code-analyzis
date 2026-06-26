"""Tests for Docker watch directory path layout (/watched/{uuid})."""

from __future__ import annotations

import pytest

from code_analysis.core.docker_watch_paths import (
    docker_watch_dir_container_path,
    validate_docker_watch_dir_entry,
)
from code_analysis.core.file_watcher_pkg.multi_project_worker_specs import (
    build_watch_dir_specs,
)


def test_container_path_uses_uuid() -> None:
    """Verify test container path uses uuid."""
    wid = "a6c47e01-1ac8-47a6-a0e8-e6416086de0c"
    assert (
        docker_watch_dir_container_path(wid)
        == "/watched/a6c47e01-1ac8-47a6-a0e8-e6416086de0c"
    )


def test_validate_matching_path_ok() -> None:
    """Verify test validate matching path ok."""
    wid = "a6c47e01-1ac8-47a6-a0e8-e6416086de0c"
    assert validate_docker_watch_dir_entry(wid, f"/watched/{wid}") is None
    assert validate_docker_watch_dir_entry(wid, f"/watched/{wid}/") is None


def test_validate_mismatch_path_errors() -> None:
    """Verify test validate mismatch path errors."""
    wid = "a6c47e01-1ac8-47a6-a0e8-e6416086de0c"
    err = validate_docker_watch_dir_entry(wid, "/watched/other-name")
    assert err is not None
    assert "must equal" in err


def test_host_path_not_validated() -> None:
    """Verify test host path not validated."""
    wid = "a6c47e01-1ac8-47a6-a0e8-e6416086de0c"
    assert validate_docker_watch_dir_entry(wid, "/home/user/tools") is None


def test_build_specs_rejects_docker_path_mismatch(tmp_path) -> None:
    """Verify test build specs rejects docker path mismatch."""
    wid = "11111111-1111-1111-1111-111111111111"
    with pytest.raises(ValueError, match="must equal"):
        build_watch_dir_specs(
            [{"id": wid, "path": "/watched/wrong-uuid"}],
        )


def test_build_specs_accepts_docker_path_match(tmp_path) -> None:
    """Verify test build specs accepts docker path match."""
    wid = "22222222-2222-2222-2222-222222222222"
    specs = build_watch_dir_specs([{"id": wid, "path": f"/watched/{wid}"}])
    assert len(specs) == 1
    assert str(specs[0].watch_dir).endswith(wid)
