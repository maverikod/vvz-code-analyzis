"""
Project-wide constants.

This module contains all constants used across the codebase to avoid hardcoded values.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Set

# ============================================================================
# File Extensions
# ============================================================================

# File extensions to process
CODE_FILE_EXTENSIONS: Set[str] = {".py", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}

# Configuration file extensions
CONFIG_FILE_EXTENSIONS: Set[str] = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}


# ============================================================================
# Ignore Patterns
# ============================================================================

# Default patterns to ignore (always applied)
DEFAULT_IGNORE_PATTERNS: Set[str] = {
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    ".venv",
    "venv",
    "data/versions",  # Version directory for deleted files
    "data/versions/**",  # All subdirectories in versions
    "*.pyc",
}

# Git ignore patterns (additional patterns for .gitignore)
GIT_IGNORE_PATTERNS: Set[str] = {
    "__pycache__/",
    "*.py[cod]",
    "*$py.class",
    "*.so",
    ".Python",
    "build/",
    "develop-eggs/",
    "dist/",
    "downloads/",
    "eggs/",
    ".eggs/",
    "lib/",
    "lib64/",
    "parts/",
    "sdist/",
    "var/",
    "wheels/",
    "*.egg-info/",
    ".installed.cfg",
    "*.egg",
    ".venv/",
    "venv/",
    "ENV/",
    "env/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".coverage",
    "htmlcov/",
    ".tox/",
    ".cache",
    "*.log",
    "data/",
    "logs/",
}


# ============================================================================
# File and Directory Names
# ============================================================================

# Project identification file name
PROJECTID_FILENAME: str = "projectid"

# Git directory name
GIT_DIR_NAME: str = ".git"

# Git ignore file name
GITIGNORE_FILENAME: str = ".gitignore"

# Version directory name (relative to project root)
VERSIONS_DIR_NAME: str = "data/versions"

# Locks directory name (relative to config directory)
LOCKS_DIR_NAME: str = "data/locks"

# Logs directory name (relative to project root)
LOGS_DIR_NAME: str = "logs"

# Data directory name (relative to project root)
DATA_DIR_NAME: str = "data"


# ============================================================================
# Sizes and Limits
# ============================================================================

# Maximum lines in a file before splitting is recommended
DEFAULT_MAX_FILE_LINES: int = 400

# Minimum text length for chunking
DEFAULT_MIN_CHUNK_LENGTH: int = 30

# Maximum log file size in bytes (10 MB)
DEFAULT_LOG_MAX_BYTES: int = 10485760

# Number of backup log files to keep
DEFAULT_LOG_BACKUP_COUNT: int = 5

# Default vector dimension for embeddings
DEFAULT_VECTOR_DIM: int = 384

# File modification time tolerance in seconds (for comparison)
FILE_MODIFICATION_TOLERANCE: float = 0.1

# Epsilon for updating last_modified timestamp
LAST_MODIFIED_EPSILON: float = 0.001


# ============================================================================
# Timeouts and Intervals
# ============================================================================

# Default poll interval in seconds
DEFAULT_POLL_INTERVAL: int = 30

# Default scan interval in seconds
DEFAULT_SCAN_INTERVAL: int = 60

# Default retry attempts count
DEFAULT_RETRY_ATTEMPTS: int = 3

# Default retry delay in seconds
DEFAULT_RETRY_DELAY: float = 10.0

# Default command timeout in seconds
DEFAULT_COMMAND_TIMEOUT: float = 60.0

# Default git command timeout in seconds
DEFAULT_GIT_TIMEOUT: float = 10.0

# Proxy driver poll interval in seconds
PROXY_DRIVER_POLL_INTERVAL: float = 1.0

# Maximum retries for database connection
DB_CONNECTION_MAX_RETRIES: int = 5

# Delay between database connection retries in seconds
DB_CONNECTION_RETRY_DELAY: float = 2.0

# Maximum scan duration in seconds
DEFAULT_MAX_SCAN_DURATION: int = 300


# ============================================================================
# Analysis Patterns
# ============================================================================

# Placeholder patterns for code analysis
PLACEHOLDER_PATTERNS: list[str] = [
    "TODO",
    "FIXME",
    "XXX",
    "HACK",
    "NOTE",
    "BUG",
    "OPTIMIZE",
    "PLACEHOLDER",
    "STUB",
    "NOT IMPLEMENTED",
]

# Stub patterns (functions/methods with pass, ellipsis, NotImplementedError)
STUB_PATTERNS: list[str] = [
    "pass",
    "...",
    "NotImplementedError",
    "raise NotImplementedError",
]


# ============================================================================
# Ports and Hosts
# ============================================================================

# Default server host
DEFAULT_SERVER_HOST: str = "0.0.0.0"

# Default server port
DEFAULT_SERVER_PORT: int = 15000

# Default chunker service port
DEFAULT_CHUNKER_PORT: int = 8009

# Default embedding service port
DEFAULT_EMBEDDING_PORT: int = 8001

# Default localhost
DEFAULT_LOCALHOST: str = "localhost"


# ============================================================================
# Circuit Breaker
# ============================================================================

# Default failure threshold for circuit breaker
DEFAULT_FAILURE_THRESHOLD: int = 5

# Default recovery timeout in seconds
DEFAULT_RECOVERY_TIMEOUT: float = 60.0

# Default success threshold for circuit breaker
DEFAULT_SUCCESS_THRESHOLD: int = 2

# Default initial backoff in seconds
DEFAULT_INITIAL_BACKOFF: float = 5.0

# Default maximum backoff in seconds
DEFAULT_MAX_BACKOFF: float = 300.0

# Default backoff multiplier
DEFAULT_BACKOFF_MULTIPLIER: float = 2.0


# ============================================================================
# Batch Processor
# ============================================================================

# Default batch size
DEFAULT_BATCH_SIZE: int = 10

# Default maximum empty iterations
DEFAULT_MAX_EMPTY_ITERATIONS: int = 3

# Default empty delay in seconds
DEFAULT_EMPTY_DELAY: float = 5.0


# ============================================================================
# File Paths (relative to project root or config directory)
# ============================================================================

# Default database path (relative to config directory)
DEFAULT_DB_PATH: str = "data/code_analysis.db"

# Default FAISS directory (relative to config directory)
DEFAULT_FAISS_DIR: str = "data/faiss"

# Default dynamic watch file path (relative to project root)
DEFAULT_DYNAMIC_WATCH_FILE: str = "data/dynamic_watch_dirs.json"

# Default vectorization worker log path (relative to project root)
DEFAULT_VECTORIZATION_WORKER_LOG: str = "logs/vectorization_worker.log"

# Default file watcher log path (relative to project root)
DEFAULT_FILE_WATCHER_LOG: str = "logs/file_watcher.log"


# ============================================================================
# Database Driver
# ============================================================================

# Default database driver type
DEFAULT_DB_DRIVER_TYPE: str = "sqlite_proxy"


# ============================================================================
# File Watcher Ignore Patterns (for config)
# ============================================================================

# Default ignore patterns for file watcher (glob patterns)
FILE_WATCHER_IGNORE_PATTERNS: list[str] = [
    "**/__pycache__/**",
    "**/.git/**",
    "**/node_modules/**",
]

