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
import asyncio
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE

from ..exceptions import ChunkerResponseError
from ..vectorization_worker_pkg.timing_log import log_operation_timing

logger = logging.getLogger(__name__)

# Max docstring texts per single ``get_chunks_batch`` RPC (multi-file prepared path).
DOCSTRING_CHUNK_BATCH_MAX_TEXTS = 128

# SQL for INSERT OR REPLACE code_chunks (same as DatabaseClient.add_code_chunk).
_INSERT_CODE_CHUNK_SQL = """
    INSERT OR REPLACE INTO code_chunks
    (
        file_id, project_id, chunk_uuid, chunk_type, chunk_text,
        chunk_ordinal, vector_id, embedding_model, bm25_score,
        embedding_vector, token_count, class_id, function_id, method_id,
        line, ast_node_type, source_type, binding_level,
        updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, julianday('now'))
"""


def _chunk_text_from_svo(chunk: Any) -> str:
    """Get text/body from svo_client chunk (SemanticChunk)."""
    if hasattr(chunk, "body") and getattr(chunk, "body") is not None:
        return str(getattr(chunk, "body"))
    if hasattr(chunk, "text") and getattr(chunk, "text") is not None:
        return str(getattr(chunk, "text"))
    return ""


def _token_count_from_text(text: str) -> int:
    """Heuristic token count (words). Use chunker token_count if available."""
    return len(text.split()) if text else 0


@dataclass(frozen=True)
class _DocItem:
    """Internal representation of an extracted doc item."""

    source_type: str
    chunk_type: str
    text: str
    line: int
    ast_node_type: str
    binding_level: int


