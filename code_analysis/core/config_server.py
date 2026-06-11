"""
ServerConfig Pydantic model for MCP server configuration.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .constants import (
    DEFAULT_BATCH_MAX_RESPONSE_BYTES,
    DEFAULT_BATCH_OUTPUT_DIR,
    DEFAULT_BATCH_OUTPUT_RETENTION_SECONDS,
    DEFAULT_FILE_WATCHER_LOG,
    DEFAULT_MAX_SCAN_DURATION,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
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
    DEFAULT_MIN_CHUNK_LENGTH,
    DEFAULT_RETRY_ATTEMPTS,
    DEFAULT_RETRY_DELAY,
    DEFAULT_VECTORIZATION_WORKER_LOG,
    VERSIONS_DIR_NAME,
    FILE_WATCHER_IGNORE_PATTERNS,
)
from .config_models import ProjectDir, SVOServiceConfig
from .docs_indexing_defaults import (
    DEFAULT_DOCS_INDEXING_EXCLUDE,
    DEFAULT_DOCS_INDEXING_INCLUDE,
    DEFAULT_DOCS_INDEXING_ROOTS,
)
from .settings_manager import get_settings


class DocsIndexingConfig(BaseModel):
    """Documentation indexing (Markdown, JSON, YAML; server config); vectorization is gated separately."""

    model_config = {"extra": "forbid"}

    enabled: bool = Field(
        default=False,
        description="When false, docs indexing eligibility is off (omitted section equals disabled).",
    )
    vectorize: bool = Field(
        default=False,
        description="When true, eligible docs may be vectorized (enforced in vectorization worker).",
    )
    roots: List[str] = Field(
        default_factory=lambda: list(DEFAULT_DOCS_INDEXING_ROOTS),
        description="Project-relative directory roots for doc trees (POSIX paths).",
    )
    include: List[str] = Field(
        default_factory=lambda: list(DEFAULT_DOCS_INDEXING_INCLUDE),
        description=(
            "Glob patterns for documentation files to include; each pattern should reference "
            ".md, .json, .yaml, or .yml."
        ),
    )
    exclude: List[str] = Field(
        default_factory=lambda: list(DEFAULT_DOCS_INDEXING_EXCLUDE),
        description="Glob patterns that win over include.",
    )


class FileLockConfig(BaseModel):
    """Cooperative project-file advisory lock settings."""

    model_config = {"extra": "forbid"}

    timeout_seconds: float = Field(
        default=30.0,
        description="Maximum seconds to wait for a sidecar flock before failing.",
    )
    poll_interval_seconds: float = Field(
        default=0.05,
        description="Sleep interval between non-blocking flock attempts.",
    )
    default_read_mode: Literal["full", "block_write"] = Field(
        default="full",
        description="Default advisory mode for read commands: full=exclusive, block_write=shared.",
    )

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout_seconds(cls, v: float) -> float:
        if v < 0:
            raise ValueError("file_lock.timeout_seconds must be >= 0")
        return float(v)

    @field_validator("poll_interval_seconds")
    @classmethod
    def validate_poll_interval_seconds(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("file_lock.poll_interval_seconds must be > 0")
        return float(v)


class SessionsConfig(BaseModel):
    """Client session subsystem configuration."""

    model_config = {"extra": "forbid"}

    show_session_ids: bool = Field(
        default=False,
        description=(
            "When False (default): session_list may be called without session_id "
            "and session_id is never included in output. "
            "When True: session_id is required in session_list and is included in output."
        ),
    )

    @field_validator("show_session_ids", mode="before")
    @classmethod
    def validate_show_session_ids(cls, v: object) -> object:
        """Validate show_session_ids is a boolean."""
        if not isinstance(v, bool):
            raise ValueError("sessions.show_session_ids must be a boolean")
        return v


class SecurityConfig(BaseModel):
    """Security policy configuration for MCP command access control."""

    model_config = {"extra": "forbid"}

    policy: Literal["disabled", "allowlist", "denylist"] = Field(
        default="disabled",
        description=(
            "Access control policy mode. "
            "disabled: no checks performed, all commands pass. "
            "allowlist: only commands explicitly granted via role_permissions are allowed. "
            "denylist: all commands permitted except those explicitly denied via role_permissions."
        ),
    )

    @field_validator("policy")
    @classmethod
    def validate_policy(cls, v: str) -> str:
        """Validate security policy mode."""
        allowed = {"disabled", "allowlist", "denylist"}
        if v not in allowed:
            raise ValueError(
                f"security.policy must be one of: {', '.join(sorted(allowed))}"
            )
        return v


class ServerConfig(BaseModel):
    """MCP server configuration."""

    model_config = {"extra": "forbid"}  # Reject unknown fields

    host: str = Field(
        default_factory=lambda: get_settings().get("server_host", DEFAULT_SERVER_HOST),
        description="Server host",
    )
    port: int = Field(
        default_factory=lambda: get_settings().get("server_port", DEFAULT_SERVER_PORT),
        description="Server port",
    )
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
    vector_search_backend: Optional[Literal["auto", "faiss", "pgvector"]] = Field(
        default="auto",
        description=(
            "Vector ANN backend: auto (PostgreSQL→pgvector, SQLite→FAISS), faiss, or pgvector. "
            "SQLite/sqlite_proxy always use FAISS regardless of this value."
        ),
    )
    min_chunk_length: int = Field(
        default_factory=lambda: get_settings().get(
            "min_chunk_length", DEFAULT_MIN_CHUNK_LENGTH
        ),
        description="Minimum text length for chunking. Shorter texts are grouped by level.",
    )
    vectorization_retry_attempts: int = Field(
        default_factory=lambda: get_settings().get(
            "retry_attempts", DEFAULT_RETRY_ATTEMPTS
        ),
        description="Number of retry attempts for vectorization on failure",
    )
    vectorization_retry_delay: float = Field(
        default_factory=lambda: get_settings().get("retry_delay", DEFAULT_RETRY_DELAY),
        description="Delay in seconds between vectorization retry attempts",
    )
    log_vectorization_chunker_trace: bool = Field(
        default=False,
        description="If true, log each chunker request/response (text preview, result, error) to logs/vectorization_chunker_trace.log",
    )
    allow_line_commands_on_healthy_files: bool = Field(
        default=False,
        description="If true, get_file_lines and replace_file_lines are allowed on files that parse successfully. If false (default), those commands return an error for healthy files and the client should use cst_load_file / cst_modify_tree / cst_save_tree instead.",
    )
    file_lock: FileLockConfig = Field(
        default_factory=FileLockConfig,
        description="Cooperative project-file advisory lock settings.",
    )
    worker: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {
            "enabled": True,
            "poll_interval": get_settings().get("poll_interval", DEFAULT_POLL_INTERVAL),
            "batch_size": get_settings().get("batch_size", DEFAULT_BATCH_SIZE),
            "retry_attempts": get_settings().get(
                "retry_attempts", DEFAULT_RETRY_ATTEMPTS
            ),
            "retry_delay": get_settings().get("retry_delay", DEFAULT_RETRY_DELAY),
            "watch_dirs": [],
            "log_path": get_settings().get(
                "vectorization_worker_log", DEFAULT_VECTORIZATION_WORKER_LOG
            ),
            "log_rotation": {
                "max_bytes": get_settings().get("log_max_bytes", DEFAULT_LOG_MAX_BYTES),
                "backup_count": get_settings().get(
                    "log_backup_count", DEFAULT_LOG_BACKUP_COUNT
                ),
            },
            "circuit_breaker": {
                "failure_threshold": get_settings().get(
                    "failure_threshold", DEFAULT_FAILURE_THRESHOLD
                ),
                "recovery_timeout": get_settings().get(
                    "recovery_timeout", DEFAULT_RECOVERY_TIMEOUT
                ),
                "success_threshold": get_settings().get(
                    "success_threshold", DEFAULT_SUCCESS_THRESHOLD
                ),
                "initial_backoff": get_settings().get(
                    "initial_backoff", DEFAULT_INITIAL_BACKOFF
                ),
                "max_backoff": get_settings().get("max_backoff", DEFAULT_MAX_BACKOFF),
                "backoff_multiplier": get_settings().get(
                    "backoff_multiplier", DEFAULT_BACKOFF_MULTIPLIER
                ),
            },
            "batch_processor": {
                "max_empty_iterations": get_settings().get(
                    "max_empty_iterations", DEFAULT_MAX_EMPTY_ITERATIONS
                ),
                "empty_delay": get_settings().get("empty_delay", DEFAULT_EMPTY_DELAY),
            },
        },
        description="Vectorization worker configuration",
    )
    file_watcher: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {
            "enabled": True,
            "scan_interval": get_settings().get("scan_interval", DEFAULT_SCAN_INTERVAL),
            "log_path": get_settings().get(
                "file_watcher_log", DEFAULT_FILE_WATCHER_LOG
            ),
            "log_rotation": {
                "max_bytes": get_settings().get("log_max_bytes", DEFAULT_LOG_MAX_BYTES),
                "backup_count": get_settings().get(
                    "log_backup_count", DEFAULT_LOG_BACKUP_COUNT
                ),
            },
            "version_dir": get_settings().get("versions_dir_name", VERSIONS_DIR_NAME),
            "max_scan_duration": get_settings().get(
                "max_scan_duration", DEFAULT_MAX_SCAN_DURATION
            ),
            "ignore_patterns": get_settings().get(
                "file_watcher_ignore_patterns", FILE_WATCHER_IGNORE_PATTERNS
            ),
        },
        description="File watcher worker configuration",
    )
    indexing_worker: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Indexing worker configuration (enabled, poll_interval, batch_size, log_path).",
    )
    batch_max_response_bytes: int = Field(
        default_factory=lambda: get_settings().get(
            "batch_max_response_bytes", DEFAULT_BATCH_MAX_RESPONSE_BYTES
        ),
        description="Max inline response size in bytes for read-only batch; above this, output goes to file. Must be finite (no bypass of overflow-to-file).",
    )
    batch_output_dir: str = Field(
        default_factory=lambda: get_settings().get(
            "batch_output_dir", DEFAULT_BATCH_OUTPUT_DIR
        ),
        description="Directory for oversized batch output files. Must comply with project writable path policy.",
    )
    batch_output_retention_seconds: int = Field(
        default_factory=lambda: get_settings().get(
            "batch_output_retention_seconds", DEFAULT_BATCH_OUTPUT_RETENTION_SECONDS
        ),
        description="Retention in seconds for batch output files; 0 means no automatic cleanup.",
    )
    read_project_text_json_structured_max_bytes: Optional[int] = Field(
        default=None,
        description=(
            "Optional max .json file size in bytes (st_size) for read_project_text_file to "
            "return structured JSON (same as json_load_file). Above this threshold, the "
            "command returns raw text lines. If omitted, DEFAULT_READ_PROJECT_TEXT_JSON_STRUCTURED_MAX_BYTES "
            "from code_analysis.core.constants is used."
        ),
    )
    venv_site_packages_index_allowlisted_distributions: List[str] = Field(
        default_factory=list,
        description=(
            "Optional list of pip distribution names (PEP 503–normalized matching). When "
            "non-empty, ``.py`` files under those distributions inside the project ``.venv``/``venv`` "
            "``site-packages`` trees may be indexed and vectorized; all other paths under "
            "``.venv``/``venv`` remain skipped. When empty, the entire project venv is excluded "
            "from indexing (default)."
        ),
    )
    ignore_exceptions: List[str] = Field(
        default_factory=list,
        description=(
            "Glob patterns relative to each project root. Matching ``.py`` files are included in "
            "indexing and file-watcher scans even when they would normally be excluded (e.g. under "
            "``.venv``/``venv``). Does not override default write restrictions for CST/text edits "
            "under the project venv."
        ),
    )
    docs_indexing: Optional[DocsIndexingConfig] = Field(
        default=None,
        description=(
            "Optional Markdown docs indexing (roots/include/exclude). Omitted or disabled: no "
            "docs eligibility. ``vectorize`` does not affect eligibility."
        ),
    )
    preview_full_text_max_lines: Optional[int] = Field(
        default=None,
        description=(
            "Maximum lines for full-text preview of Python files. "
            "None means use the server default (200). Set to 0 to disable full-text preview."
        ),
    )
    sessions: Optional[SessionsConfig] = Field(
        default=None,
        description="Client session subsystem configuration.",
    )
    security: Optional[SecurityConfig] = Field(
        default=None,
        description="Security policy configuration for MCP command access control.",
    )
    preview_max_chars_default: int = Field(
        default=32_000,
        description=(
            "Default max characters for universal_file_preview post-render pagination."
        ),
    )
    preview_value_preview_len_default: int = Field(
        default=120,
        description=(
            "Default max inline scalar/name length for universal_file_preview summaries."
        ),
    )
    grep_line_preview_len_default: int = Field(
        default=120,
        description="Default max line preview length returned by fs_grep.",
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
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return str(log_path.resolve())

    @field_validator("db_path")
    @classmethod
    def validate_db_path(cls, v: Optional[str]) -> Optional[str]:
        """Validate database path."""
        if v is None:
            return None
        db_path = Path(v)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return str(db_path.resolve())

    @field_validator("faiss_index_path")
    @classmethod
    def validate_faiss_index_path(cls, v: Optional[str]) -> Optional[str]:
        """Validate FAISS index path."""
        if v is None:
            return None
        index_path = Path(v)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        return str(index_path.resolve())

    @field_validator("vector_dim")
    @classmethod
    def validate_vector_dim(cls, v: Optional[int]) -> Optional[int]:
        """Validate vector dimension."""
        if v is not None and v <= 0:
            raise ValueError("Vector dimension must be positive")
        return v

    @field_validator("vector_search_backend")
    @classmethod
    def validate_vector_search_backend(
        cls, v: Optional[str]
    ) -> Optional[Literal["auto", "faiss", "pgvector"]]:
        """Allow only known backend keywords."""
        if v is None:
            return "auto"
        s = str(v).strip().lower()
        if s not in ("auto", "faiss", "pgvector"):
            raise ValueError(
                "vector_search_backend must be one of: auto, faiss, pgvector"
            )
        return s  # type: ignore[return-value]

    @field_validator("batch_max_response_bytes")
    @classmethod
    def validate_batch_max_response_bytes(cls, v: int) -> int:
        """Ensure finite threshold; no hidden default that bypasses overflow-to-file."""
        if v <= 0:
            raise ValueError(
                "batch_max_response_bytes must be positive (overflow-to-file contract)"
            )
        return v

    @field_validator(
        "preview_max_chars_default",
        "preview_value_preview_len_default",
        "grep_line_preview_len_default",
    )
    @classmethod
    def validate_positive_preview_defaults(cls, v: int) -> int:
        if v < 1:
            raise ValueError("preview/grep length defaults must be >= 1")
        return v

    @field_validator("batch_output_dir")
    @classmethod
    def validate_batch_output_dir(cls, v: str) -> str:
        """Resolve absolute paths and enforce writable path policy (no system dirs)."""
        if not v or not v.strip():
            raise ValueError("batch_output_dir cannot be empty")
        path = Path(v.strip()).expanduser()
        if not path.is_absolute():
            # Resolved at runtime against config directory (see storage_paths).
            return v.strip()
        path = path.resolve()
        forbidden_prefixes = (
            "/etc",
            "/usr",
            "/bin",
            "/sbin",
            "/sys",
            "/proc",
            "/root",
            "/boot",
            "/lib",
            "/lib64",
            "/dev",
        )
        path_str = str(path)
        for prefix in forbidden_prefixes:
            if path_str == prefix or path_str.startswith(prefix + "/"):
                raise ValueError(
                    f"batch_output_dir must not be under system path: {prefix}"
                )
        if path_str == "/":
            raise ValueError("batch_output_dir must not be filesystem root")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path_str

    @field_validator("batch_output_retention_seconds")
    @classmethod
    def validate_batch_output_retention_seconds(cls, v: int) -> int:
        """Retention must be non-negative."""
        if v < 0:
            raise ValueError("batch_output_retention_seconds must be >= 0")
        return v

    @field_validator("read_project_text_json_structured_max_bytes")
    @classmethod
    def validate_read_project_text_json_structured_max_bytes(
        cls, v: Optional[int]
    ) -> Optional[int]:
        """When set, must be positive (bytes threshold for structured .json read)."""
        if v is not None and v <= 0:
            raise ValueError(
                "read_project_text_json_structured_max_bytes must be positive when set"
            )
        return v

    @field_validator("venv_site_packages_index_allowlisted_distributions")
    @classmethod
    def validate_venv_site_packages_index_allowlisted_distributions(
        cls,
        v: List[str],
    ) -> List[str]:
        """Allowlist entries must be non-empty strings (distribution names)."""
        if not v:
            return []
        out: List[str] = []
        for item in v:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(
                    "venv_site_packages_index_allowlisted_distributions entries must be "
                    "non-empty strings"
                )
            out.append(item.strip())
        return out

    @field_validator("ignore_exceptions")
    @classmethod
    def validate_ignore_exceptions(cls, v: List[str]) -> List[str]:
        """Ignore-exception glob patterns must be non-empty strings when present."""
        if not v:
            return []
        out: List[str] = []
        for item in v:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("ignore_exceptions entries must be non-empty strings")
            out.append(item.strip())
        return out
