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

from .constants import (
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    DEFAULT_CHUNKER_PORT,
    DEFAULT_EMBEDDING_PORT,
    DEFAULT_LOCALHOST,
    DEFAULT_MIN_CHUNK_LENGTH,
    DEFAULT_RETRY_ATTEMPTS,
    DEFAULT_RETRY_DELAY,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_EMPTY_ITERATIONS,
    DEFAULT_EMPTY_DELAY,
    DEFAULT_LOG_MAX_BYTES,
    DEFAULT_LOG_BACKUP_COUNT,
    DEFAULT_FAILURE_THRESHOLD,
    DEFAULT_RECOVERY_TIMEOUT,
    DEFAULT_SUCCESS_THRESHOLD,
    DEFAULT_INITIAL_BACKOFF,
    DEFAULT_MAX_BACKOFF,
    DEFAULT_BACKOFF_MULTIPLIER,
    DEFAULT_MAX_SCAN_DURATION,
    DEFAULT_DYNAMIC_WATCH_FILE,
    DEFAULT_VECTORIZATION_WORKER_LOG,
    DEFAULT_FILE_WATCHER_LOG,
    VERSIONS_DIR_NAME,
    FILE_WATCHER_IGNORE_PATTERNS,
)


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
        default=DEFAULT_RETRY_ATTEMPTS, description="Number of retry attempts on failure"
    )
    retry_delay: float = Field(
        default=DEFAULT_RETRY_DELAY,
        description="Delay in seconds between retry attempts",
    )
    timeout: Optional[float] = Field(
        default=None, description="Optional timeout for service requests (seconds)"
    )
    check_hostname: bool = Field(
        default=False, description="Enable hostname verification for SSL/TLS connections (default: False)"
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

    host: str = Field(default=DEFAULT_SERVER_HOST, description="Server host")
    port: int = Field(default=DEFAULT_SERVER_PORT, description="Server port")
    log: Optional[str] = Field(default=None, description="Path to log file")
    db_path: Optional[str] = Field(default=None, description="Path to SQLite database")
    dirs: List[ProjectDir] = Field(
        default_factory=list, description="Project directories"
    )
    chunker: Optional[SVOServiceConfig] = Field(
        default=None,
        description="Chunker service configuration (chunker handles both chunking and embeddings)",
    )
    embedding: Optional[SVOServiceConfig] = Field(
        default=None,
        description="Embedding service configuration (optional, if separate from chunker)",
    )
    faiss_index_path: Optional[str] = Field(
        default=None,
        description="Path to FAISS index file (shared across all projects)",
    )
    vector_dim: Optional[int] = Field(
        default=None,
        description="Vector dimension for embeddings (required if using FAISS)",
    )
    min_chunk_length: int = Field(
        default=DEFAULT_MIN_CHUNK_LENGTH,
        description="Minimum text length for chunking. Shorter texts are grouped by level.",
    )
    vectorization_retry_attempts: int = Field(
        default=DEFAULT_RETRY_ATTEMPTS,
        description="Number of retry attempts for vectorization on failure",
    )
    vectorization_retry_delay: float = Field(
        default=DEFAULT_RETRY_DELAY,
        description="Delay in seconds between vectorization retry attempts",
    )
    worker: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {
            "enabled": True,
            "poll_interval": DEFAULT_POLL_INTERVAL,
            "batch_size": DEFAULT_BATCH_SIZE,
            "retry_attempts": DEFAULT_RETRY_ATTEMPTS,
            "retry_delay": DEFAULT_RETRY_DELAY,
            "watch_dirs": [],
            "dynamic_watch_file": DEFAULT_DYNAMIC_WATCH_FILE,
            "log_path": DEFAULT_VECTORIZATION_WORKER_LOG,
            "log_rotation": {
                "max_bytes": DEFAULT_LOG_MAX_BYTES,
                "backup_count": DEFAULT_LOG_BACKUP_COUNT,
            },
            "circuit_breaker": {
                "failure_threshold": DEFAULT_FAILURE_THRESHOLD,
                "recovery_timeout": DEFAULT_RECOVERY_TIMEOUT,
                "success_threshold": DEFAULT_SUCCESS_THRESHOLD,
                "initial_backoff": DEFAULT_INITIAL_BACKOFF,
                "max_backoff": DEFAULT_MAX_BACKOFF,
                "backoff_multiplier": DEFAULT_BACKOFF_MULTIPLIER,
            },
            "batch_processor": {
                "max_empty_iterations": DEFAULT_MAX_EMPTY_ITERATIONS,
                "empty_delay": DEFAULT_EMPTY_DELAY,
            },
        },
        description="Vectorization worker configuration",
    )
    file_watcher: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {
            "enabled": True,
            "scan_interval": DEFAULT_SCAN_INTERVAL,
            # lock_file_name removed: locks are now stored in locks_dir (service state directory)
            # See Step 4 of REFACTOR_MULTI_PROJECT_INDEXING_PLAN.md
            "log_path": DEFAULT_FILE_WATCHER_LOG,
            "log_rotation": {
                "max_bytes": DEFAULT_LOG_MAX_BYTES,
                "backup_count": DEFAULT_LOG_BACKUP_COUNT,
            },
            "version_dir": VERSIONS_DIR_NAME,
            "max_scan_duration": DEFAULT_MAX_SCAN_DURATION,
            "ignore_patterns": FILE_WATCHER_IGNORE_PATTERNS,
        },
        description="File watcher worker configuration",
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
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
    log: Optional[str] = None,
    db_path: Optional[str] = None,
    dirs: Optional[List[Dict[str, str]]] = None,
    chunker_host: str = DEFAULT_LOCALHOST,
    chunker_port: int = DEFAULT_CHUNKER_PORT,
    embedding_host: str = DEFAULT_LOCALHOST,
    embedding_port: int = DEFAULT_EMBEDDING_PORT,
    mtls_certificates: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Generate server configuration.

    Args:
        host: Server host (default from constants)
        port: Server port (default from constants)
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
    cert_file = None
    key_file = None
    ca_cert_file = None
    crl_file = None
    if mtls_certificates:
        # Support multiple key styles used across the project/tests.
        cert_file = mtls_certificates.get("cert_file") or mtls_certificates.get("cert")
        key_file = mtls_certificates.get("key_file") or mtls_certificates.get("key")
        ca_cert_file = mtls_certificates.get("ca_cert_file") or mtls_certificates.get(
            "ca_cert"
        )
        crl_file = mtls_certificates.get("crl_file") or mtls_certificates.get("crl")

    protocol = "mtls" if (cert_file and key_file) else "https"

    config["chunker"] = {
        "enabled": True,
        "host": chunker_host,
        "port": chunker_port,
        "protocol": protocol,
        "cert_file": cert_file,
        "key_file": key_file,
        "ca_cert_file": ca_cert_file,
        "crl_file": crl_file,
    }
    config["embedding"] = {
        "enabled": True,
        "host": embedding_host,
        "port": embedding_port,
        "protocol": protocol,
        "cert_file": cert_file,
        "key_file": key_file,
        "ca_cert_file": ca_cert_file,
        "crl_file": crl_file,
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
