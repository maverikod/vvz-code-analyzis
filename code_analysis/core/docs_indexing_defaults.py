"""
Default values and helpers for ``code_analysis.docs_indexing`` (single source of truth).

Used by config generator, JSON validator, and runtime eligibility.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Final, FrozenSet, Tuple

DEFAULT_DOCS_INDEXING_ENABLED: Final[bool] = False
DEFAULT_DOCS_INDEXING_VECTORIZE: Final[bool] = False

# Eligible documentation file suffixes (lowercase, with leading dot).
DOCS_INDEX_FILE_SUFFIXES: Final[Tuple[str, ...]] = (".md", ".json", ".yaml", ".yml")

# Tuple defaults — copied to mutable lists where JSON / pydantic needs lists.
DEFAULT_DOCS_INDEXING_ROOTS: Final[tuple[str, ...]] = ("docs",)
DEFAULT_DOCS_INDEXING_INCLUDE: Final[tuple[str, ...]] = (
    "docs/**/*.md",
    "docs/*.md",
    "docs/**/*.json",
    "docs/*.json",
    "docs/**/*.yaml",
    "docs/**/*.yml",
    "docs/*.yaml",
    "docs/*.yml",
    "README.md",
)
DEFAULT_DOCS_INDEXING_EXCLUDE: Final[tuple[str, ...]] = (
    "docs/plans/**",
    "docs/ai_reports/**",
)

ALLOWED_DOCS_INDEXING_KEYS: FrozenSet[str] = frozenset(
    {"enabled", "vectorize", "roots", "include", "exclude"}
)


def docs_include_pattern_mentions_indexed_suffix(pattern: str) -> bool:
    """True if a glob pattern string mentions an indexed documentation extension."""
    low = str(pattern).strip().lower()
    return any(ext in low for ext in DOCS_INDEX_FILE_SUFFIXES)


def default_docs_indexing_dict() -> Dict[str, Any]:
    """Serializable defaults for generator and docs (Markdown/JSON/YAML, indexing/vectorize off)."""
    return {
        "enabled": DEFAULT_DOCS_INDEXING_ENABLED,
        "vectorize": DEFAULT_DOCS_INDEXING_VECTORIZE,
        "roots": list(DEFAULT_DOCS_INDEXING_ROOTS),
        "include": list(DEFAULT_DOCS_INDEXING_INCLUDE),
        "exclude": list(DEFAULT_DOCS_INDEXING_EXCLUDE),
    }
