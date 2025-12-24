"""
Configuration management for MCP server.

Provides configuration schema, validation, and generation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, field_validator, model_validator


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
    url: str = Field(default="localhost", description="Service URL or hostname")
    host: Optional[str] = Field(default=None, description="Alias for url (host)")
    port: int = Field(default=8009, description="Service port")
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
        default=3, description="Number of retry attempts on failure (default: 3)"
    )
    retry_delay: float = Field(
        default=5.0, description="Delay in seconds between retry attempts (default: 5.0)"
    )
    timeout: Optional[float] = Field(
        default=None, description="Optional timeout for service requests (seconds)"
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

    @model_validator(mode='after')
    def validate_mtls_config(self) -> 'SVOServiceConfig':
        """Validate mTLS configuration after initialization."""
        # If host provided, use it as url
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


class ServerConfig(BaseModel):
    """MCP server configuration."""

    model_config = {"extra": "forbid"}  # Reject unknown fields

    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=15000, description="Server port")
    log: Optional[str] = Field(default=None, description="Path to log file")
    db_path: Optional[str] = Field(default=None, description="Path to SQLite database")
    dirs: List[ProjectDir] = Field(
        default_factory=list, description="Project directories"
    )
    chunker: Optional[SVOServiceConfig] = Field(
        default=None, description="Chunker service configuration (chunker handles both chunking and embeddings)"
    )
    embedding: Optional[SVOServiceConfig] = Field(
        default=None, description="Embedding service configuration (optional, if separate from chunker)"
    )
    faiss_index_path: Optional[str] = Field(
        default=None, description="Path to FAISS index file (shared across all projects)"
    )
    vector_dim: Optional[int] = Field(
        default=None, description="Vector dimension for embeddings (required if using FAISS)"
    )
    min_chunk_length: int = Field(
        default=30, description="Minimum text length for chunking (default: 30). Shorter texts are grouped by level."
    )
    vectorization_retry_attempts: int = Field(
        default=3, description="Number of retry attempts for vectorization on failure (default: 3)"
    )
    vectorization_retry_delay: float = Field(
        default=10.0, description="Delay in seconds between vectorization retry attempts (default: 10.0)"
    )
    worker: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {
            "enabled": True,
            "poll_interval": 30,
            "batch_size": 10,
            "retry_attempts": 3,
            "retry_delay": 10.0,
            "watch_dirs": [],
            "dynamic_watch_file": "data/dynamic_watch_dirs.json",
        },
        description="Vectorization worker configuration",
    )

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port range."""
        if not (1 <= v <= 65535):
            raise ValueError(f"Port must be between 1 and 65535: {v}")
        return v

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        """Validate host format."""
        if not v or not v.strip():
            raise ValueError("Host cannot be empty")
        return v.strip()

    @field_validator("log")
    @classmethod
    def validate_log_path(cls, v: Optional[str]) -> Optional[str]:
        """Validate log file path."""
        if v is None:
            return None
        log_path = Path(v)
        # Ensure parent directory exists
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return str(log_path.resolve())

    @field_validator("db_path")
    @classmethod
    def validate_db_path(cls, v: Optional[str]) -> Optional[str]:
        """Validate database path."""
        if v is None:
            return None
        db_path = Path(v)
        # Ensure parent directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return str(db_path.resolve())

    @field_validator("faiss_index_path")
    @classmethod
    def validate_faiss_index_path(cls, v: Optional[str]) -> Optional[str]:
        """Validate FAISS index path."""
        if v is None:
            return None
        index_path = Path(v)
        # Ensure parent directory exists
        index_path.parent.mkdir(parents=True, exist_ok=True)
        return str(index_path.resolve())

    @field_validator("vector_dim")
    @classmethod
    def validate_vector_dim(cls, v: Optional[int]) -> Optional[int]:
        """Validate vector dimension."""
        if v is not None and v <= 0:
            raise ValueError("Vector dimension must be positive")
        return v