@dataclass(frozen=True)
class PreparedDocstringFile:
    """One file ready for multi-file docstring chunking (``process_prepared_files``)."""

    file_id: int
    project_id: str
    file_path: str
    tree: ast.Module
    file_content: str
    items: List[_DocItem]


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
        log_timing: bool = False,
    ) -> None:
        """
        Initialize docstring chunker.

        Args:
            database: CodeDatabase instance.
            svo_client_manager: SVO client manager for embeddings (optional).
            faiss_manager: FAISS index manager (optional, reserved for future use).
            min_chunk_length: Minimum text length to store (default: 30).
            embedding_model: Embedding model identifier stored in DB.
            log_timing: When True, log every operation with duration for bottleneck analysis.
        """

        self.database = database
        self.svo_client_manager = svo_client_manager
        self.faiss_manager = faiss_manager
        self.min_chunk_length = int(min_chunk_length)
        self.embedding_model = embedding_model
        self.log_timing = log_timing

    def _file_still_exists_and_not_deleted(self, file_id: int, project_id: str) -> bool:
        """
        Check if file and project still exist and file is not marked deleted.

        Used before and during chunk persistence to avoid writing chunks when
        the file or project has been removed (or file marked deleted) in the meantime.

        Returns:
            True if file exists, belongs to project, and is not deleted; False otherwise.
        """
        if hasattr(self.database, "_fetchone"):
            row = self.database._fetchone(
                "SELECT 1 FROM files WHERE id = ? AND project_id = ? AND "
                + WHERE_FILES_ACTIVE,
                (file_id, project_id),
            )
            return row is not None
        r = self.database.execute(
            "SELECT 1 FROM files WHERE id = ? AND project_id = ? AND "
            + WHERE_FILES_ACTIVE,
            (file_id, project_id),
        )
        data = r.get("data", []) if isinstance(r, dict) else []
        return len(data) > 0

    def _rows_from_item_and_chunks(
        self,
        item: _DocItem,
        chunks: List[Any],
    ) -> List[
        Tuple[
            _DocItem,
            int,
            str,
            Optional[List[float]],
            Optional[str],
            Optional[int],
        ]
    ]:
        """Build persist rows for one doc item from SVO chunk objects (or [])."""
        rows: List[
            Tuple[
                _DocItem,
                int,
                str,
                Optional[List[float]],
                Optional[str],
                Optional[int],
            ]
        ] = []
        if chunks:
            chunk_embedding_model: Optional[str] = None
            for j, ch in enumerate(chunks):
                chunk_text = _chunk_text_from_svo(ch)
                emb = getattr(ch, "embedding", None)
                if emb is None and hasattr(ch, "vector"):
                    emb = ch.vector
                if chunk_embedding_model is None:
                    chunk_embedding_model = getattr(ch, "embedding_model", None)
                tc = getattr(ch, "token_count", None)
                if tc is None and chunk_text:
                    tc = _token_count_from_text(chunk_text)
                rows.append(
                    (item, j, chunk_text, emb, chunk_embedding_model, tc),
                )
            if chunk_embedding_model and not self.embedding_model:
                self.embedding_model = chunk_embedding_model
        else:
            tc = _token_count_from_text(item.text)
            rows.append(
                (item, 0, item.text, None, None, tc if tc else None),
            )
        return rows

    def _build_insert_ops_for_docstring_rows(
        self,
        file_id: int,
        project_id: str,
        file_path: str,
        rows_to_persist: List[
            Tuple[
                _DocItem,
                int,
                str,
                Optional[List[float]],
                Optional[str],
                Optional[int],
            ]
        ],
    ) -> List[Tuple[str, Tuple[Any, ...]]]:
        """Turn resolved chunk rows into INSERT OR REPLACE ops for ``code_chunks``."""
        insert_ops: List[Tuple[str, Tuple[Any, ...]]] = []
        ordinal = 0
        for (
            it,
            chunk_index,
            chunk_text,
            emb,
            _chunk_embedding_model,
            token_count,
        ) in rows_to_persist:
            if not self._file_still_exists_and_not_deleted(file_id, project_id):
                logger.warning(
                    f"[FILE {file_id}] File or project deleted during persist, "
                    f"stopping after {len(insert_ops)} chunks for {file_path}"
                )
                break
            ordinal += 1
            text_sig = hashlib.sha1(chunk_text.encode("utf-8")).hexdigest()
            uuid_name = (
                f"{file_id}:{it.ast_node_type}:{it.line}:{it.source_type}:"
                f"{chunk_index}:{text_sig}"
            )
            chunk_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, uuid_name))
            embedding_json: Optional[str] = None
            embedding_model: Optional[str] = None
            if emb is not None:
                model = self.embedding_model and str(self.embedding_model).strip()
                if model:
                    embedding_json = json.dumps(emb)
                    embedding_model = model
                else:
                    msg = (
                        "Chunker returned chunk with embedding but no model name. "
                        "Chunker server must include 'model' or 'embedding_model' in each chunk."
                    )
                    err = ChunkerResponseError(
                        msg + " See docs/CHUNKER_MODEL_FIELD.md",
                        file_path=file_path,
                        details={"file_id": file_id, "line": it.line},
                    )
                    logger.critical(
                        "%s (file_path=%s, file_id=%s, line=%s)",
                        err.message,
                        file_path,
                        file_id,
                        it.line,
                    )
                    raise err
            params = (
                file_id,
                project_id,
                chunk_uuid,
                it.chunk_type,
                chunk_text,
                ordinal,
                None,
                embedding_model,
                None,
                embedding_json,
                token_count,
                None,
                None,
                None,
                int(it.line),
                it.ast_node_type,
                it.source_type,
                int(it.binding_level),
            )
            insert_ops.append((_INSERT_CODE_CHUNK_SQL.strip(), params))
        return insert_ops

    async def _fetch_rows_for_item_with_get_chunks(self, item: _DocItem) -> List[
        Tuple[
            _DocItem,
            int,
            str,
            Optional[List[float]],
            Optional[str],
            Optional[int],
        ]
    ]:
        """Single-docstring path using ``get_chunks`` (matches ``process_file`` fallback)."""
        rows_to_persist: List[
            Tuple[
                _DocItem,
                int,
                str,
                Optional[List[float]],
                Optional[str],
                Optional[int],
            ]
        ] = []
        mgr = self.svo_client_manager
        if not mgr:
            tc = _token_count_from_text(item.text)
            return [(item, 0, item.text, None, None, tc if tc else None)]
        try:
            t0_one = time.time()
            chunks = await mgr.get_chunks(text=item.text, type="DocBlock")
            log_operation_timing(
                getattr(self, "log_timing", False),
                logger,
                "get_chunks_one",
                time.time() - t0_one,
            )
            if chunks and len(chunks) > 0:
                return self._rows_from_item_and_chunks(item, list(chunks))
            tc = _token_count_from_text(item.text)
            return [(item, 0, item.text, None, None, tc if tc else None)]
        except Exception as e:
            logger.warning(
                "Failed to get chunks for single docstring: %s (persisting without embedding)",
                e,
            )
            tc = _token_count_from_text(item.text)
            return [(item, 0, item.text, None, None, tc if tc else None)]

    async def process_prepared_files(
        self, prepared: List[PreparedDocstringFile]
    ) -> Dict[int, int]:
        """
        Process multiple prepared files using ``get_chunks_batch`` when available.

        Batches docstrings across files (flat order) up to
        :data:`DOCSTRING_CHUNK_BATCH_MAX_TEXTS`, then persists all inserts in one
        logical write batch when supported.
        """
        counts: Dict[int, int] = {pf.file_id: 0 for pf in prepared}
        flat: List[Tuple[PreparedDocstringFile, _DocItem]] = []
        for pf in prepared:
            for it in pf.items:
                flat.append((pf, it))
        if not flat:
            return counts

        all_insert_ops: List[Tuple[str, Tuple[Any, ...]]] = []
        idx = 0
        max_t = DOCSTRING_CHUNK_BATCH_MAX_TEXTS
        while idx < len(flat):
            seg = flat[idx : idx + max_t]
            idx += len(seg)
            if not self.svo_client_manager:
                for pf, item in seg:
                    if not self._file_still_exists_and_not_deleted(
                        pf.file_id, pf.project_id
                    ):
                        continue
                    rows = self._rows_from_item_and_chunks(item, [])
                    all_insert_ops.extend(
                        self._build_insert_ops_for_docstring_rows(
                            pf.file_id,
                            pf.project_id,
                            pf.file_path,
                            rows,
                        )
                    )
                continue

            get_batch = getattr(self.svo_client_manager, "get_chunks_batch", None)
            if not callable(get_batch):
                for pf, item in seg:
                    if not self._file_still_exists_and_not_deleted(
                        pf.file_id, pf.project_id
                    ):
                        continue
                    rows = await self._fetch_rows_for_item_with_get_chunks(item)
                    all_insert_ops.extend(
                        self._build_insert_ops_for_docstring_rows(
                            pf.file_id,
                            pf.project_id,
                            pf.file_path,
                            rows,
                        )
                    )
                continue

            texts = [it.text for _, it in seg]
            batch_results: Optional[List[Any]] = None
            try:
                t0_batch = time.time()
                batch_results = await get_batch(texts, type="DocBlock")
                log_operation_timing(
                    getattr(self, "log_timing", False),
                    logger,
                    "get_chunks_batch",
                    time.time() - t0_batch,
                    texts=len(texts),
                )
            except Exception as e:
                logger.warning(
                    "process_prepared_files: get_chunks_batch failed: %s; "
                    "falling back to per-item get_chunks",
                    e,
                )
                for pf, item in seg:
                    if not self._file_still_exists_and_not_deleted(
                        pf.file_id, pf.project_id
                    ):
                        continue
                    rows = await self._fetch_rows_for_item_with_get_chunks(item)
                    all_insert_ops.extend(
                        self._build_insert_ops_for_docstring_rows(
                            pf.file_id,
                            pf.project_id,
                            pf.file_path,
                            rows,
                        )
                    )

            if batch_results is not None:
                for k, (pf, item) in enumerate(seg):
                    if not self._file_still_exists_and_not_deleted(
                        pf.file_id, pf.project_id
                    ):
                        continue
                    chunks: List[Any] = []
                    if k < len(batch_results) and batch_results[k] is not None:
                        chunks = list(batch_results[k])
                    rows = self._rows_from_item_and_chunks(item, chunks)
                    all_insert_ops.extend(
                        self._build_insert_ops_for_docstring_rows(
                            pf.file_id,
                            pf.project_id,
                            pf.file_path,
                            rows,
                        )
                    )

        if not all_insert_ops:
            return counts

        lw = getattr(self.database, "execute_logical_write_operation", None)
        if callable(lw):
            program = {"batches": [all_insert_ops]}
            if asyncio.iscoroutinefunction(lw):
                await lw(program)
            else:
                await asyncio.to_thread(lw, program)
        else:
            execute_batch = self.database.execute_batch
            if asyncio.iscoroutinefunction(execute_batch):
                await execute_batch(all_insert_ops)
            else:
                await asyncio.to_thread(execute_batch, all_insert_ops)

        for _sql, params in all_insert_ops:
            fid = int(params[0])
            counts[fid] = counts.get(fid, 0) + 1
        return counts

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
        process_start_time = time.time()
        logger.info(f"[FILE {file_id}] Starting process_file for {file_path}")

        if not isinstance(tree, ast.Module):
            logger.debug("Skipping non-module AST for %s", file_path)
            return 0

        items = list(self._extract_docstrings(tree, file_content))
        logger.info(
            f"[FILE {file_id}] Extracted {len(items)} docstrings from {file_path}"
        )
        if not items:
            return 0

        # For each docstring: call chunker (SVO) - it returns all chunks with embeddings.
        # Collect (item, chunk_index, chunk_text, embedding, embedding_model, token_count)
        # for every chunk; if chunker returns [], persist one row with original text.
        rows_to_persist: List[
            Tuple[
                _DocItem,
                int,
                str,
                Optional[List[float]],
                Optional[str],
                Optional[int],
            ]
        ] = []
        if self.svo_client_manager:
            logger.info(
                f"[FILE {file_id}] Requesting chunks+embeddings for {len(items)} docstrings from chunker service..."
            )
            embedding_start_time = time.time()
            try:
                get_batch = getattr(self.svo_client_manager, "get_chunks_batch", None)
                if callable(get_batch):
                    texts = [item.text for item in items]
                    batch_results = None
                    batch_last_error = None
                    for attempt in range(2):
                        try:
                            t0_batch = time.time()
                            batch_results = await get_batch(texts, type="DocBlock")
                            log_operation_timing(
                                getattr(self, "log_timing", False),
                                logger,
                                "get_chunks_batch",
                                time.time() - t0_batch,
                                file_id=file_id,
                                texts=len(texts),
                                attempt=attempt + 1,
                            )
                            break
                        except Exception as batch_e:
                            batch_last_error = batch_e
                            if attempt == 0:
                                logger.warning(
                                    f"[FILE {file_id}] get_chunks_batch attempt {attempt + 1}/2 failed: {batch_e}, retrying in 2s..."
                                )
                                await asyncio.sleep(2)
                            else:
                                logger.warning(
                                    f"[FILE {file_id}] get_chunks_batch failed after 2 attempts: {batch_last_error}, "
                                    "falling back to per-item get_chunks"
                                )
                                rows_to_persist = []
                                get_batch = None
                    if batch_results is not None:
                        for i, item in enumerate(items):
                            chunks = (
                                batch_results[i]
                                if i < len(batch_results) and batch_results[i]
                                else []
                            )
                            if chunks:
                                chunk_embedding_model = None
                                for j, ch in enumerate(chunks):
                                    chunk_text = _chunk_text_from_svo(ch)
                                    emb = getattr(ch, "embedding", None)
                                    if emb is None and hasattr(ch, "vector"):
                                        emb = ch.vector
                                    if chunk_embedding_model is None:
                                        chunk_embedding_model = getattr(
                                            ch, "embedding_model", None
                                        )
                                    tc = getattr(ch, "token_count", None)
                                    if tc is None and chunk_text:
                                        tc = _token_count_from_text(chunk_text)
                                    rows_to_persist.append(
                                        (
                                            item,
                                            j,
                                            chunk_text,
                                            emb,
                                            chunk_embedding_model,
                                            tc,
                                        )
                                    )
                                if chunk_embedding_model and not self.embedding_model:
                                    self.embedding_model = chunk_embedding_model
                            else:
                                tc = _token_count_from_text(item.text)
                                rows_to_persist.append(
                                    (
                                        item,
                                        0,
                                        item.text,
                                        None,
                                        None,
                                        tc if tc else None,
                                    )
                                )
                if not callable(get_batch):
                    for i, item in enumerate(items):
                        try:
                            t0_one = time.time()
                            chunks = await self.svo_client_manager.get_chunks(
                                text=item.text, type="DocBlock"
                            )
                            log_operation_timing(
                                getattr(self, "log_timing", False),
                                logger,
                                "get_chunks_one",
                                time.time() - t0_one,
                                file_id=file_id,
                                index=i,
                            )
                            if chunks and len(chunks) > 0:
                                chunk_embedding_model = None
                                for j, ch in enumerate(chunks):
                                    chunk_text = _chunk_text_from_svo(ch)
                                    emb = getattr(ch, "embedding", None)
                                    if emb is None and hasattr(ch, "vector"):
                                        emb = ch.vector
                                    if chunk_embedding_model is None:
                                        chunk_embedding_model = getattr(
                                            ch, "embedding_model", None
                                        )
                                    tc = getattr(ch, "token_count", None)
                                    if tc is None and chunk_text:
                                        tc = _token_count_from_text(chunk_text)
                                    rows_to_persist.append(
                                        (
                                            item,
                                            j,
                                            chunk_text,
                                            emb,
                                            chunk_embedding_model,
                                            tc,
                                        )
                                    )
                                if chunk_embedding_model and not self.embedding_model:
                                    self.embedding_model = chunk_embedding_model
                            else:
                                tc = _token_count_from_text(item.text)
                                rows_to_persist.append(
                                    (
                                        item,
                                        0,
                                        item.text,
                                        None,
                                        None,
                                        tc if tc else None,
                                    )
                                )
                        except Exception as e:
                            logger.warning(
                                f"[FILE {file_id}] [DOCSTRING {i+1}/{len(items)}] Failed to get chunks: {e} "
                                "(persisting one row without embedding)"
                            )
                            tc = _token_count_from_text(item.text)
                            rows_to_persist.append(
                                (
                                    item,
                                    0,
                                    item.text,
                                    None,
                                    None,
                                    tc if tc else None,
                                )
                            )
            except Exception as e:
                logger.warning(
                    f"[FILE {file_id}] Chunker failed: {e}; persisting docstrings without embeddings"
                )
                for item in items:
                    tc = _token_count_from_text(item.text)
                    rows_to_persist.append(
                        (item, 0, item.text, None, None, tc if tc else None)
                    )
            else:
                logger.info(
                    f"[FILE {file_id}] Chunker returned {len(rows_to_persist)} chunks in "
                    f"{time.time() - embedding_start_time:.3f}s"
                )
        else:
            for item in items:
                tc = _token_count_from_text(item.text)
                rows_to_persist.append(
                    (item, 0, item.text, None, None, tc if tc else None)
                )

        # Persist each chunk row (only if file and project still exist)
        if not self._file_still_exists_and_not_deleted(file_id, project_id):
            logger.warning(
                f"[FILE {file_id}] File or project no longer exists or file is marked deleted, "
                f"skipping chunk persistence for {file_path}"
            )
            return 0

        with_embedding = sum(1 for r in rows_to_persist if r[3] is not None)
        without_embedding = len(rows_to_persist) - with_embedding
        logger.info(
            f"[FILE {file_id}] Persisting {len(rows_to_persist)} chunks "
            f"({with_embedding} with embedding, {without_embedding} without) to database..."
        )
        persist_start_time = time.time()
        insert_ops = self._build_insert_ops_for_docstring_rows(
            file_id, project_id, file_path, rows_to_persist
        )

        written = 0
        if insert_ops:
            execute_batch = self.database.execute_batch
            if asyncio.iscoroutinefunction(execute_batch):
                await execute_batch(insert_ops)
            else:
                await asyncio.to_thread(execute_batch, insert_ops)
            written = len(insert_ops)

        persist_duration = time.time() - persist_start_time
        log_operation_timing(
            getattr(self, "log_timing", False),
            logger,
            "persist_chunks",
            persist_duration,
            file_id=file_id,
            written=written,
            total=len(rows_to_persist),
        )
        logger.info(
            f"[FILE {file_id}] Persisted {written} docstring chunks to database in {persist_duration:.3f}s"
        )
        total_duration = time.time() - process_start_time
        logger.info(
            f"[FILE {file_id}] Completed process_file for {file_path} in {total_duration:.3f}s "
            f"(wrote {written} chunks)"
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
