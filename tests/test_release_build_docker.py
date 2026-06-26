"""Release pipeline must publish Docker Hub image before deb references it."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_sh_runs_docker_push_by_default() -> None:
    """Verify test build sh runs docker push by default."""
    text = (REPO_ROOT / "build.sh").read_text(encoding="utf-8")
    assert (
        'release_build.sh" --skip-pypi' in text
        or "release_build.sh' --skip-pypi" in text
    )
    assert "exec" in text
    for line in text.splitlines():
        if line.strip().startswith("exec ") and "release_build.sh" in line:
            assert "--deb-only" not in line


def test_release_build_verifies_docker_hub() -> None:
    """Verify test release build verifies docker hub."""
    text = (REPO_ROOT / "scripts/release_build.sh").read_text(encoding="utf-8")
    assert "casmgr_build_and_push_docker_image" in text
    assert "casmgr_verify_docker_image_on_hub" in text
    assert "casmgr_ensure_docker_image_published" in text
    assert "--skip-docker-push" in text
    assert "Refusing to build deb" in text
