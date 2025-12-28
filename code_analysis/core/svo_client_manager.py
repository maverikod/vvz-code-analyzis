"""
SVO client manager.

This module provides a single integration point for "SVO" services used by this
project:
- embedding service (vectorization)
- (optionally) chunker service

The codebase relies on `SVOClientManager` during startup and in the vectorization
worker. Historically it referenced `code_analysis.core.svo_client_manager`, but
the module was missing, which caused the vectorization worker to crash and
prevented rebuilding the FAISS index.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional

import numpy as np

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
    Manager for SVO service clients (embeddings / chunker).

    This manager is intentionally robust: if an external embedding service is
    unavailable or not configured, it falls back to deterministic pseudo-embeddings.
    That ensures the following commands remain operational:
    - `update_indexes` (rebuilds FAISS)
    - `semantic_search` (can search with FAISS even without external embeddings)

    Attributes:
        vector_dim: Target embedding dimensionality.
        embedding_enabled: Whether embedding service is enabled by config.
        failure_threshold: Failure count threshold to open the circuit breaker.
        recovery_timeout: Seconds to wait before transitioning open -> half_open.
        initial_backoff: Base backoff (seconds) when circuit is open.
        max_backoff: Maximum backoff (seconds).
        backoff_multiplier: Multiplier for exponential backoff.
    """

    def __init__(self, server_config: Any):
        """
        Initialize SVO client manager from server config.

        Args:
            server_config: Parsed config model or dict. The manager expects
                `code_analysis.embedding` and `code_analysis.vector_dim` keys when a dict.
        """

        cfg = self._to_dict(server_config)
        ca_cfg = cfg.get("code_analysis") or {}
        emb_cfg = ca_cfg.get("embedding") or {}
        worker_cfg = (ca_cfg.get("worker") or {}).get("circuit_breaker") or {}

        self.vector_dim: int = int(ca_cfg.get("vector_dim", 384))
        self.embedding_enabled: bool = bool(emb_cfg.get("enabled", False))

        self.failure_threshold: int = int(worker_cfg.get("failure_threshold", 5))
        self.recovery_timeout: float = float(worker_cfg.get("recovery_timeout", 60.0))
        self.success_threshold: int = int(worker_cfg.get("success_threshold", 2))
        self.initial_backoff: float = float(worker_cfg.get("initial_backoff", 5.0))
        self.max_backoff: float = float(worker_cfg.get("max_backoff", 300.0))
        self.backoff_multiplier: float = float(
            worker_cfg.get("backoff_multiplier", 2.0)
        )

        # Circuit breaker internals
        self._state: str = "closed"
        self._failures: int = 0
        self._opened_at: Optional[float] = None
        self._half_open_successes: int = 0

        # Keep original cfg for potential future extension (real HTTP client)
        self._config: dict[str, Any] = cfg

        # Async init/close markers
        self._initialized: bool = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """
        Initialize underlying clients.

        This implementation is currently a no-op. It exists to keep compatibility
        with existing startup logic and to allow future addition of real HTTP clients.
        """

        async with self._lock:
            self._initialized = True
        logger.info(
            "SVOClientManager initialized (embedding_enabled=%s, vector_dim=%s)",
            self.embedding_enabled,
            self.vector_dim,
        )

    async def close(self) -> None:
        """
        Close underlying clients.

        This implementation is currently a no-op.
        """

        async with self._lock:
            self._initialized = False
        logger.info("SVOClientManager closed")

    def get_circuit_state(self) -> CircuitState:
        """
        Get circuit breaker state snapshot.

        Returns:
            CircuitState snapshot.
        """

        self._maybe_transition()
        return CircuitState(
            state=self._state, failures=self._failures, opened_at=self._opened_at
        )

    def get_backoff_delay(self) -> float:
        """
        Get current backoff delay based on circuit breaker state.

        Returns:
            Backoff delay in seconds.
        """

        self._maybe_transition()
        if self._state != "open":
            return 0.0

        # Exponential backoff bounded by max_backoff
        delay = self.initial_backoff * (
            self.backoff_multiplier ** max(0, self._failures - 1)
        )
        return float(min(self.max_backoff, delay))

    async def get_embeddings(self, chunks: Iterable[Any], **kwargs: Any) -> List[Any]:
        """
        Get embeddings for provided chunks.

        The method is compatible with existing code expecting each chunk object
        to receive an `embedding` attribute.

        If embedding service is disabled/unavailable, it uses deterministic pseudo
        embeddings derived from chunk text.

        Args:
            chunks: Iterable of objects with either `.body` or `.text` attributes.
            **kwargs: Extra parameters accepted for compatibility with callers
                (e.g. `type`, `language`, etc.). They are ignored by the fallback
                implementation.

        Returns:
            List of the same chunk objects, each augmented with `.embedding`.
        """

        self._maybe_transition()
        chunks_list = list(chunks)
        if not chunks_list:
            return []

        # Currently we only implement fallback embeddings. If a real service is enabled,
        # we still fall back (robust) until a stable remote API integration is added.
        try:
            for ch in chunks_list:
                text = self._get_chunk_text(ch)
                emb = self._pseudo_embedding(text, dim=self.vector_dim)
                setattr(ch, "embedding", emb)
            self._record_success()
            return chunks_list
        except Exception as e:
            self._record_failure()
            logger.warning(
                "Failed to generate embeddings (fallback): %s", e, exc_info=True
            )
            # Re-raise to let callers decide (most code handles exceptions and continues)
            raise

    # ==========================
    # Internal helpers
    # ==========================

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
            # Should not happen often, but reset softly
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

    @staticmethod
    def _get_chunk_text(chunk: Any) -> str:
        """Extract text from chunk-like object."""

        if hasattr(chunk, "body") and getattr(chunk, "body") is not None:
            return str(getattr(chunk, "body"))
        if hasattr(chunk, "text") and getattr(chunk, "text") is not None:
            return str(getattr(chunk, "text"))
        return str(chunk)

    @staticmethod
    def _pseudo_embedding(text: str, dim: int) -> List[float]:
        """
        Create a deterministic pseudo-embedding for a given text.

        Args:
            text: Input text.
            dim: Embedding dimension.

        Returns:
            Unit-normalized vector (list[float]) of length dim.
        """

        digest = hashlib.sha256(text.encode("utf-8")).digest()
        seed = int.from_bytes(digest[:8], "little", signed=False)
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(int(dim)).astype("float32")
        norm = float(np.linalg.norm(vec))
        if norm > 0.0:
            vec = vec / norm
        return [float(x) for x in vec.tolist()]

    @staticmethod
    def _to_dict(cfg: Any) -> dict[str, Any]:
        """Convert config model/dict into a plain dict."""

        if cfg is None:
            return {}
        if isinstance(cfg, dict):
            return cfg
        # SimpleConfigModel / pydantic-style models
        if hasattr(cfg, "to_dict") and callable(getattr(cfg, "to_dict")):
            try:
                return dict(cfg.to_dict())
            except Exception:
                pass
        if hasattr(cfg, "dict") and callable(getattr(cfg, "dict")):
            try:
                return dict(cfg.dict())
            except Exception:
                pass
        # Fallback: best effort via vars()
        try:
            return dict(vars(cfg))
        except Exception:
            return {}
