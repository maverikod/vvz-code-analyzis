"""Ensure production config template matches deb install expectations."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from code_analysis.core.config_json import load_config_json
from code_analysis.core.docs_indexing_defaults import default_docs_indexing_dict
from code_analysis.core.search_session.policy import (
    SEARCH_MAX_BLOCK_SIZE_BYTES_DEFAULT,
    SEARCH_SESSION_TTL_SECONDS_DEFAULT,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPO_ROOT / "packaging" / "config.json.template"
INSTALL_SCRIPT = REPO_ROOT / "debian" / "install-package.sh"


def test_packaging_template_file_exists() -> None:
    assert TEMPLATE_PATH.is_file(), f"missing canonical template: {TEMPLATE_PATH}"


def test_packaging_template_production_shape() -> None:
    data = load_config_json(TEMPLATE_PATH)
    server = data["server"]
    assert server["port"] == 15010
    assert server["servername"] == "code-analysis-server"
    assert server["log_dir"] == "/var/log/casmgr"
    assert server["ssl"]["cert"].startswith("/etc/casmgr/mtls/")

    registration = data["registration"]
    assert registration["server_id"] == "code-analysis-server"
    assert registration["instance_uuid"] == "REPLACE_ON_INSTALL"
    assert "MCP_PROXY_HOST" in registration["register_url"]

    ca = data["code_analysis"]
    assert ca["port"] == 15010
    storage = ca["storage"]
    assert storage["db_path"] == "/var/casmgr/data/code_analysis.db"
    assert storage["faiss_dir"] == "/var/casmgr/faiss"

    driver = ca["database"]["driver"]
    assert driver["type"] == "postgres"
    assert driver["config"]["password_env"] == "CODE_ANALYSIS_POSTGRES_PASSWORD"

    rpc = ca["database"]["rpc"]
    assert rpc["shm_enabled"] is True
    assert rpc["shm_threshold_bytes"] == 65536

    assert ca["docs_indexing"] == default_docs_indexing_dict()
    assert ca["search_session"] == {
        "ttl_seconds": SEARCH_SESSION_TTL_SECONDS_DEFAULT,
        "max_block_size_bytes": SEARCH_MAX_BLOCK_SIZE_BYTES_DEFAULT,
    }


def test_install_package_script_uses_packaging_template() -> None:
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert "packaging/config.json.template" in text
    assert "/usr/share/doc/casmgr-server/config.json.template" in text
    assert "/etc/casmgr/config.json" in text


@pytest.mark.parametrize(
    "staging_rel,mode",
    [
        ("etc/casmgr/config.json", "640"),
        ("usr/share/doc/casmgr-server/config.json.template", "644"),
    ],
)
def test_debian_staging_installs_same_template(staging_rel: str, mode: str) -> None:
    staging_root = REPO_ROOT / "debian" / "casmgr-server"
    try:
        subprocess.run(
            ["bash", str(INSTALL_SCRIPT), str(REPO_ROOT)],
            check=True,
            cwd=REPO_ROOT,
        )
        staged = staging_root / staging_rel
        assert staged.is_file(), staging_rel
        assert oct(staged.stat().st_mode & 0o777) == oct(int(mode, 8))
        assert staged.read_text(encoding="utf-8") == TEMPLATE_PATH.read_text(
            encoding="utf-8"
        )
        load_config_json(staged)
    finally:
        if staging_root.is_dir():
            import shutil

            shutil.rmtree(staging_root, ignore_errors=True)
