"""
Shared TLS/mTLS path resolution for SVO chunker and embedding clients.

Rule: every certificate path set in config is forwarded to the client.
``protocol: https`` and ``protocol: mtls`` are treated the same for cert wiring;
``embed_client`` / ``svo_client`` pick mTLS when both client cert and key are present.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def is_tls_protocol(protocol: str | None) -> bool:
    """True when config protocol uses HTTPS transport."""
    return (protocol or "http").lower() in ("https", "mtls")


def resolve_service_file_path(
    root: Path | None,
    path_str: str | None,
) -> str | None:
    """Resolve a config-relative certificate/path string to an absolute path."""
    if not path_str or not str(path_str).strip():
        return None
    path = Path(path_str).expanduser()
    if not path.is_absolute() and root is not None:
        path = root / path
    return str(path.resolve())


def _configured_tls_paths(
    root: Path | None,
    *,
    cert_file: str | None,
    key_file: str | None,
    ca_cert_file: str | None,
    crl_file: str | None,
) -> dict[str, str]:
    """Resolve all configured TLS file paths (only non-empty entries)."""
    paths: dict[str, str] = {}
    cert = resolve_service_file_path(root, cert_file)
    key = resolve_service_file_path(root, key_file)
    ca = resolve_service_file_path(root, ca_cert_file)
    crl = resolve_service_file_path(root, crl_file)
    if cert:
        paths["cert_file"] = cert
    if key:
        paths["key_file"] = key
    if ca:
        paths["ca_cert_file"] = ca
    if crl:
        paths["crl_file"] = crl
    return paths


def service_use_tls(
    protocol: str | None,
    *,
    root: Path | None,
    cert_file: str | None,
    key_file: str | None,
    ca_cert_file: str | None,
    crl_file: str | None = None,
) -> bool:
    """True when TLS transport is required (explicit protocol or any cert path set)."""
    if is_tls_protocol(protocol):
        return True
    return bool(
        _configured_tls_paths(
            root,
            cert_file=cert_file,
            key_file=key_file,
            ca_cert_file=ca_cert_file,
            crl_file=crl_file,
        )
    )


def embedding_client_ssl_kwargs(
    *,
    root: Path | None,
    protocol: str,
    cert_file: str | None,
    key_file: str | None,
    ca_cert_file: str | None,
    crl_file: str | None,
    check_hostname: bool,
) -> dict[str, Any]:
    """
    Build SSL/mTLS kwargs for ``embed_client.ClientFactory.create_client``.

    All configured cert paths are included. ``https`` and ``mtls`` behave the same;
    the factory selects mTLS when both ``cert_file`` and ``key_file`` are present.
    """
    if not service_use_tls(
        protocol,
        root=root,
        cert_file=cert_file,
        key_file=key_file,
        ca_cert_file=ca_cert_file,
        crl_file=crl_file,
    ):
        return {}
    kwargs: dict[str, Any] = {"check_hostname": bool(check_hostname)}
    kwargs.update(
        _configured_tls_paths(
            root,
            cert_file=cert_file,
            key_file=key_file,
            ca_cert_file=ca_cert_file,
            crl_file=crl_file,
        )
    )
    return kwargs


def chunker_client_tls_paths(
    *,
    root: Path | None,
    protocol: str,
    cert_file: str | None,
    key_file: str | None,
    ca_cert_file: str | None,
    crl_file: str | None = None,
) -> dict[str, str]:
    """Build ``cert`` / ``key`` / ``ca`` paths for ``SvoChunkerClient``."""
    if not service_use_tls(
        protocol,
        root=root,
        cert_file=cert_file,
        key_file=key_file,
        ca_cert_file=ca_cert_file,
        crl_file=crl_file,
    ):
        return {}
    resolved = _configured_tls_paths(
        root,
        cert_file=cert_file,
        key_file=key_file,
        ca_cert_file=ca_cert_file,
        crl_file=crl_file,
    )
    out: dict[str, str] = {}
    if "cert_file" in resolved:
        out["cert"] = resolved["cert_file"]
    if "key_file" in resolved:
        out["key"] = resolved["key_file"]
    if "ca_cert_file" in resolved:
        out["ca"] = resolved["ca_cert_file"]
    return out