def generate_config(
    host: str = "0.0.0.0",
    port: int = 15000,
    log: Optional[str] = None,
    db_path: Optional[str] = None,
    dirs: Optional[List[Dict[str, str]]] = None,
    chunker_host: str = "localhost",
    chunker_port: int = 8009,
    mtls_certificates: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Generate server configuration.

    Args:
        host: Server host (default: 0.0.0.0)
        port: Server port (default: 15000)
        log: Path to log file (optional)
        db_path: Path to SQLite database (optional)
        dirs: List of directories with 'name' and 'path' keys.
              UUID4 will be generated automatically.

    Returns:
        Configuration dictionary
    """
    config_dirs = []
    if dirs:
        for dir_info in dirs:
            name = dir_info.get("name", Path(dir_info["path"]).name)
            path = Path(dir_info["path"]).resolve()
            if not path.exists():
                raise ValueError(f"Path does not exist: {path}")
            if not path.is_dir():
                raise ValueError(f"Path is not a directory: {path}")

            config_dirs.append(
                {
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "path": str(path),
                }
            )

    config = {
        "host": host,
        "port": port,
        "dirs": config_dirs,
    }
    if log:
        log_path = Path(log)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        config["log"] = str(log_path.resolve())
    if db_path:
        db_path_obj = Path(db_path)
        db_path_obj.parent.mkdir(parents=True, exist_ok=True)
        config["db_path"] = str(db_path_obj.resolve())

    # Add SVO service configurations
    if mtls_certificates:
        # Determine protocol based on presence of certificates
        protocol = "mtls" if mtls_certificates.get("cert_file") else "https"
        
        config["chunker"] = {
            "enabled": True,
            "url": chunker_host,
            "port": chunker_port,
            "protocol": protocol,
            "cert_file": mtls_certificates.get("cert_file"),
            "key_file": mtls_certificates.get("key_file"),
            "ca_cert_file": mtls_certificates.get("ca_cert_file"),
            "crl_file": mtls_certificates.get("crl_file"),
        }

    return config


def validate_config(
    config_path: Path,
) -> tuple[bool, Optional[str], Optional[ServerConfig]]:
    """
    Validate configuration file.

    Args:
        config_path: Path to configuration file

    Returns:
        Tuple of (is_valid, error_message, config_object)
    """
    try:
        if not config_path.exists():
            return False, f"Configuration file not found: {config_path}", None

        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        # Validate using Pydantic
        config = ServerConfig(**config_data)

        # Additional validations: check for duplicate IDs and names
        ids = [d.id for d in config.dirs]
        names = [d.name for d in config.dirs]

        # Check for duplicate IDs
        if len(ids) != len(set(ids)):
            duplicates = [id for id in ids if ids.count(id) > 1]
            return (
                False,
                f"Duplicate project IDs found: {set(duplicates)}",
                None,
            )

        # Check for duplicate names
        if len(names) != len(set(names)):
            duplicates = [name for name in names if names.count(name) > 1]
            return (
                False,
                f"Duplicate project names found: {set(duplicates)}",
                None,
            )

        return True, None, config

    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {str(e)}", None
    except ValueError as e:
        return False, f"Validation error: {str(e)}", None
    except Exception as e:
        return False, f"Unexpected error: {str(e)}", None


def load_config(config_path: Path) -> ServerConfig:
    """
    Load and validate configuration.

    Args:
        config_path: Path to configuration file

    Returns:
        ServerConfig object

    Raises:
        ValueError: If configuration is invalid
    """
    is_valid, error, config = validate_config(config_path)
    if not is_valid:
        raise ValueError(error or "Invalid configuration")
    if config is None:
        raise ValueError("Failed to load configuration")
    return config


def save_config(config: Dict[str, Any], config_path: Path) -> None:
    """
    Save configuration to file.

    Args:
        config: Configuration dictionary
        config_path: Path to save configuration
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
