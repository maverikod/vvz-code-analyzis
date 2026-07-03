"""
Constants for config validator (allowed keys, etc.).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.core.config import ServerConfig

# Allowed keys in code_analysis section: ServerConfig fields + "database" (driver only).
# Config must contain only what is used in code.
ALLOWED_CODE_ANALYSIS_KEYS = frozenset(ServerConfig.model_fields) | {
    "database",
    "search_session",
    "all_logs_rotation",
    "git_commit_on_write",
    "github",
    "storage",
}
