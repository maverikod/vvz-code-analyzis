"""
Docstring extraction and chunk persistence.

This module implements `DocstringChunker`, a minimal and robust docstring
extractor used by the vectorization worker.

The worker expects:
- `DocstringChunker.process_file(...)` to insert docstring chunks into DB
- chunks to be stored in `code_chunks` with `source_type` like "docstring"
- optionally precomputed `embedding_vector` to speed up vectorization

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _DocItem:
    """Internal representation of an extracted doc item."""

    source_type: str
    chunk_type: str
    text: str
    line: int
    ast_node_type: str
    binding_level: int


class DocstringChunker:
    """
    Extract docstrings from a Python AST and store them as `code_chunks`.

    Notes:
        - This implementation focuses on docstrings only (module/class/function/method).
        - It does not depend on external chunker services.
        - If `svo_client_manager` is provided, it precomputes embeddings using the
          manager's `get_embeddings(...)` (requires real embedding service).

    Attributes:
        database: CodeDatabase instance.
        svo_client_manager: Optional embedding client manager.
        faiss_manager: Optional FAISS manager (not used directly here).
        min_chunk_length: Minimum length of docstring text to store.
        embedding_model: Name stored in DB for produced embeddings.
    """

    def __init__(
        self,
        database: Any,
        svo_client_manager: Optional[Any] = None,
        faiss_manager: Optional[Any] = None,
        min_chunk_length: int = 30,
        embedding_model: Optional[str] = None,
    ) -> None:
        """
        Initialize docstring chunker.

        Args:
            database: CodeDatabase instance.
            svo_client_manager: SVO client manager for embeddings (optional).
            faiss_manager: FAISS index manager (optional, reserved for future use).
            min_chunk_length: Minimum text length to store (default: 30).
            embedding_model: Embedding model identifier stored in DB.
        """

        self.database = database
        self.svo_client_manager = svo_client_manager
        self.faiss_manager = faiss_manager
        self.min_chunk_length = int(min_chunk_length)
        self.embedding_model = embedding_model

    async def process_file(
        self,
        *,
        file_id: int,
        project_id: str,
        file_path: str,
        tree: ast.AST,
        file_content: str,
    ) -> int:
        """
        Extract docstrings from the AST and persist them into the database.

        Args:
            file_id: Database file ID.
            project_id: Project UUID.
            file_path: Path to file (used for diagnostics only).
            tree: Parsed AST tree.
            file_content: Original file content (used only for module docstring safety).

        Returns:
            Number of chunks inserted/updated.
        """

        if not isinstance(tree, ast.Module):
            logger.debug("Skipping non-module AST for %s", file_path)
            return 0

        items = list(self._extract_docstrings(tree, file_content))
        if not items:
            return 0

        # Precompute embeddings using chunker service (SVO - chunks and vectorizes)
        embeddings: list[Optional[list[float]]] = [None] * len(items)
        if self.svo_client_manager:
            try:
                # Use chunker service for each docstring - it returns chunks with embeddings
                for i, item in enumerate(items):
                    try:
                        # Call chunker service - it chunks and vectorizes
                        chunks = await self.svo_client_manager.get_chunks(
                            text=item.text, type="DocBlock"
                        )
                        # Extract embedding from first chunk (chunker returns chunks with embeddings)
                        if chunks and len(chunks) > 0:
                            first_chunk = chunks[0]
                            # SemanticChunk from svo_client has embedding attribute
                            emb = getattr(first_chunk, "embedding", None)
                            if isinstance(emb, list) and emb:
                                embeddings[i] = emb
                            elif hasattr(first_chunk, "vector") and first_chunk.vector:
                                # Alternative: check for vector attribute
                                embeddings[i] = first_chunk.vector
                    except Exception as e:
                        logger.warning(
                            "Failed to get chunks with embeddings for docstring %d in %s: %s (continuing without embedding)",
                            i,
                            file_path,
                            e,
                        )
                        # Continue without embedding - chunk will be saved without embedding
                        embeddings[i] = None
            except Exception as e:
                # If chunking fails, log warning but continue - chunks will be saved without embeddings
                logger.warning(
                    "Failed to precompute embeddings for docstrings in %s: %s (continuing without embeddings)",
                    file_path,
                    e,
                )
                # Continue processing - chunks will be saved without embeddings

        # Persist items
        written = 0
        ordinal = 0
        for it, emb in zip(items, embeddings):
            ordinal += 1
            if len(it.text) < self.min_chunk_length:
                continue

            # Stable UUID to avoid duplicating chunks across repeated worker cycles.
            # This allows `add_or_update_code_chunk` to update instead of always inserting.
            text_sig = hashlib.sha1(it.text.encode("utf-8")).hexdigest()
            uuid_name = (
                f"{file_id}:{it.ast_node_type}:{it.line}:{it.source_type}:{text_sig}"
            )
            chunk_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, uuid_name))
            embedding_json: Optional[str] = None
            embedding_model: Optional[str] = None
            if emb is not None:
                embedding_json = json.dumps(emb)
                embedding_model = self.embedding_model

            try:
                await self.database.add_code_chunk(
                    file_id=file_id,
                    project_id=project_id,
                    chunk_uuid=chunk_uuid,
                    chunk_type=it.chunk_type,
                    chunk_text=it.text,
                    chunk_ordinal=ordinal,
                    vector_id=None,
                    embedding_model=embedding_model,
                    bm25_score=None,
                    embedding_vector=embedding_json,
                    class_id=None,
                    function_id=None,
                    method_id=None,
                    line=int(it.line),
                    ast_node_type=it.ast_node_type,
                    source_type=it.source_type,
                    binding_level=int(it.binding_level),
                )
                written += 1
            except Exception as e:
                logger.warning(
                    "Failed to persist docstring chunk for %s (line=%s): %s",
                    file_path,
                    it.line,
                    e,
                    exc_info=True,
                )

        return written

    def _extract_docstrings(
        self, tree: ast.Module, file_content: str
    ) -> Iterable[_DocItem]:
        """
        Extract docstrings from module/class/function nodes.

        Args:
            tree: Parsed module.
            file_content: Original file content.

        Yields:
            _DocItem entries.
        """

        # Module docstring
        module_doc = ast.get_docstring(tree)
        if module_doc:
            yield _DocItem(
                source_type="file_docstring",
                chunk_type="DocBlock",
                text=module_doc,
                line=1,
                ast_node_type="Module",
                binding_level=1,
            )

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                doc = self._safe_get_docstring(node)
                if doc:
                    yield _DocItem(
                        source_type="docstring",
                        chunk_type="DocBlock",
                        text=doc,
                        line=int(getattr(node, "lineno", 1) or 1),
                        ast_node_type="ClassDef",
                        binding_level=2,
                    )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = self._safe_get_docstring(node)
                if not doc:
                    continue

                binding_level = 3
                node_type = "FunctionDef"
                yield _DocItem(
                    source_type="docstring",
                    chunk_type="DocBlock",
                    text=doc,
                    line=int(getattr(node, "lineno", 1) or 1),
                    ast_node_type=node_type,
                    binding_level=binding_level,
                )

    @staticmethod
    def _safe_get_docstring(node: ast.AST) -> Optional[str]:
        """Safely get a docstring for nodes that support it."""

        try:
            return ast.get_docstring(node)  # type: ignore[arg-type]
        except Exception:
            return None


class _DummyChunk:
    """Chunk-like object for embedding API compatibility."""

    def __init__(self, text: str) -> None:
        self.body = text
        self.text = text
