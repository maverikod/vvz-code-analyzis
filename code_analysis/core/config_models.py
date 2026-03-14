"""
Pydantic models for MCP server configuration (ProjectDir, SVOServiceConfig, ServerConfig).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .constants import (
    DEFAULT_CHUNKER_PORT,
    DEFAULT_LOCALHOST,
    DEFAULT_RETRY_ATTEMPTS,
    DEFAULT_RETRY_DELAY,
)
from .settings_manager import get_settings


class ProjectDir(BaseModel):
    """Project directory configuration."""

    model_config = {"extra": "forbid"}  # Reject unknown fields

    id: str = Field(..., description="UUID4 identifier")
    name: str = Field(..., description="Human-friendly identifier")
    path: str = Field(..., description="Absolute path to project directory")

    @field_validator("id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        """Validate UUID4 format."""
        try:
            uuid.UUID(v, version=4)
            return v
        except ValueError:
            raise ValueError(f"Invalid UUID4 format: {v}")

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate absolute path."""
        path = Path(v)
        if not path.is_absolute():
            raise ValueError(f"Path must be absolute: {v}")
        if not path.exists():
            raise ValueError(f"Path does not exist: {v}")
        if not path.is_dir():
            raise ValueError(f"Path must be a directory: {v}")
        return str(path.resolve())


class SVOServiceConfig(BaseModel):
    """Configuration for SVO service integration.

    Each service (chunker, embedding) has its own configuration block with:
    - url: Service URL/hostname
    - port: Service port
    - protocol: Communication protocol (http, https, mtls)
    - Certificate files (if protocol is mtls)
    - Retry configuration for handling service unavailability
    """

    model_config = {"extra": "forbid"}  # Reject unknown fields

    enabled: bool = Field(default=False, description="Enable SVO service")
    url: str = Field(default=DEFAULT_LOCALHOST, description="Service URL or hostname")
    host: str = Field(default=DEFAULT_LOCALHOST, description="Alias for url (host)")
    port: int = Field(default=DEFAULT_CHUNKER_PORT, description="Service port")
    protocol: str = Field(default="http", description="Protocol: http, https, or mtls")
    cert_file: Optional[str] = Field(
        default=None, description="Path to client certificate file (required for mTLS)"
    )
    key_file: Optional[str] = Field(
        default=None, description="Path to client private key file (required for mTLS)"
    )
    ca_cert_file: Optional[str] = Field(
        default=None, description="Path to CA certificate file (required for mTLS)"
    )
    crl_file: Optional[str] = Field(
        default=None, description="Path to CRL file (optional for mTLS)"
    )
    retry_attempts: int = Field(
        default_factory=lambda: get_settings().get(
            "retry_attempts", DEFAULT_RETRY_ATTEMPTS
        ),
        description="Number of retry attempts on failure",
    )
    retry_delay: float = Field(
        default_factory=lambda: get_settings().get("retry_delay", DEFAULT_RETRY_DELAY),
        description="Delay in seconds between retry attempts",
    )
    timeout: Optional[float] = Field(
        default=None, description="Optional timeout for service requests (seconds)"
    )
    check_hostname: bool = Field(
        default=False,
        description="Enable hostname verification for SSL/TLS connections (default: False)",
    )

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, v: str) -> str:
        """Validate protocol value."""
        v_lower = v.lower()
        if v_lower not in ("http", "https", "mtls"):
            raise ValueError(f"Protocol must be 'http', 'https', or 'mtls', got: {v}")
        return v_lower

    @field_validator("cert_file", "key_file", "ca_cert_file", "crl_file")
    @classmethod
    def validate_cert_path(cls, v: Optional[str]) -> Optional[str]:
        """Validate certificate file path exists if provided."""
        if v is None:
            return None
        path = Path(v)
        if not path.exists():
            raise ValueError(f"Certificate file does not exist: {v}")
        return str(path.resolve())

    @model_validator(mode="after")
    def validate_mtls_config(self) -> "SVOServiceConfig":
        """Validate mTLS configuration after initialization."""
        if self.host:
            object.__setattr__(self, "url", self.host)

        if self.protocol == "mtls":
            if not self.cert_file:
                raise ValueError("cert_file is required when protocol is 'mtls'")
            if not self.key_file:
                raise ValueError("key_file is required when protocol is 'mtls'")
            if not self.ca_cert_file:
                raise ValueError("ca_cert_file is required when protocol is 'mtls'")
        return self
