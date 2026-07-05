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
    """Verify test packaging template file exists."""
    assert TEMPLATE_PATH.is_file(), f"missing canonical template: {TEMPLATE_PATH}"


def test_packaging_template_production_shape() -> None:
    """Verify test packaging template production shape."""
    data = load_config_json(TEMPLATE_PATH)
    server = data["server"]
    assert server["port"] == 15010
    assert server["servername"] == "code-analysis-server"
    assert server["log_dir"] == "/var/log/casmgr"
    assert server["ssl"]["cert"].startswith("/etc/casmgr/mtls/")

    registration = data["registration"]
    assert registration["server_id"] == "code-analysis-server-vvz"
    assert registration["instance_uuid"] == "REPLACE_ON_INSTALL"
    assert registration["register_url"] == "https://172.18.0.1:3004/register"

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
    """Verify test install package script uses packaging template."""
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert "packaging/config.json.template" in text
    assert "/usr/share/casmgr-server/config.json.template" in text
    assert (
        "${ST}/etc/casmgr/config.json" in text
        or '"${ST}/etc/casmgr/config.json"' in text
        or "${ST}/etc/casmgr/config.json" in text
    )


@pytest.mark.parametrize(
    "staging_rel,mode",
    [
        ("etc/casmgr/config.json", "640"),
        ("usr/share/casmgr-server/config.json.template", "644"),
    ],
)
def test_debian_staging_installs_config_and_runtime_template(
    staging_rel: str, mode: str
) -> None:
    """Verify test debian staging installs config and runtime template."""
    staging_root = REPO_ROOT / "debian" / "casmgr-server"
    try:
        if staging_root.is_dir():
            import shutil

            shutil.rmtree(staging_root, ignore_errors=True)
        subprocess.run(
            ["bash", str(INSTALL_SCRIPT), str(REPO_ROOT)],
            check=True,
            cwd=REPO_ROOT,
        )
        staged = staging_root / staging_rel
        assert staged.is_file(), staging_rel
        assert oct(staged.stat().st_mode & 0o777) == oct(int(mode, 8))
        # The staged config is now STRICT JSON (comments stripped from the JSONC
        # source template): /etc/casmgr/config.json is read not only by the app's
        # commentjson-tolerant loader but also by mcp_proxy_adapter's eager
        # import-time json.load, which rejects comments and would crash-loop the
        # daemon (with 40-casmgr/run's `cd /etc/casmgr`). So it must parse with the
        # plain stdlib json loader and be semantically identical to the template.
        import json

        staged_text = staged.read_text(encoding="utf-8")
        staged_data = json.loads(staged_text)  # strict: no comment support
        assert staged_data == load_config_json(TEMPLATE_PATH)
        assert not any(
            line.lstrip().startswith(("#", "//"))
            for line in staged_text.splitlines()
        )
    finally:
        if staging_root.is_dir():
            import shutil

            shutil.rmtree(staging_root, ignore_errors=True)
