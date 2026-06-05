"""
Tests for shared SVO service TLS kwargs (chunker + embedding).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis.core.svo_client_manager_embedding import init_embedding
from code_analysis.core.svo_client_manager_ssl import (
    chunker_client_tls_paths,
    embedding_client_ssl_kwargs,
    is_tls_protocol,
    resolve_service_file_path,
    service_use_tls,
)


def test_is_tls_protocol() -> None:
    assert is_tls_protocol("https") is True
    assert is_tls_protocol("mtls") is True
    assert is_tls_protocol("http") is False


def test_embedding_client_ssl_kwargs_https_includes_client_certs(tmp_path) -> None:
    cert = tmp_path / "client.crt"
    key = tmp_path / "client.key"
    ca = tmp_path / "ca.crt"
    cert.write_text("cert", encoding="utf-8")
    key.write_text("key", encoding="utf-8")
    ca.write_text("ca", encoding="utf-8")

    for protocol in ("https", "mtls"):
        kwargs = embedding_client_ssl_kwargs(
            root=tmp_path,
            protocol=protocol,
            cert_file="client.crt",
            key_file="client.key",
            ca_cert_file="ca.crt",
            crl_file=None,
            check_hostname=False,
        )

        assert kwargs["cert_file"] == str(cert.resolve()), protocol
        assert kwargs["key_file"] == str(key.resolve()), protocol
        assert kwargs["ca_cert_file"] == str(ca.resolve()), protocol
        assert kwargs["check_hostname"] is False, protocol
        assert "verify" not in kwargs, protocol


def test_chunker_tls_paths_https_and_mtls_identical(tmp_path) -> None:
    cert = tmp_path / "client.crt"
    key = tmp_path / "client.key"
    ca = tmp_path / "ca.crt"
    cert.write_text("cert", encoding="utf-8")
    key.write_text("key", encoding="utf-8")
    ca.write_text("ca", encoding="utf-8")

    expected = {
        "cert": str(cert.resolve()),
        "key": str(key.resolve()),
        "ca": str(ca.resolve()),
    }
    for protocol in ("https", "mtls"):
        paths = chunker_client_tls_paths(
            root=tmp_path,
            protocol=protocol,
            cert_file="client.crt",
            key_file="client.key",
            ca_cert_file="ca.crt",
        )
        assert paths == expected, protocol


def test_service_use_tls_when_only_ca_configured(tmp_path) -> None:
    ca = tmp_path / "ca.crt"
    ca.write_text("ca", encoding="utf-8")
    assert service_use_tls(
        "http",
        root=tmp_path,
        cert_file=None,
        key_file=None,
        ca_cert_file="ca.crt",
    )


def test_resolve_service_file_path_relative_to_root(tmp_path) -> None:
    rel = tmp_path / "tls" / "ca.crt"
    rel.parent.mkdir()
    rel.write_text("ca", encoding="utf-8")
    assert resolve_service_file_path(tmp_path, "tls/ca.crt") == str(rel.resolve())


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", ["https", "mtls"])
async def test_init_embedding_forwards_ssl_kwargs(tmp_path, protocol: str) -> None:
    cert = tmp_path / "client.crt"
    key = tmp_path / "client.key"
    ca = tmp_path / "ca.crt"
    cert.write_text("cert", encoding="utf-8")
    key.write_text("key", encoding="utf-8")
    ca.write_text("ca", encoding="utf-8")

    manager = SimpleNamespace(
        embedding_enabled=True,
        _root_path=tmp_path,
        _embedding_url="192.168.254.26",
        _embedding_port=8001,
        _embedding_protocol=protocol,
        _embedding_cert_file=str(cert),
        _embedding_key_file=str(key),
        _embedding_ca_cert_file=str(ca),
        _embedding_crl_file=None,
        _embedding_timeout=30.0,
        _embedding_check_hostname=False,
        _embedding_client=None,
        vector_dim=384,
    )
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "code_analysis.core.svo_client_manager_embedding.ClientFactory.create_client",
        return_value=mock_client,
    ) as create_client:
        await init_embedding(manager)

    assert manager._embedding_client is mock_client
    kwargs = create_client.call_args.kwargs
    assert kwargs["cert_file"] == str(cert.resolve())
    assert kwargs["key_file"] == str(key.resolve())
    assert kwargs["ca_cert_file"] == str(ca.resolve())
    assert kwargs["check_hostname"] is False
    assert "verify" not in kwargs
    assert create_client.call_args.kwargs["ssl_enabled"] is True
