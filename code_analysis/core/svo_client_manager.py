"""
SVO client manager.

This module provides a single integration point for "SVO" services used by this
project:
- chunker service (SVO) - chunks text and returns chunks with embeddings.
  Chunking is only via WebSocket (queue + completion push on /ws).
- embedding service (embed-client) - only vectorization (embeddings)

The codebase relies on `SVOClientManager` during startup and in the vectorization
worker. Historically it referenced `code_analysis.core.svo_client_manager`, but
the module was missing, which caused the vectorization worker to crash and
prevented rebuilding the FAISS index.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional

from .svo_client_manager_config import build_config
from .svo_client_manager_chunker import (
    close_chunker,
    fetch_chunk_limits,
    get_chunks as _get_chunks_impl,
    get_chunks_batch as _get_chunks_batch_impl,
    init_chunker,
)
from .svo_client_manager_embedding import (
    close_embedding,
    get_embeddings as _get_embeddings_impl,
    init_embedding,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CircuitState:
    """
    Lightweight circuit breaker state snapshot.

    Attributes:
        state: Circuit state name ("closed", "open", "half_open").
        failures: Current consecutive failure count.
        opened_at: Timestamp when circuit was opened, if any.
    """

    state: str
    failures: int
    opened_at: Optional[float]


class SVOClientManager:
    """
    Manager for SVO service clients (chunker and embedding).

    - Chunker (SVO): Chunks text and returns chunks with embeddings (for docstrings)
    - Embedding (embed-client): Only vectorization (for search queries)

    This manager requires real services to be available and configured.
    No fallback mechanisms - if service is unavailable, exceptions are raised.

    Attributes:
        vector_dim: Target embedding dimensionality.
        chunker_enabled: Whether chunker service is enabled by config.
        embedding_enabled: Whether embedding service is enabled by config.
        failure_threshold: Failure count threshold to open the circuit breaker.
        recovery_timeout: Seconds to wait before transitioning open -> half_open.
        initial_backoff: Base backoff (seconds) when circuit is open.
        max_backoff: Maximum backoff (seconds).
        backoff_multiplier: Multiplier for exponential backoff.
    """

    def __init__(self, server_config: Any, root_dir: Optional[str | Path] = None):
        """
        Initialize SVO client manager from server config.

        Args:
            server_config: Parsed config model or dict. The manager expects
                code_analysis.embedding and code_analysis.vector_dim when a dict.
            root_dir: Optional root directory path for resolving relative certificate paths.
        """
        cfg = build_config(server_config, root_dir)
        for key, value in cfg.items():
            setattr(self, key, value)
        self._state: str = "closed"
        self._failures: int = 0
        self._opened_at: Optional[float] = None
        self._half_open_successes: int = 0
        self._chunker_available: bool = True
        self._chunker_status_logged: bool = False
        self._embedding_available: bool = True
        self._embedding_status_logged: bool = False
        self._min_chunk_length: Optional[int] = None
        self._max_chunk_length: Optional[int] = None
        self._chunker_client: Optional[Any] = None
        self._embedding_client: Optional[Any] = None
        self._initialized: bool = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """
        Initialize underlying clients.

        Creates ChunkerClient (SVO) if chunker enabled and EmbeddingServiceAsyncClient
        (embed-client) if embedding enabled.
        """
        async with self._lock:
            if self.chunker_enabled:
                await init_chunker(self)
            if self.embedding_enabled:
                await init_embedding(self)
            self._initialized = True

    async def close(self) -> None:
        """Close underlying clients."""
        async with self._lock:
            await close_chunker(self)
            await close_embedding(self)
            self._initialized = False
        logger.info("SVOClientManager closed")

    def get_circuit_state(self) -> CircuitState:
        """Get circuit breaker state snapshot."""
        self._maybe_transition()
        return CircuitState(
            state=self._state, failures=self._failures, opened_at=self._opened_at
        )

    def get_backoff_delay(self) -> float:
        """Get current backoff delay based on circuit breaker state (seconds)."""
        self._maybe_transition()
        if self._state != "open":
            return 0.0
        delay = self.initial_backoff * (
            self.backoff_multiplier ** max(0, self._failures - 1)
        )
        return float(min(self.max_backoff, delay))

    async def get_chunks(self, text: str, **kwargs: Any) -> List[Any]:
        """
        Get chunks with embeddings from chunker service (SVO) via WebSocket.
        """
        return await _get_chunks_impl(self, text, **kwargs)

    async def get_chunks_batch(
        self, texts: List[str], **kwargs: Any
    ) -> List[List[Any]]:
        """Get chunks with embeddings for multiple texts via WebSocket."""
        return await _get_chunks_batch_impl(self, texts, **kwargs)

    async def get_embeddings(self, chunks: Iterable[Any], **kwargs: Any) -> List[Any]:
        """Get embeddings for provided chunks using real embedding service."""
        return await _get_embeddings_impl(self, chunks, **kwargs)

    def _record_success(self) -> None:
        """Record a successful call and update circuit breaker."""
        if self._state == "half_open":
            self._half_open_successes += 1
            if self._half_open_successes >= self.success_threshold:
                self._state = "closed"
                self._failures = 0
                self._opened_at = None
                self._half_open_successes = 0
                return
        if self._state == "closed":
            self._failures = 0
        elif self._state == "open":
            self._failures = 0

    def _record_failure(self) -> None:
        """Record a failed call and update circuit breaker."""
        self._failures += 1
        self._half_open_successes = 0
        if (
            self._state in ("closed", "half_open")
            and self._failures >= self.failure_threshold
        ):
            self._state = "open"
            self._opened_at = time.time()

    def _maybe_transition(self) -> None:
        """Handle open -> half_open transition after recovery timeout."""
        if self._state != "open":
            return
        if self._opened_at is None:
            self._opened_at = time.time()
            return
        if (time.time() - self._opened_at) >= self.recovery_timeout:
            self._state = "half_open"
            self._half_open_successes = 0

    async def _fetch_chunk_limits(self) -> None:
        """Fetch chunk size limits from chunker service (e.g. after recovery)."""
        await fetch_chunk_limits(self)
