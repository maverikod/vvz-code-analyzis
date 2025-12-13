"""
Configuration generator for SVO chunker client with mTLS support.

Provides utilities for generating configuration files for svo_client
with mutual TLS authentication.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class MTLSConfig(BaseModel):
    """mTLS configuration for SVO services."""

    cert_file: str = Field(..., description="Path to client certificate file")
    key_file: str = Field(..., description="Path to client private key file")
    ca_file: Optional[str] = Field(
        default=None, description="Path to CA certificate file"
    )
    verify_hostname: bool = Field(
        default=False, description="Verify hostname in certificate"
    )

    @field_validator("cert_file", "key_file")
    @classmethod
    def validate_cert_path(cls, v: str) -> str:
        """Validate certificate file path exists."""
        path = Path(v)
        if not path.exists():
            raise ValueError(f"Certificate file does not exist: {v}")
        return str(path.resolve())

    @field_validator("ca_file")
    @classmethod
    def validate_ca_path(cls, v: Optional[str]) -> Optional[str]:
        """Validate CA certificate file path exists."""
        if v is None:
            return None
        path = Path(v)
        if not path.exists():
            raise ValueError(f"CA certificate file does not exist: {v}")
        return str(path.resolve())


class SVOServiceConfig(BaseModel):
    """Configuration for SVO service (chunker or embedding)."""

    host: str = Field(default="localhost", description="Service host")
    port: int = Field(..., description="Service port")
    protocol: str = Field(default="https", description="Protocol (http/https)")
    mtls: Optional[MTLSConfig] = Field(
        default=None, description="mTLS configuration"
    )
    timeout: float = Field(default=60.0, description="Request timeout in seconds")

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port range."""
        if not (1 <= v <= 65535):
            raise ValueError(f"Port must be between 1 and 65535: {v}")
        return v

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, v: str) -> str:
        """Validate protocol."""
        if v not in ("http", "https"):
            raise ValueError(f"Protocol must be 'http' or 'https': {v}")
        return v


class SVOClientConfig(BaseModel):
    """Complete configuration for SVO client."""

    chunker: SVOServiceConfig = Field(..., description="Chunker service config")
    embedding: SVOServiceConfig = Field(..., description="Embedding service config")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "chunker": {
                "host": self.chunker.host,
                "port": self.chunker.port,
                "protocol": self.chunker.protocol,
                "timeout": self.chunker.timeout,
                "mtls": (
                    {
                        "cert_file": self.chunker.mtls.cert_file,
                        "key_file": self.chunker.mtls.key_file,
                        "ca_file": self.chunker.mtls.ca_file,
                        "verify_hostname": self.chunker.mtls.verify_hostname,
                    }
                    if self.chunker.mtls
                    else None
                ),
            },
            "embedding": {
                "host": self.embedding.host,
                "port": self.embedding.port,
                "protocol": self.embedding.protocol,
                "timeout": self.embedding.timeout,
                "mtls": (
                    {
                        "cert_file": self.embedding.mtls.cert_file,
                        "key_file": self.embedding.mtls.key_file,
                        "ca_file": self.embedding.mtls.ca_file,
                        "verify_hostname": self.embedding.mtls.verify_hostname,
                    }
                    if self.embedding.mtls
                    else None
                ),
            },
        }


def generate_svo_config(
    chunker_host: str = "localhost",
    chunker_port: int = 8009,
    embedding_host: str = "localhost",
    embedding_port: int = 8001,
    mtls_certificates: Optional[Dict[str, str]] = None,
    verify_hostname: bool = False,
    timeout: float = 60.0,
) -> SVOClientConfig:
    """
    Generate SVO client configuration.

    Args:
        chunker_host: Chunker service host (default: localhost)
        chunker_port: Chunker service port (default: 8009)
        embedding_host: Embedding service host (default: localhost)
        embedding_port: Embedding service port (default: 8001)
        mtls_certificates: Dictionary with certificate paths:
            - cert_file: Path to client certificate
            - key_file: Path to client private key
            - ca_file: Path to CA certificate (optional)
        verify_hostname: Verify hostname in certificate (default: False)
        timeout: Request timeout in seconds (default: 60.0)

    Returns:
        SVOClientConfig object
    """
    mtls_config = None
    if mtls_certificates:
        mtls_config = MTLSConfig(
            cert_file=mtls_certificates["cert_file"],
            key_file=mtls_certificates["key_file"],
            ca_file=mtls_certificates.get("ca_file"),
            verify_hostname=verify_hostname,
        )

    chunker_config = SVOServiceConfig(
        host=chunker_host,
        port=chunker_port,
        protocol="https" if mtls_config else "http",
        mtls=mtls_config,
        timeout=timeout,
    )

    embedding_config = SVOServiceConfig(
        host=embedding_host,
        port=embedding_port,
        protocol="https" if mtls_config else "http",
        mtls=mtls_config,
        timeout=timeout,
    )

    return SVOClientConfig(chunker=chunker_config, embedding=embedding_config)


def save_svo_config(config: SVOClientConfig, config_path: Path) -> None:
    """
    Save SVO client configuration to file.

    Args:
        config: SVOClientConfig object
        config_path: Path to save configuration
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)


def load_svo_config(config_path: Path) -> SVOClientConfig:
    """
    Load SVO client configuration from file.

    Args:
        config_path: Path to configuration file

    Returns:
        SVOClientConfig object

    Raises:
        ValueError: If configuration is invalid
    """
    if not config_path.exists():
        raise ValueError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config_data = json.load(f)

    # Parse chunker config
    chunker_data = config_data.get("chunker", {})
    chunker_mtls = None
    if chunker_data.get("mtls"):
        chunker_mtls = MTLSConfig(**chunker_data["mtls"])

    chunker_config = SVOServiceConfig(
        host=chunker_data.get("host", "localhost"),
        port=chunker_data["port"],
        protocol=chunker_data.get("protocol", "https" if chunker_mtls else "http"),
        mtls=chunker_mtls,
        timeout=chunker_data.get("timeout", 60.0),
    )

    # Parse embedding config
    embedding_data = config_data.get("embedding", {})
    embedding_mtls = None
    if embedding_data.get("mtls"):
        embedding_mtls = MTLSConfig(**embedding_data["mtls"])

    embedding_config = SVOServiceConfig(
        host=embedding_data.get("host", "localhost"),
        port=embedding_data["port"],
        protocol=embedding_data.get("protocol", "https" if embedding_mtls else "http"),
        mtls=embedding_mtls,
        timeout=embedding_data.get("timeout", 60.0),
    )

    return SVOClientConfig(chunker=chunker_config, embedding=embedding_config)

