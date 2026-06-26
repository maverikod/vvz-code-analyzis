"""Tests for casmgr-install-server-config (debian postinst config policy)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from code_analysis.core.config_json import load_config_json

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_CONFIG = REPO_ROOT / "packaging" / "bin" / "casmgr-install-server-config"
TEMPLATE = REPO_ROOT / "packaging" / "config.json.template"


def _run_install_config(etc_dir: Path) -> subprocess.CompletedProcess[str]:
    """Return run install config."""
    doc_template = etc_dir / "doc" / "config.json.template"
    doc_template.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(TEMPLATE, doc_template)
    return subprocess.run(
        ["bash", str(INSTALL_CONFIG), str(etc_dir), str(doc_template), "casgrp"],
        check=True,
        capture_output=True,
        text=True,
    )


def test_install_config_creates_config_when_missing(tmp_path: Path) -> None:
    """Verify test install config creates config when missing."""
    etc = tmp_path / "etc" / "casmgr"
    result = _run_install_config(etc)
    config = etc / "config.json"
    assert config.is_file()
    assert "Installed new" in result.stdout
    data = load_config_json(config)
    uuid = data["registration"]["instance_uuid"]
    assert uuid != "REPLACE_ON_INSTALL"
    assert not (etc / "config.json.template").exists()


def test_install_config_preserves_existing_and_writes_template_beside(
    tmp_path: Path,
) -> None:
    """Verify test install config preserves existing and writes template beside."""
    etc = tmp_path / "etc" / "casmgr"
    etc.mkdir(parents=True)
    existing = etc / "config.json"
    existing.write_text('{"keep": true}\n', encoding="utf-8")
    before = existing.read_text(encoding="utf-8")

    result = _run_install_config(etc)

    assert existing.read_text(encoding="utf-8") == before
    assert (etc / "config.json.template").is_file()
    assert "Preserved existing" in result.stdout


def test_install_config_finalizes_pristine_package_config(tmp_path: Path) -> None:
    """Verify test install config finalizes pristine package config."""
    etc = tmp_path / "etc" / "casmgr"
    etc.mkdir(parents=True)
    shutil.copy(TEMPLATE, etc / "config.json")

    result = _run_install_config(etc)

    data = load_config_json(etc / "config.json")
    assert data["registration"]["instance_uuid"] != "REPLACE_ON_INSTALL"
    assert not (etc / "config.json.template").exists()
    assert "Finalized new" in result.stdout


def test_install_config_accepts_gzipped_doc_template(tmp_path: Path) -> None:
    """Verify test install config accepts gzipped doc template."""
    import gzip

    etc = tmp_path / "etc" / "casmgr"
    etc.mkdir(parents=True)
    existing = etc / "config.json"
    existing.write_text('{"keep": true}\n', encoding="utf-8")

    doc_dir = etc / "doc"
    doc_dir.mkdir()
    gz_path = doc_dir / "config.json.template.gz"
    with gzip.open(gz_path, "wb") as fh:
        fh.write(TEMPLATE.read_bytes())

    result = subprocess.run(
        [
            "bash",
            str(INSTALL_CONFIG),
            str(etc),
            str(doc_dir / "config.json.template"),
            "casgrp",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert existing.read_text(encoding="utf-8") == '{"keep": true}\n'
    assert (etc / "config.json.template").is_file()
    assert "Preserved existing" in result.stdout
    load_config_json(etc / "config.json.template")
