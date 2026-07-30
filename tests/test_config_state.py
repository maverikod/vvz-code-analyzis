"""
Tests for the per-path config validation cache (bug 8e6acb34 component B).

``revalidate_config_at_path`` used to re-parse and re-validate ``config.json`` on
EVERY call -- including 8 RSA ``load_pem_private_key`` calls inside the TLS
material validator -- regardless of whether the file had changed since the last
call. These tests exercise the REAL validator (real self-signed cert/key on disk,
``protocol: "https"``) so a passing cache-hit assertion actually proves the RSA
parses were skipped, not merely that some mocked stand-in was skipped. They pin
the caching contract: an unchanged file is served from the in-process cache (no
re-parse/re-validate), an mtime/size change forces a fresh validation, and a
failed validation is cached as its own outcome, never coerced into a stale
success.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import datetime
import json
import os
import time
from pathlib import Path
from typing import Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from code_analysis.core.config_state import (
    get_config_runtime_state,
    get_config_validation_cache_diagnostics,
    is_config_valid,
    reset_config_validation_cache,
    revalidate_config_at_path,
)


def _make_self_signed_cert_key(cert_path: Path, key_path: Path) -> None:
    """Write a minimal self-signed cert/key pair -- real enough for the TLS
    material validator (cert/key pairing + ``load_pem_private_key``) to accept.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "test.local")]
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _server_configs(config_dir: Path) -> Tuple[dict, dict]:
    """Return (valid_config, invalid_config) referencing real cert/key in ``config_dir``."""
    _make_self_signed_cert_key(config_dir / "server.crt", config_dir / "server.key")
    server_block = {
        "host": "localhost",
        "port": 15000,
        "protocol": "https",
        "ssl": {"cert": "server.crt", "key": "server.key"},
    }
    valid = {
        "server": server_block,
        "queue_manager": {"enabled": True},
        "code_analysis": {
            "database": {
                "driver": {
                    "type": "postgres",
                    "config": {
                        "host": "127.0.0.1",
                        "port": 5432,
                        "dbname": "code_analysis",
                        "user": "postgres",
                        "password_env": "CODE_ANALYSIS_POSTGRES_PASSWORD",
                    },
                }
            },
        },
    }
    # Semantically invalid: a database driver with no ``type`` key at all.
    invalid = {
        "server": server_block,
        "queue_manager": {"enabled": True},
        "code_analysis": {
            "database": {"driver": {"config": {"path": "data/test.db"}}},
        },
    }
    return valid, invalid


def _write_config(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_revalidate_config_caches_unchanged_file(tmp_path: Path) -> None:
    """A second call against an unchanged file is served from cache, not re-parsed."""
    reset_config_validation_cache()
    valid_cfg, _ = _server_configs(tmp_path)
    cfg_path = tmp_path / "config.json"
    _write_config(cfg_path, valid_cfg)

    data1, valid1 = revalidate_config_at_path(cfg_path)
    diag_after_first = get_config_validation_cache_diagnostics()
    assert valid1 is True
    assert diag_after_first["load_count"] == 1
    assert diag_after_first["cache_hit_count"] == 0

    data2, valid2 = revalidate_config_at_path(cfg_path)
    diag_after_second = get_config_validation_cache_diagnostics()
    assert valid2 is True
    assert data2 == data1
    # No new parse/validate (and no new RSA load_pem_private_key) happened;
    # only the cache-hit counter moved.
    assert diag_after_second["load_count"] == 1
    assert diag_after_second["cache_hit_count"] == 1

    # A cache hit still refreshes the externally visible runtime state.
    assert is_config_valid() is True
    assert get_config_runtime_state().valid is True


def test_revalidate_config_reloads_after_mtime_change(tmp_path: Path) -> None:
    """Editing the file (mtime/size change) forces a fresh parse+validate."""
    reset_config_validation_cache()
    valid_cfg, _ = _server_configs(tmp_path)
    cfg_path = tmp_path / "config.json"
    _write_config(cfg_path, valid_cfg)

    revalidate_config_at_path(cfg_path)
    assert get_config_validation_cache_diagnostics()["load_count"] == 1

    # Force a distinct (mtime_ns, size) key: change content and bump mtime.
    changed = dict(valid_cfg)
    changed["queue_manager"] = {"enabled": False}
    _write_config(cfg_path, changed)
    future = time.time() + 5
    os.utime(cfg_path, (future, future))

    data2, valid2 = revalidate_config_at_path(cfg_path)
    diag = get_config_validation_cache_diagnostics()
    assert valid2 is True
    assert data2["queue_manager"]["enabled"] is False
    assert diag["load_count"] == 2  # re-validated, not served from stale cache
    assert diag["cache_hit_count"] == 0


def test_revalidate_config_failed_validation_not_cached_as_success(
    tmp_path: Path,
) -> None:
    """A failed validation is cached as its own outcome, not coerced to success."""
    reset_config_validation_cache()
    valid_cfg, invalid_cfg = _server_configs(tmp_path)
    cfg_path = tmp_path / "config.json"
    _write_config(cfg_path, invalid_cfg)

    data1, valid1 = revalidate_config_at_path(cfg_path)
    assert valid1 is False
    assert get_config_runtime_state().valid is False

    # Second call, unchanged file: still False, served from cache (not re-derived
    # as success just because a cache entry exists).
    data2, valid2 = revalidate_config_at_path(cfg_path)
    diag = get_config_validation_cache_diagnostics()
    assert valid2 is False
    assert data2 == data1
    assert diag["load_count"] == 1
    assert diag["cache_hit_count"] == 1
    assert is_config_valid() is False

    # Fixing the file (mtime change) must flip the cached outcome to success.
    future = time.time() + 5
    _write_config(cfg_path, valid_cfg)
    os.utime(cfg_path, (future, future))
    data3, valid3 = revalidate_config_at_path(cfg_path)
    assert valid3 is True
    assert get_config_validation_cache_diagnostics()["load_count"] == 2


def test_revalidate_config_cache_is_per_path(tmp_path: Path) -> None:
    """Two distinct config paths are cached independently."""
    reset_config_validation_cache()
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    valid_cfg, _ = _server_configs(dir_a)
    _, invalid_cfg = _server_configs(dir_b)
    path_a = dir_a / "config.json"
    path_b = dir_b / "config.json"
    _write_config(path_a, valid_cfg)
    _write_config(path_b, invalid_cfg)

    _, valid_a = revalidate_config_at_path(path_a)
    _, valid_b = revalidate_config_at_path(path_b)
    assert valid_a is True
    assert valid_b is False
    assert get_config_validation_cache_diagnostics()["load_count"] == 2

    # Re-reading each unchanged path hits its own cache entry, not the other's.
    _, valid_a2 = revalidate_config_at_path(path_a)
    _, valid_b2 = revalidate_config_at_path(path_b)
    assert valid_a2 is True
    assert valid_b2 is False
    diag = get_config_validation_cache_diagnostics()
    assert diag["load_count"] == 2
    assert diag["cache_hit_count"] == 2
