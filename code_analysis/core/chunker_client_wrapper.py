"""
Helper functions for creating ChunkerClient with mTLS support.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ssl
import logging
from pathlib import Path
from typing import Optional

from svo_client import ChunkerClient

from .config import SVOServiceConfig

logger = logging.getLogger(__name__)


def create_ssl_context(
    cert_file: Optional[str] = None,
    key_file: Optional[str] = None,
    ca_cert_file: Optional[str] = None,
    crl_file: Optional[str] = None,
) -> Optional[ssl.SSLContext]:
    """
    Create SSL context for mTLS.

    Args:
        cert_file: Path to client certificate file
        key_file: Path to client private key file
        ca_cert_file: Path to CA certificate file
        crl_file: Path to CRL file (optional)

    Returns:
        SSL context or None if no certificates provided
    """
    if not cert_file or not key_file or not ca_cert_file:
        return None

    # Create SSL context for client authentication
    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

    # Load client certificate and key
    ssl_context.load_cert_chain(cert_file, key_file)

    # Load CA certificate for server verification
    ssl_context.load_verify_locations(ca_cert_file)

    # Set verification mode to require server certificate
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    ssl_context.check_hostname = False

    # Load CRL if provided
    if crl_file and Path(crl_file).exists():
        try:
            # Note: Python's ssl module doesn't directly support CRL loading
            logger.warning(
                f"CRL file provided but not loaded: {crl_file}. CRL support requires additional implementation."
            )
        except Exception as e:
            logger.warning(f"Failed to load CRL file {crl_file}: {e}")

    return ssl_context


def create_chunker_client(config: SVOServiceConfig) -> ChunkerClient:
    """
    Create ChunkerClient with mTLS support if configured.

    Args:
        config: SVO service configuration

    Returns:
        Configured ChunkerClient instance
    """
    # New ChunkerClient API (v2.2.0+): host, port, cert, key, ca, timeout
    # ChunkerClient now supports mTLS natively through cert/key/ca parameters
    # and uses JsonRpcClient internally with proper config resolution
    # ChunkerClient internally uses ConfigLoader.resolve_config() which creates
    # config dict in format: {"server": {...}, "ssl": {...}, "auth": {...}}
    # Then config_to_client_kwargs() converts it to JsonRpcClient kwargs

    # Extract host from url (remove protocol if present)
    host = config.url
    if "://" in host:
        host = host.split("://", 1)[1]
    # Remove trailing slash
    host = host.rstrip("/")

    client_kwargs = {
        "host": host,
        "port": config.port,
        "check_hostname": False,  # Disable hostname verification for mTLS
    }

    # Add timeout if configured
    if config.timeout is not None:
        client_kwargs["timeout"] = float(config.timeout)

    # Add mTLS certificates only if protocol is explicitly mtls or https
    # Note: If protocol is "http", do NOT pass certificates even if they are configured,
    # as this will cause the client to try to use SSL/TLS which the server doesn't support
    if config.protocol in ("https", "mtls"):
        if config.cert_file and config.key_file and config.ca_cert_file:
            # Resolve paths to absolute if relative
            cert_file = Path(config.cert_file)
            key_file = Path(config.key_file)
            ca_cert_file = Path(config.ca_cert_file)

            # Resolve to absolute paths
            if cert_file.exists():
                client_kwargs["cert"] = str(cert_file.resolve())
            else:
                client_kwargs["cert"] = config.cert_file

            if key_file.exists():
                client_kwargs["key"] = str(key_file.resolve())
            else:
                client_kwargs["key"] = config.key_file

            if ca_cert_file.exists():
                client_kwargs["ca"] = str(ca_cert_file.resolve())
            else:
                client_kwargs["ca"] = config.ca_cert_file

            logger.debug(
                f"Configuring mTLS: cert={client_kwargs['cert']}, "
                f"key={client_kwargs['key']}, ca={client_kwargs['ca']}"
            )
        else:
            logger.warning("mTLS protocol specified but certificates not provided")
    elif config.protocol == "http":
        # Explicitly do NOT pass certificates for HTTP protocol
        # This ensures the client uses HTTP instead of trying to use SSL/TLS
        logger.debug("Using HTTP protocol (no certificates)")

    # Create client - ChunkerClient will handle config resolution internally
    # It uses ConfigLoader.resolve_config() which merges CLI/API > env > file config
    # The cert/key/ca parameters will be used to create SSL config with verify_mode="CERT_REQUIRED"
    # which will result in protocol="mtls" in config_to_client_kwargs()
    client = ChunkerClient(**client_kwargs)

    return client
