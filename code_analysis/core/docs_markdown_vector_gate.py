"""
Markdown docs chunks (Group E): discriminator and ``docs_indexing.vectorize`` policy.

Chunks from the ``.md`` / ``DocBlock`` path use ``source_type == \"docs_markdown\"``.
When ``docs_indexing.enabled`` and not ``docs_indexing.vectorize``, embeddings and
FAISS must not apply to those rows (policy is global server config).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

DOCS_MARKDOWN_SOURCE_TYPE = "docs_markdown"


def is_docs_markdown_chunk(
    *,
    source_type: Optional[str] = None,
    chunk: Optional[Mapping[str, Any]] = None,
) -> bool:
    """Return True when the row is from the Markdown docs chunking path (Group E)."""
    if chunk is not None:
        return str(chunk.get("source_type") or "") == DOCS_MARKDOWN_SOURCE_TYPE
    return (source_type or "") == DOCS_MARKDOWN_SOURCE_TYPE


def docs_markdown_embeddings_disabled_by_policy(docs_indexing: Any) -> bool:
    """
    True when config says Markdown docs may be indexed but must not be embedded.

    When ``docs_indexing`` is absent or not enabled, this is False (no gate).
    When ``enabled`` is true, ``vectorize`` defaults false if omitted (generator default).
    """
    if docs_indexing is None or not isinstance(docs_indexing, dict):
        return False
    if not bool(docs_indexing.get("enabled")):
        return False
    return not bool(docs_indexing.get("vectorize", False))


def docs_markdown_embeddings_enabled_from_code_analysis_section(
    code_analysis_cfg: Mapping[str, Any],
) -> bool:
    """Prefer True unless ``docs_indexing`` policy disables Markdown doc embeddings."""
    di = code_analysis_cfg.get("docs_indexing")
    return not docs_markdown_embeddings_disabled_by_policy(di)


def docs_markdown_embeddings_enabled_from_server_config_mapping(
    raw: Mapping[str, Any],
) -> bool:
    """Resolve from top-level JSON (``code_analysis`` section). Missing → True."""
    ca = raw.get("code_analysis")
    if not isinstance(ca, dict):
        return True
    return docs_markdown_embeddings_enabled_from_code_analysis_section(ca)


def sql_and_exclude_docs_markdown_chunks(table_alias: str = "cc") -> str:
    """SQL fragment excluding ``docs_markdown`` rows (leading space)."""
    return (
        f" AND ({table_alias}.source_type IS NULL OR "
        f"{table_alias}.source_type != '{DOCS_MARKDOWN_SOURCE_TYPE}') "
    )
