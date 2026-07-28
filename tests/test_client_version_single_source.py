"""
Tests for single-source casmgr Docker image resolution in info_command.py
(recovered from casmgr:1.6.87 image, built from an uncommitted tree).

Precedence under test (highest to lowest):
    1. CASMGR_IMAGE_REF env var (used verbatim).
    2. The on-disk docker-image marker file, but only when its tag matches the
       expected version (CASMGR_VERSION env, else the running package version).
    3. The canonical ``vasilyvz/casmgr:<version>`` computed from that same
       expected version.
    4. ``None`` when no version is known at all.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

import pytest

import code_analysis.commands.info_command as info_module


def _no_marker_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point every docker-image marker candidate at a nonexistent path."""
    monkeypatch.setattr(
        info_module,
        "DOCKER_IMAGE_PATH_CANDIDATES",
        [tmp_path / "no-such-docker-image-marker"],
    )


def _marker_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, content: str) -> Path:
    """Write one docker-image marker candidate file and wire it as the only candidate."""
    marker = tmp_path / "docker-image"
    marker.write_text(content + "\n", encoding="utf-8")
    monkeypatch.setattr(info_module, "DOCKER_IMAGE_PATH_CANDIDATES", [marker])
    return marker


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CASMGR_IMAGE_REF", raising=False)
    monkeypatch.delenv("CASMGR_VERSION", raising=False)


class TestDockerRefTag:
    """_docker_ref_tag: extract the tag component from an image reference."""

    def test_extracts_tag(self) -> None:
        assert info_module._docker_ref_tag("vasilyvz/casmgr:1.6.87") == "1.6.87"

    def test_no_colon_returns_none(self) -> None:
        assert info_module._docker_ref_tag("vasilyvz/casmgr") is None

    def test_empty_string_returns_none(self) -> None:
        assert info_module._docker_ref_tag("") is None

    def test_trailing_colon_returns_none(self) -> None:
        assert info_module._docker_ref_tag("vasilyvz/casmgr:") is None


class TestDefaultDockerImageRef:
    """_default_docker_image_ref: build the canonical repo:tag for a version."""

    def test_builds_canonical_ref(self) -> None:
        assert (
            info_module._default_docker_image_ref("1.6.87")
            == "vasilyvz/casmgr:1.6.87"
        )

    def test_unknown_version_returns_none(self) -> None:
        assert info_module._default_docker_image_ref("unknown") is None

    def test_empty_version_returns_none(self) -> None:
        assert info_module._default_docker_image_ref("") is None


class TestResolveRuntimeDockerImage:
    """_resolve_runtime_docker_image: env-first precedence chain."""

    def test_env_image_ref_wins_over_everything(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CASMGR_IMAGE_REF is used verbatim even when a marker file disagrees."""
        _marker_file(monkeypatch, tmp_path, "vasilyvz/casmgr:9.9.9")
        monkeypatch.setenv("CASMGR_IMAGE_REF", "myregistry/casmgr:override")

        assert (
            info_module._resolve_runtime_docker_image("1.6.87")
            == "myregistry/casmgr:override"
        )

    def test_marker_file_used_when_tag_matches_version(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The marker file wins when its tag matches the running version."""
        _clear_env(monkeypatch)
        _marker_file(monkeypatch, tmp_path, "vasilyvz/casmgr:1.6.87")

        assert (
            info_module._resolve_runtime_docker_image("1.6.87")
            == "vasilyvz/casmgr:1.6.87"
        )

    def test_marker_file_ignored_when_tag_stale(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A stale marker file (old tag) is rejected in favor of the canonical ref."""
        _clear_env(monkeypatch)
        _marker_file(monkeypatch, tmp_path, "vasilyvz/casmgr:1.6.6")

        assert (
            info_module._resolve_runtime_docker_image("1.6.87")
            == "vasilyvz/casmgr:1.6.87"
        )

    def test_canonical_ref_used_when_no_marker_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No marker file at all falls back to the canonical repo:version ref."""
        _clear_env(monkeypatch)
        _no_marker_file(monkeypatch, tmp_path)

        assert (
            info_module._resolve_runtime_docker_image("1.6.87")
            == "vasilyvz/casmgr:1.6.87"
        )

    def test_casmgr_version_env_overrides_expected_tag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CASMGR_VERSION (not the package version) drives the expected tag/canonical ref."""
        _clear_env(monkeypatch)
        monkeypatch.setenv("CASMGR_VERSION", "2.0.0")
        _marker_file(monkeypatch, tmp_path, "vasilyvz/casmgr:2.0.0")

        assert (
            info_module._resolve_runtime_docker_image("1.6.87")
            == "vasilyvz/casmgr:2.0.0"
        )

    def test_unknown_version_and_no_marker_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No env, no marker file, and an unresolvable version yields no image ref."""
        _clear_env(monkeypatch)
        _no_marker_file(monkeypatch, tmp_path)

        assert info_module._resolve_runtime_docker_image("unknown") is None


class TestRuntimePackageInfoWiring:
    """_runtime_package_info: the single version lookup feeds both fields."""

    def test_docker_image_uses_resolved_runtime_image(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """docker_image comes from _resolve_runtime_docker_image, not a separate read."""
        _clear_env(monkeypatch)
        monkeypatch.setattr(
            info_module, "_safe_distribution_version", lambda _name: "1.6.87"
        )
        _no_marker_file(monkeypatch, tmp_path)

        info = info_module._runtime_package_info(source={"path": None})

        assert info["version"] == "1.6.87"
        assert info["docker_image"] == "vasilyvz/casmgr:1.6.87"
