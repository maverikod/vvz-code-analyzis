"""
SVO client manager.

This module provides a single integration point for "SVO" services used by this
project:
- chunker service (SVO) - chunks text and returns chunks with embeddings
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

logger = logging.getLogger(__name__)

# Try to import embed_client (vectorization only)
try:
    from embed_client.async_client import EmbeddingServiceAsyncClient
    from embed_client.client_factory import ClientFactory
    EMBED_CLIENT_AVAILABLE = True
except ImportError:
    EmbeddingServiceAsyncClient = None  # type: ignore
    ClientFactory = None  # type: ignore
    EMBED_CLIENT_AVAILABLE = False

# Try to import svo_client (chunker - chunks and vectorizes)
try:
    from svo_client import ChunkerClient
    CHUNKER_CLIENT_AVAILABLE = True
except ImportError:
    ChunkerClient = None  # type: ignore
    CHUNKER_CLIENT_AVAILABLE = False


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
                `code_analysis.embedding` and `code_analysis.vector_dim` keys when a dict.
            root_dir: Optional root directory path for resolving relative certificate paths.
                If not provided, will try to infer from config (db_path or log path).
        """

        cfg = self._to_dict(server_config)
        
        # Handle both formats: full config dict with "code_analysis" key, or ServerConfig object
        if "code_analysis" in cfg:
            ca_cfg = cfg.get("code_analysis") or {}
        else:
            # server_config is already a ServerConfig object (parsed code_analysis section)
            ca_cfg = cfg
        
        # Convert nested objects to dicts if needed
        if hasattr(ca_cfg, "chunker") and hasattr(ca_cfg.chunker, "enabled"):
            # ServerConfig object - extract directly
            chunker_cfg = self._to_dict(ca_cfg.chunker) if ca_cfg.chunker else {}
            emb_cfg = self._to_dict(ca_cfg.embedding) if ca_cfg.embedding else {}
            worker_dict = self._to_dict(ca_cfg.worker) if ca_cfg.worker else {}
            worker_cfg = worker_dict.get("circuit_breaker") or {} if isinstance(worker_dict, dict) else {}
            self.vector_dim: int = int(ca_cfg.vector_dim or 384)
            self.chunker_enabled: bool = bool(chunker_cfg.get("enabled", False))
            self.embedding_enabled: bool = bool(emb_cfg.get("enabled", False))
        else:
            # Dict format - extract as before
            chunker_cfg = ca_cfg.get("chunker") or {}
            emb_cfg = ca_cfg.get("embedding") or {}
            worker_cfg = (ca_cfg.get("worker") or {}).get("circuit_breaker") or {}
            self.vector_dim: int = int(ca_cfg.get("vector_dim", 384))
            self.chunker_enabled: bool = bool(chunker_cfg.get("enabled", False))
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

        # Track service availability status (for logging only on status change)
        self._chunker_available: bool = True
        self._chunker_status_logged: bool = False
        self._embedding_available: bool = True
        self._embedding_status_logged: bool = False

        # Keep original cfg for client creation
        self._config: dict[str, Any] = cfg

        # Chunker client (SVO - chunks and vectorizes)
        self._chunker_client: Optional[Any] = None

        # Extract chunker configuration (ensure dict format)
        chunker_cfg_dict = self._to_dict(chunker_cfg) if not isinstance(chunker_cfg, dict) else chunker_cfg
        self._chunker_url: str = str(chunker_cfg_dict.get("url") or chunker_cfg_dict.get("host") or "localhost")
        self._chunker_port: int = int(chunker_cfg_dict.get("port", 8009))
        self._chunker_protocol: str = str(chunker_cfg_dict.get("protocol", "http"))
        self._chunker_cert_file: Optional[str] = chunker_cfg_dict.get("cert_file")
        self._chunker_key_file: Optional[str] = chunker_cfg_dict.get("key_file")
        self._chunker_ca_cert_file: Optional[str] = chunker_cfg_dict.get("ca_cert_file")
        self._chunker_crl_file: Optional[str] = chunker_cfg_dict.get("crl_file")
        self._chunker_timeout: Optional[float] = chunker_cfg_dict.get("timeout")
        self._chunker_check_hostname: bool = bool(chunker_cfg_dict.get("check_hostname", False))

        # Embedding client (embed-client - only vectorization)
        self._embedding_client: Optional[Any] = None

        # Extract embedding configuration (ensure dict format)
        emb_cfg_dict = self._to_dict(emb_cfg) if not isinstance(emb_cfg, dict) else emb_cfg
        self._embedding_url: str = str(emb_cfg_dict.get("url") or emb_cfg_dict.get("host") or "localhost")
        self._embedding_port: int = int(emb_cfg_dict.get("port", 8001))
        self._embedding_protocol: str = str(emb_cfg_dict.get("protocol", "http"))
        # Store certificate paths as-is (will be resolved relative to config file location if needed)
        self._embedding_cert_file: Optional[str] = emb_cfg_dict.get("cert_file")
        self._embedding_key_file: Optional[str] = emb_cfg_dict.get("key_file")
        self._embedding_ca_cert_file: Optional[str] = emb_cfg_dict.get("ca_cert_file")
        self._embedding_crl_file: Optional[str] = emb_cfg_dict.get("crl_file")
        self._embedding_timeout: Optional[float] = emb_cfg_dict.get("timeout")
        self._embedding_check_hostname: bool = bool(emb_cfg_dict.get("check_hostname", False))
        
        # Store root path for resolving relative certificate paths
        # Priority: explicit root_dir > infer from config > current working directory
        self._root_path: Optional[Path] = None
        if root_dir:
            self._root_path = Path(root_dir)
        elif "code_analysis" in cfg:
            # Try to infer from db_path or log path
            db_path = ca_cfg.get("db_path")
            if db_path:
                self._root_path = Path(db_path).parent.parent  # data/code_analysis.db -> project root
            else:
                log_path = ca_cfg.get("log")
                if log_path:
                    self._root_path = Path(log_path).parent.parent  # logs/code_analysis.log -> project root

        # Async init/close markers
        self._initialized: bool = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """
        Initialize underlying clients.

        Creates:
        - ChunkerClient (SVO) if chunker is enabled - for chunking and vectorization
        - EmbeddingServiceAsyncClient (embed-client) if embedding is enabled - for vectorization only
        """

        async with self._lock:
            # Initialize chunker client (SVO - chunks and vectorizes)
            if self.chunker_enabled and CHUNKER_CLIENT_AVAILABLE:
                try:
                    # Create ChunkerClient (uses host and port, not url)
                    # Map cert_file/key_file/ca_cert_file to cert/key/ca
                    chunker_kwargs: dict[str, Any] = {
                        "host": self._chunker_url,
                        "port": self._chunker_port,
                        "check_hostname": self._chunker_check_hostname,
                    }
                    if self._chunker_timeout:
                        chunker_kwargs["timeout"] = self._chunker_timeout
                    
                    # Map certificate files to ChunkerClient parameters
                    if self._chunker_protocol in ("mtls", "https"):
                        if self._chunker_cert_file:
                            cert_path = Path(self._chunker_cert_file)
                            if not cert_path.is_absolute() and self._root_path:
                                cert_path = self._root_path / cert_path
                            chunker_kwargs["cert"] = str(cert_path.resolve())
                        if self._chunker_key_file:
                            key_path = Path(self._chunker_key_file)
                            if not key_path.is_absolute() and self._root_path:
                                key_path = self._root_path / key_path
                            chunker_kwargs["key"] = str(key_path.resolve())
                        if self._chunker_ca_cert_file:
                            ca_cert_path = Path(self._chunker_ca_cert_file)
                            if not ca_cert_path.is_absolute() and self._root_path:
                                ca_cert_path = self._root_path / ca_cert_path
                            chunker_kwargs["ca"] = str(ca_cert_path.resolve())
                    
                    # Create ChunkerClient and enter context manager
                    self._chunker_client = ChunkerClient(**chunker_kwargs)
                    await self._chunker_client.__aenter__()

                    logger.info(
                        "SVOClientManager initialized with real chunker service "
                        "(url=%s:%s, protocol=%s)",
                        self._chunker_url,
                        self._chunker_port,
                        self._chunker_protocol,
                    )
                except Exception as e:
                    logger.error(
                        "Failed to initialize real chunker client: %s",
                        e,
                        exc_info=True,
                    )
                    raise RuntimeError(
                        f"Failed to initialize chunker service: {e}"
                    ) from e
            else:
                if self.chunker_enabled and not CHUNKER_CLIENT_AVAILABLE:
                    error_msg = (
                        "svo_client library is not available. "
                        "Install it to use chunker service."
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

            # Initialize embedding client (embed-client - only vectorization)
            if self.embedding_enabled and EMBED_CLIENT_AVAILABLE:
                try:
                    # Determine base URL based on protocol
                    if self._embedding_protocol == "mtls":
                        base_url = f"https://{self._embedding_url}"
                    elif self._embedding_protocol == "https":
                        base_url = f"https://{self._embedding_url}"
                    else:
                        base_url = f"http://{self._embedding_url}"

                    # Create client using ClientFactory
                    client_kwargs: dict[str, Any] = {}
                    if self._embedding_timeout:
                        client_kwargs["timeout"] = self._embedding_timeout

                    # Configure SSL/TLS for mTLS or HTTPS
                    if self._embedding_protocol in ("mtls", "https"):
                        ssl_enabled = True
                        if self._embedding_protocol == "mtls":
                            if self._embedding_cert_file and self._embedding_key_file:
                                # Resolve relative paths
                                cert_path = Path(self._embedding_cert_file)
                                key_path = Path(self._embedding_key_file)
                                if not cert_path.is_absolute() and self._root_path:
                                    cert_path = self._root_path / cert_path
                                if not key_path.is_absolute() and self._root_path:
                                    key_path = self._root_path / key_path
                                client_kwargs["cert_file"] = str(cert_path.resolve())
                                client_kwargs["key_file"] = str(key_path.resolve())
                            if self._embedding_ca_cert_file:
                                ca_cert_path = Path(self._embedding_ca_cert_file)
                                if not ca_cert_path.is_absolute() and self._root_path:
                                    ca_cert_path = self._root_path / ca_cert_path
                                client_kwargs["ca_cert_file"] = str(ca_cert_path.resolve())
                            if self._embedding_crl_file:
                                crl_path = Path(self._embedding_crl_file)
                                if not crl_path.is_absolute() and self._root_path:
                                    crl_path = self._root_path / crl_path
                                client_kwargs["crl_file"] = str(crl_path.resolve())
                        else:
                            # HTTPS without client certs
                            if self._embedding_ca_cert_file:
                                ca_cert_path = Path(self._embedding_ca_cert_file)
                                if not ca_cert_path.is_absolute() and self._root_path:
                                    ca_cert_path = self._root_path / ca_cert_path
                                client_kwargs["ca_cert_file"] = str(ca_cert_path.resolve())
                    else:
                        ssl_enabled = False

                    # Add check_hostname if SSL is enabled
                    if ssl_enabled:
                        client_kwargs["verify"] = self._embedding_check_hostname
                    
                    # Create client
                    self._embedding_client = ClientFactory.create_client(
                        base_url=base_url,
                        port=self._embedding_port,
                        auth_method="none",  # Can be extended later
                        ssl_enabled=ssl_enabled,
                        **client_kwargs,
                    )

                    # Initialize client (enter context manager)
                    await self._embedding_client.__aenter__()

                    logger.info(
                        "SVOClientManager initialized with real embedding service "
                        "(url=%s:%s, protocol=%s, vector_dim=%s)",
                        self._embedding_url,
                        self._embedding_port,
                        self._embedding_protocol,
                        self.vector_dim,
                    )
                except Exception as e:
                    logger.error(
                        "Failed to initialize real embedding client: %s",
                        e,
                        exc_info=True,
                    )
                    raise RuntimeError(
                        f"Failed to initialize embedding service: {e}"
                    ) from e
            else:
                if not self.embedding_enabled:
                    error_msg = (
                        "Embedding service is disabled in configuration. "
                        "Set code_analysis.embedding.enabled=true to enable."
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
                elif not EMBED_CLIENT_AVAILABLE:
                    error_msg = (
                        "embed_client library is not available. "
                        "Install it to use embedding service."
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

            self._initialized = True

    async def close(self) -> None:
        """
        Close underlying clients.
        """

        async with self._lock:
            if self._chunker_client:
                try:
                    # Use context manager exit for proper cleanup
                    await self._chunker_client.__aexit__(None, None, None)
                except Exception as e:
                    logger.warning("Error closing chunker client: %s", e, exc_info=True)
                finally:
                    self._chunker_client = None

            if self._embedding_client:
                try:
                    await self._embedding_client.__aexit__(None, None, None)
                except Exception as e:
                    logger.warning("Error closing embedding client: %s", e, exc_info=True)
                finally:
                    self._embedding_client = None

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

    async def get_chunks(self, text: str, **kwargs: Any) -> List[Any]:
        """
        Get chunks with embeddings from chunker service (SVO).

        Chunker service chunks text and returns chunks with embeddings.
        Used for vectorizing docstrings.

        Args:
            text: Text to chunk and vectorize.
            **kwargs: Additional chunking parameters (type, language, etc.).

        Returns:
            List of chunk objects with embeddings (SemanticChunk from svo_client).

        Raises:
            RuntimeError: If chunker service is not available or not enabled.
        """

        self._maybe_transition()

        # Require real chunker service
        if not self._chunker_client or not self.chunker_enabled:
            error_msg = (
                "Chunker service is not available or not enabled. "
                "Ensure code_analysis.chunker.enabled=true and service is running."
            )
            logger.error(
                "get_chunks called but chunker service is not available: "
                "client=%s, enabled=%s",
                self._chunker_client is not None,
                self.chunker_enabled,
            )
            raise RuntimeError(error_msg)

        try:
            # Call chunker service - it returns chunks with embeddings
            chunks = await self._chunker_client.chunk_text(text=text, **kwargs)
            self._record_success()
            # Service is available
            if not self._chunker_available:
                # Status changed: unavailable -> available
                logger.info("✅ Chunker service is now available")
                self._chunker_available = True
                self._chunker_status_logged = True
            else:
                self._chunker_status_logged = False  # Already logged as available
            return chunks
        except Exception as e:
            self._record_failure()
            # Check if error indicates service unavailability
            error_str = str(e).lower()
            is_unavailable_error = (
                "model rpc server failed" in error_str
                or "connection" in error_str
                or "timeout" in error_str
                or "unavailable" in error_str
                or "failed after" in error_str
            )
            
            if is_unavailable_error:
                if self._chunker_available:
                    # Status changed: available -> unavailable
                    logger.warning(f"⚠️  Chunker service is now unavailable: {e}")
                    self._chunker_available = False
                    self._chunker_status_logged = True
                elif not self._chunker_status_logged:
                    # First time logging unavailability
                    logger.warning(f"⚠️  Chunker service is unavailable: {e}")
                    self._chunker_status_logged = True
                else:
                    # Already logged, don't spam
                    self._chunker_status_logged = False
            else:
                # Other error (not availability-related), log normally
                logger.error(
                    "Failed to get chunks from chunker service: %s",
                    e,
                    exc_info=True,
                )
            raise

    async def get_embeddings(self, chunks: Iterable[Any], **kwargs: Any) -> List[Any]:
        """
        Get embeddings for provided chunks using real embedding service.

        The method is compatible with existing code expecting each chunk object
        to receive an `embedding` attribute.

        Requires real embedding service to be available and enabled.
        No fallback mechanisms - raises exception if service is unavailable.

        Args:
            chunks: Iterable of objects with either `.body` or `.text` attributes.
            **kwargs: Extra parameters accepted for compatibility with callers
                (e.g. `type`, `language`, etc.).

        Returns:
            List of the same chunk objects, each augmented with `.embedding`.

        Raises:
            RuntimeError: If embedding service is not available or not enabled.
            ValueError: If embedding service returns invalid response.
        """

        self._maybe_transition()
        chunks_list = list(chunks)
        if not chunks_list:
            return []

        # Require real embedding service
        if not self._embedding_client or not self.embedding_enabled:
            error_msg = (
                "Embedding service is not available or not enabled. "
                "Ensure code_analysis.embedding.enabled=true and service is running."
            )
            logger.error(
                "get_embeddings called but embedding service is not available: "
                "client=%s, enabled=%s",
                self._embedding_client is not None,
                self.embedding_enabled,
            )
            raise RuntimeError(error_msg)

        try:
            # Extract texts from chunks
            texts: list[str] = []
            for ch in chunks_list:
                text = self._get_chunk_text(ch)
                texts.append(text)

            # Call embedding service
            result = await self._embedding_client.cmd(
                command="embed",
                params={"texts": texts},
            )

            # Extract embeddings from response
            if result and "result" in result:
                result_data = result["result"]
                if result_data.get("success") and "data" in result_data:
                    data = result_data["data"]
                    # Try different response formats
                    embeddings = None
                    if "embeddings" in data:
                        embeddings = data["embeddings"]
                    elif "results" in data:
                        # New format with results array
                        results = data["results"]
                        embeddings = [
                            r.get("embedding") if isinstance(r, dict) else None
                            for r in results
                        ]

                    if embeddings and len(embeddings) == len(chunks_list):
                        # Assign embeddings to chunks
                        for ch, emb in zip(chunks_list, embeddings):
                            if emb is not None:
                                setattr(ch, "embedding", emb)
                                # Also set embedding_model if available
                                if isinstance(data, dict) and "model" in data:
                                    setattr(ch, "embedding_model", data["model"])
                        self._record_success()
                        return chunks_list
                    else:
                        error_msg = "Embedding service returned unexpected format or count mismatch"
                        logger.error(
                            "%s: expected %d embeddings, got %d",
                            error_msg,
                            len(chunks_list),
                            len(embeddings) if embeddings else 0,
                        )
                        raise ValueError(error_msg)
                else:
                    error_msg = result_data.get("error", "Unknown error")
                    logger.error(
                        "Embedding service returned error: %s (response: %s)",
                        error_msg,
                        result_data,
                    )
                    raise ValueError(f"Embedding service error: {error_msg}")
            else:
                error_msg = "Invalid embedding service response"
                logger.error(
                    "%s: result structure is invalid (result=%s)",
                    error_msg,
                    result,
                )
                raise ValueError(error_msg)

        except Exception as e:
            self._record_failure()
            # Check if error indicates service unavailability
            error_str = str(e).lower()
            is_unavailable_error = (
                "connection" in error_str
                or "timeout" in error_str
                or "unavailable" in error_str
                or "failed after" in error_str
            )
            
            if is_unavailable_error:
                if self._embedding_available:
                    # Status changed: available -> unavailable
                    logger.warning(f"⚠️  Embedding service is now unavailable: {e}")
                    self._embedding_available = False
                    self._embedding_status_logged = True
                elif not self._embedding_status_logged:
                    # First time logging unavailability
                    logger.warning(f"⚠️  Embedding service is unavailable: {e}")
                    self._embedding_status_logged = True
                else:
                    # Already logged, don't spam
                    self._embedding_status_logged = False
            else:
                # Other error (not availability-related), log normally
                logger.error(
                    "Failed to get embeddings from real service: %s",
                    e,
                    exc_info=True,
                )
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
