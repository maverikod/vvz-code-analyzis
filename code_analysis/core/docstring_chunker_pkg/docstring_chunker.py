"""
Docstring extraction and chunk persistence.

This module implements `DocstringChunker`, a minimal and robust docstring
extractor used by the vectorization worker.

The worker expects:
- `DocstringChunker.process_file(...)` to insert docstring chunks into DB
- chunks to be stored in `code_chunks` with `source_type` like "docstring"
- optionally precomputed `embedding_vector` to speed up vectorization

Persistence uses the portable statement in ``code_analysis.core.database.code_chunk_sql``
and, when available, ``database.upsert_code_chunks_batch`` (RPC / in-process client);
the PostgreSQL driver translates upserts in ``postgres_run._adapt_sqlite_dml_for_postgres``.

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

from code_analysis.core.database.code_chunk_sql import (
    CODE_CHUNK_UPSERT_PARAM_COUNT,
    build_code_chunk_upsert_batch,
)
from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE

from ..docs_markdown_vector_gate import DOCS_MARKDOWN_SOURCE_TYPE
from ..exceptions import ChunkerResponseError
from ..vectorization_worker_pkg.timing_log import log_operation_timing

logger = logging.getLogger(__name__)

# Max docstring texts per single ``get_chunks_batch`` RPC (multi-file prepared path).
DOCSTRING_CHUNK_BATCH_MAX_TEXTS = 128


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

    file_id: str
    project_id: str
    file_path: str
    tree: ast.Module
    file_content: str
    items: List[_DocItem]


class DocstringChunker:
    """
    Extract docstrings from a Python AST and store them as `code_chunks`.

    This class owns AST extraction and stable chunk parameter rows only; it does not
    embed SQL dialect details. Portable ``code_chunks`` upsert SQL and the 18-column
    bind layout (``CODE_CHUNK_UPSERT_PARAM_COUNT`` / ``build_code_chunk_upsert_batch``)
    live in ``code_analysis.core.database.code_chunk_sql``.

    Notes:
        - This implementation focuses on docstrings only (module/class/function/method).
        - It does not depend on external chunker services.
        - If `svo_client_manager` is provided, it precomputes embeddings using the
          manager's `get_embeddings(...)` (requires real embedding service).

    Attributes:
        database: Legacy SQL facade instance.
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
        docs_markdown_embeddings_enabled: bool = True,
    ) -> None:
        """
        Initialize docstring chunker.

        Args:
            database: Legacy SQL facade instance.
            svo_client_manager: SVO client manager for embeddings (optional).
            faiss_manager: FAISS index manager (optional, reserved for future use).
            min_chunk_length: Minimum text length to store (default: 30).
            embedding_model: Embedding model identifier stored in DB.
            log_timing: When True, log every operation with duration for bottleneck analysis.
            docs_markdown_embeddings_enabled: When False, Markdown docs use local text rows
                without chunker/embed RPC (``docs_indexing.vectorize=false`` gate).
        """

        self.database = database
        self.svo_client_manager = svo_client_manager
        self.faiss_manager = faiss_manager
        self.min_chunk_length = int(min_chunk_length)
        self.embedding_model = embedding_model
        self.log_timing = log_timing
        self.docs_markdown_embeddings_enabled = bool(docs_markdown_embeddings_enabled)

    def _file_still_exists_and_not_deleted(self, file_id: str, project_id: str) -> bool:
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

    def _code_chunk_upsert_param_rows_for_docstring_rows(
        self,
        file_id: str,
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
    ) -> List[Tuple[Any, ...]]:
        """
        Build parameter tuples for portable ``code_chunks`` upsert.

        Each tuple has ``CODE_CHUNK_UPSERT_PARAM_COUNT`` values in
        ``CODE_CHUNK_UPSERT_PARAM_ORDER`` from ``code_chunk_sql`` (``updated_at`` is
        set by the statement, not bound).
        """
        param_rows: List[Tuple[Any, ...]] = []
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
                    f"stopping after {len(param_rows)} chunks for {file_path}"
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
            chunk_pk = str(uuid.uuid4())
            params = (
                chunk_pk,
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
            if len(params) != CODE_CHUNK_UPSERT_PARAM_COUNT:
                raise ValueError(
                    "docstring chunk param row length mismatch: "
                    f"expected {CODE_CHUNK_UPSERT_PARAM_COUNT}, got {len(params)}"
                )
            param_rows.append(params)
        return param_rows

    async def _persist_code_chunk_param_rows(
        self, param_rows: List[Tuple[Any, ...]]
    ) -> None:
        """Persist via DB abstraction when available, else ``execute_batch`` of portable ops."""
        if not param_rows:
            return
        upsert_batch = getattr(self.database, "upsert_code_chunks_batch", None)
        if callable(upsert_batch):
            if asyncio.iscoroutinefunction(upsert_batch):
                await upsert_batch(param_rows)
            else:
                await asyncio.to_thread(upsert_batch, param_rows)
            return
        ops = build_code_chunk_upsert_batch(param_rows)
        execute_batch = self.database.execute_batch
        if asyncio.iscoroutinefunction(execute_batch):
            await execute_batch(ops)
        else:
            await asyncio.to_thread(execute_batch, ops)

    def _chunker_params_for_items(self, items: List[_DocItem]) -> Dict[str, Any]:
        if any(
            it.source_type == DOCS_MARKDOWN_SOURCE_TYPE
            or it.ast_node_type == "MarkdownDoc"
            for it in items
        ):
            chunk_set = "technical_text"
        else:
            chunk_set = "docstring"
        return {
            "chunk_set": chunk_set,
            "use_sv": False,
            "language": "en",
            "type": "DocBlock",
        }

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
            chunks = await mgr.get_chunks(
                text=item.text, **self._chunker_params_for_items([item])
            )
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
    ) -> Dict[str, int]:
        """
        Process multiple prepared files using ``get_chunks_batch`` when available.

        Batches docstrings across files (flat order) up to
        :data:`DOCSTRING_CHUNK_BATCH_MAX_TEXTS`, then persists all inserts in one
        logical write batch when supported.
        """
        counts: Dict[str, int] = {pf.file_id: 0 for pf in prepared}
        flat: List[Tuple[PreparedDocstringFile, _DocItem]] = []
        for pf in prepared:
            for it in pf.items:
                flat.append((pf, it))
        if not flat:
            return counts

        all_param_rows: List[Tuple[Any, ...]] = []
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
                    all_param_rows.extend(
                        self._code_chunk_upsert_param_rows_for_docstring_rows(
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
                    all_param_rows.extend(
                        self._code_chunk_upsert_param_rows_for_docstring_rows(
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
                batch_results = await get_batch(
                    texts, **self._chunker_params_for_items([it for _, it in seg])
                )
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
                    all_param_rows.extend(
                        self._code_chunk_upsert_param_rows_for_docstring_rows(
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
                    all_param_rows.extend(
                        self._code_chunk_upsert_param_rows_for_docstring_rows(
                            pf.file_id,
                            pf.project_id,
                            pf.file_path,
                            rows,
                        )
                    )

        if not all_param_rows:
            return counts

        lw = getattr(self.database, "execute_logical_write_operation", None)
        if callable(lw):
            program = {"batches": [build_code_chunk_upsert_batch(all_param_rows)]}
            if asyncio.iscoroutinefunction(lw):
                await lw(program)
            else:
                await asyncio.to_thread(lw, program)
        else:
            await self._persist_code_chunk_param_rows(all_param_rows)

        for params in all_param_rows:
            fid = params[1]
            counts[fid] = counts.get(fid, 0) + 1
        return counts

    async def _gather_rows_for_docblock_items(
        self,
        items: List[_DocItem],
        *,
        log_file_id: str,
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
        """Collect (item, slice, text, embedding, model, tokens) rows via DocBlock chunker."""
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
                "[FILE %s] Requesting DocBlock chunks (%s texts) via SVO chunker…",
                log_file_id,
                len(items),
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
                            batch_results = await get_batch(
                                texts, **self._chunker_params_for_items(items)
                            )
                            log_operation_timing(
                                getattr(self, "log_timing", False),
                                logger,
                                "get_chunks_batch",
                                time.time() - t0_batch,
                                file_id=log_file_id,
                                texts=len(texts),
                                attempt=attempt + 1,
                            )
                            break
                        except Exception as batch_e:
                            batch_last_error = batch_e
                            if attempt == 0:
                                logger.warning(
                                    f"[FILE {log_file_id}] get_chunks_batch attempt {attempt + 1}/2 failed: {batch_e}, retrying in 2s…"
                                )
                                await asyncio.sleep(2)
                            else:
                                logger.warning(
                                    f"[FILE {log_file_id}] get_chunks_batch failed after 2 attempts: {batch_last_error}, "
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
                                text=item.text,
                                **self._chunker_params_for_items([item]),
                            )
                            log_operation_timing(
                                getattr(self, "log_timing", False),
                                logger,
                                "get_chunks_one",
                                time.time() - t0_one,
                                file_id=log_file_id,
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
                                f"[FILE {log_file_id}] [item {i+1}/{len(items)}] Failed to get chunks: {e} "
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
                    f"[FILE {log_file_id}] Chunker failed: {e}; persisting without embeddings"
                )
                for item in items:
                    tc = _token_count_from_text(item.text)
                    rows_to_persist.append(
                        (item, 0, item.text, None, None, tc if tc else None)
                    )
            else:
                logger.info(
                    f"[FILE {log_file_id}] Chunker returned {len(rows_to_persist)} rows in "
                    f"{time.time() - embedding_start_time:.3f}s"
                )
        else:
            for item in items:
                tc = _token_count_from_text(item.text)
                rows_to_persist.append(
                    (item, 0, item.text, None, None, tc if tc else None)
                )
        return rows_to_persist

    async def _write_docblock_chunk_rows(
        self,
        *,
        file_id: str,
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
        log_kind: str = "chunks",
    ) -> int:
        """Persist assembled DocBlock rows via portable code_chunks upsert."""
        process_start_time = time.time()
        logger.info(
            f"[FILE {file_id}] Starting _write_docblock_chunk_rows ({log_kind}) for {file_path}"
        )
        if not self._file_still_exists_and_not_deleted(file_id, project_id):
            logger.warning(
                f"[FILE {file_id}] File or project no longer exists or file is marked deleted, "
                f"skipping chunk persistence for {file_path}"
            )
            return 0

        with_embedding = sum(1 for r in rows_to_persist if r[3] is not None)
        without_embedding = len(rows_to_persist) - with_embedding
        logger.info(
            f"[FILE {file_id}] Persisting {len(rows_to_persist)} rows "
            f"({with_embedding} with embedding, {without_embedding} without)…"
        )
        persist_start_time = time.time()
        param_rows = self._code_chunk_upsert_param_rows_for_docstring_rows(
            file_id, project_id, file_path, rows_to_persist
        )

        written = 0
        if param_rows:
            await self._persist_code_chunk_param_rows(param_rows)
            written = len(param_rows)

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
        total_dur = time.time() - process_start_time
        logger.info(
            f"[FILE {file_id}] Persisted {written} rows in {persist_duration:.3f}s "
            f"({total_dur:.3f}s total)"
        )
        return written

    async def _mark_docs_markdown_vectorization_skipped(
        self, file_id: str, project_id: str
    ) -> None:
        """Exclude Markdown docs chunks from embedding retry loops."""
        sql = (
            "UPDATE code_chunks SET vectorization_skipped = 1 "
            "WHERE file_id = ? AND project_id = ? AND source_type = ?"
        )
        params = (file_id, project_id, DOCS_MARKDOWN_SOURCE_TYPE)
        ex = getattr(self.database, "execute", None)
        if not callable(ex):
            return
        if asyncio.iscoroutinefunction(ex):
            await ex(sql, params)
        else:

            def _run() -> None:
                ex(sql, params)

            await asyncio.to_thread(_run)

    async def process_markdown_document(
        self,
        *,
        file_id: str,
        project_id: str,
        file_path: str,
        text: str,
    ) -> int:
        """Chunk full Markdown file text as DocBlock; Group F distinguishes via ``source_type=docs_markdown``."""
        if not text.strip():
            return 0
        item = _DocItem(
            source_type="docs_markdown",
            chunk_type="DocBlock",
            text=text,
            line=1,
            ast_node_type="MarkdownDoc",
            binding_level=0,
        )
        if not self.docs_markdown_embeddings_enabled:
            tc = _token_count_from_text(text)
            rows_to_persist = [
                (item, 0, text, None, None, tc if tc else None),
            ]
        else:
            rows_to_persist = await self._gather_rows_for_docblock_items(
                [item], log_file_id=str(file_id)
            )
        written = await self._write_docblock_chunk_rows(
            file_id=file_id,
            project_id=project_id,
            file_path=file_path,
            rows_to_persist=rows_to_persist,
            log_kind="markdown_doc",
        )
        if written and not self.docs_markdown_embeddings_enabled:
            await self._mark_docs_markdown_vectorization_skipped(file_id, project_id)
        return written

    async def process_file(
        self,
        *,
        file_id: str,
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

        rows_to_persist = await self._gather_rows_for_docblock_items(
            items, log_file_id=str(file_id)
        )
        written = await self._write_docblock_chunk_rows(
            file_id=file_id,
            project_id=project_id,
            file_path=file_path,
            rows_to_persist=rows_to_persist,
            log_kind="docstring",
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
