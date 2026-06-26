"""Tests for TLS material validation across all certificate config sections."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_analysis.core.config_models import SVOServiceConfig
from code_analysis.core.config_validator import CodeAnalysisConfigValidator
from code_analysis.core.tls_material_validation import (
    iter_tls_material_blocks,
    validate_crl_against_ca_or_system,
    validate_tls_material_block,
)
from tests.test_config_driver_helpers import (
    create_crl_for_ca,
    create_dummy_ssl_certs_in_dir,
    create_mismatched_key_pair,
)


def _base_config(tmp_path: Path) -> dict:
    """Return base config."""
    create_dummy_ssl_certs_in_dir(tmp_path)

    def rel(name: str) -> str:
        """Return rel."""
        return str((tmp_path / name).resolve())

    return {
        "server": {
            "host": "127.0.0.1",
            "port": 15000,
            "protocol": "https",
            "ssl": {
                "cert": rel("server.crt"),
                "key": rel("server.key"),
                "ca": rel("ca.crt"),
            },
        },
        "queue_manager": {"enabled": True},
        "code_analysis": {
            "chunker": {
                "enabled": True,
                "protocol": "https",
                "cert_file": rel("server.crt"),
                "key_file": rel("server.key"),
                "ca_cert_file": rel("ca.crt"),
            },
            "embedding": {
                "enabled": True,
                "protocol": "https",
                "cert_file": rel("server.crt"),
                "key_file": rel("server.key"),
                "ca_cert_file": rel("ca.crt"),
            },
        },
    }


def test_iter_tls_material_blocks_finds_all_sections(tmp_path: Path) -> None:
    """Verify test iter tls material blocks finds all sections."""
    config = _base_config(tmp_path)
    config["client"] = {
        "enabled": False,
        "protocol": "https",
        "ssl": {
            "cert": str((tmp_path / "server.crt").resolve()),
            "key": str((tmp_path / "server.key").resolve()),
        },
    }
    blocks = list(iter_tls_material_blocks(config))
    sections = {b.section for b in blocks}
    assert "server" in sections
    assert "client" in sections
    assert "code_analysis" in sections
    assert sum(1 for b in blocks if b.key_prefix == "chunker.") == 1
    assert sum(1 for b in blocks if b.key_prefix == "embedding.") == 1


def test_cert_without_key_reports_error(tmp_path: Path) -> None:
    """Verify test cert without key reports error."""
    config = _base_config(tmp_path)
    config["server"]["ssl"].pop("key")
    block = next(iter_tls_material_blocks(config))
    findings = validate_tls_material_block(block, tmp_path)
    assert any("key" in msg for _, msg, _ in findings)


def test_key_without_cert_reports_error(tmp_path: Path) -> None:
    """Verify test key without cert reports error."""
    config = _base_config(tmp_path)
    config["code_analysis"]["chunker"].pop("cert_file")
    block = next(
        b for b in iter_tls_material_blocks(config) if b.key_prefix == "chunker."
    )
    findings = validate_tls_material_block(block, tmp_path)
    assert any("cert_file" in key for _, _, key in findings if key)


def test_mismatched_cert_key_reports_error(tmp_path: Path) -> None:
    """Verify test mismatched cert key reports error."""
    create_dummy_ssl_certs_in_dir(tmp_path)
    cert_path, key_path = create_mismatched_key_pair(tmp_path)
    config = _base_config(tmp_path)
    config["server"]["ssl"]["cert"] = str(cert_path.resolve())
    config["server"]["ssl"]["key"] = str(key_path.resolve())
    block = next(b for b in iter_tls_material_blocks(config) if b.section == "server")
    findings = validate_tls_material_block(block, tmp_path)
    assert any("does not match" in msg for _, msg, _ in findings)


def test_crl_signed_by_configured_ca_passes(tmp_path: Path) -> None:
    """Verify test crl signed by configured ca passes."""
    create_dummy_ssl_certs_in_dir(tmp_path)
    crl_path = create_crl_for_ca(tmp_path)
    ca_path = tmp_path / "ca.crt"
    ok, err = validate_crl_against_ca_or_system(crl_path, ca_path)
    assert ok, err


def test_crl_not_signed_by_wrong_ca_fails(tmp_path: Path) -> None:
    """Verify test crl not signed by wrong ca fails."""
    create_dummy_ssl_certs_in_dir(tmp_path)
    crl_path = create_crl_for_ca(tmp_path)
    # Second CA not used to sign the CRL
    subprocess = __import__("subprocess")
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(tmp_path / "other-ca.key"),
            "-out",
            str(tmp_path / "other-ca.crt"),
            "-days",
            "1",
            "-nodes",
            "-subj",
            "/CN=OtherCA",
        ],
        check=True,
        capture_output=True,
    )
    ok, err = validate_crl_against_ca_or_system(crl_path, tmp_path / "other-ca.crt")
    assert not ok
    assert err is not None
    assert "configured CA" in err


def test_validator_checks_all_ssl_sections(tmp_path: Path) -> None:
    """Verify test validator checks all ssl sections."""
    config = _base_config(tmp_path)
    crl_path = create_crl_for_ca(tmp_path)
    rel_crl = str(crl_path.resolve())
    config["server"]["ssl"]["crl"] = rel_crl
    config["client"] = {
        "enabled": False,
        "protocol": "https",
        "ssl": {
            "cert": config["server"]["ssl"]["cert"],
            "key": config["server"]["ssl"]["key"],
            "ca": config["server"]["ssl"]["ca"],
            "crl": rel_crl,
        },
    }
    config["registration"] = {
        "enabled": False,
        "protocol": "https",
        "ssl": {
            "cert": config["server"]["ssl"]["cert"],
            "key": config["server"]["ssl"]["key"],
            "ca": config["server"]["ssl"]["ca"],
        },
    }
    config["server_validation"] = {
        "enabled": False,
        "protocol": "https",
        "ssl": {
            "cert": config["server"]["ssl"]["cert"],
            "key": config["server"]["ssl"]["key"],
            "ca": config["server"]["ssl"]["ca"],
        },
    }
    config["code_analysis"]["chunker"]["crl_file"] = rel_crl
    config["code_analysis"]["embedding"]["crl_file"] = rel_crl

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config), encoding="utf-8")
    validator = CodeAnalysisConfigValidator(str(config_file))
    validator.load_config()
    results = validator.validate_config()
    tls_errors = [r for r in results if r.key and ("cert" in r.key or "crl" in r.key)]
    assert not tls_errors, [r.message for r in tls_errors]


def test_svo_service_config_cert_key_pairing(tmp_path: Path) -> None:
    """Verify test svo service config cert key pairing."""
    create_dummy_ssl_certs_in_dir(tmp_path)
    SVOServiceConfig(
        enabled=True,
        protocol="https",
        cert_file=str((tmp_path / "server.crt").resolve()),
        key_file=str((tmp_path / "server.key").resolve()),
    )
    with pytest.raises(ValueError, match="key_file"):
        SVOServiceConfig(
            enabled=True,
            protocol="https",
            cert_file=str((tmp_path / "server.crt").resolve()),
        )


def test_svo_service_config_crl_against_ca(tmp_path: Path) -> None:
    """Verify test svo service config crl against ca."""
    create_dummy_ssl_certs_in_dir(tmp_path)
    crl_path = create_crl_for_ca(tmp_path)
    SVOServiceConfig(
        enabled=True,
        protocol="https",
        cert_file=str((tmp_path / "server.crt").resolve()),
        key_file=str((tmp_path / "server.key").resolve()),
        ca_cert_file=str((tmp_path / "ca.crt").resolve()),
        crl_file=str(crl_path.resolve()),
    )
