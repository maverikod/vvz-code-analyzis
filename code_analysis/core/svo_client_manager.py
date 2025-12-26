"""
Manager for SVO chunker client.

Provides unified interface for working with chunker service which handles
both chunking and embeddings with mTLS support.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import logging
from typing import Optional, List, Any

from .config import ServerConfig
from .chunker_client_wrapper import create_chunker_client
from .circuit_breaker import CircuitBreaker, CircuitState
from svo_client import ChunkerClient
from embed_client.async_client import EmbeddingServiceAsyncClient

logger = logging.getLogger(__name__)


class SVOClientManager:
    """
    Manager for SVO chunker client.

    Handles initialization and lifecycle of chunker client which provides
    both chunking and embedding capabilities.
    """

    def __init__(self, config: ServerConfig):
        """
        Initialize SVO client manager.

        Args:
            config: Server configuration
        """
        self.config = config
        self._chunker_client: Optional[ChunkerClient] = None
        self._embedding_client: Optional[EmbeddingServiceAsyncClient] = None
        
        # Get circuit breaker config from worker config or use defaults
        circuit_breaker_config = {}
        if config.worker and isinstance(config.worker, dict):
            circuit_breaker_config = config.worker.get("circuit_breaker", {})
        
        # Circuit breaker for chunker service
        self._chunker_circuit = CircuitBreaker(
            failure_threshold=circuit_breaker_config.get("failure_threshold", 5),
            recovery_timeout=circuit_breaker_config.get("recovery_timeout", 60.0),
            success_threshold=circuit_breaker_config.get("success_threshold", 2),
            initial_backoff=circuit_breaker_config.get("initial_backoff", 5.0),
            max_backoff=circuit_breaker_config.get("max_backoff", 300.0),
            backoff_multiplier=circuit_breaker_config.get("backoff_multiplier", 2.0),
        )
        self._chunker_circuit.set_service_name("chunker")

    async def initialize(self) -> None:
        """Initialize chunker client."""
        if self.config.chunker and self.config.chunker.enabled:
            try:
                self._chunker_client = create_chunker_client(self.config.chunker)
                logger.info(
                    f"Initialized chunker client: {self.config.chunker.protocol}://"
                    f"{self.config.chunker.url}:{self.config.chunker.port}"
                )
            except Exception as e:
                logger.error(f"Failed to initialize chunker client: {e}")
                self._chunker_client = None
        # Initialize embedding client if configured
        if self.config.embedding and self.config.embedding.enabled:
            try:
                # Build base_url with explicit scheme for embedding service
                emb_url = self.config.embedding.url
                if "://" in emb_url:
                    base_url = emb_url
                else:
                    scheme = (
                        "https"
                        if self.config.embedding.protocol in ("https", "mtls")
                        else "http"
                    )
                    base_url = f"{scheme}://{emb_url}"

                emb_cfg = {
                    "server": {
                        "base_url": base_url,
                        "port": self.config.embedding.port,
                    },
                    "ssl": {
                        "enabled": self.config.embedding.protocol in ("https", "mtls"),
                        "cert_file": self.config.embedding.cert_file,
                        "key_file": self.config.embedding.key_file,
                        "ca_cert_file": self.config.embedding.ca_cert_file,
                        "check_hostname": False,
                    },
                    "client": {"timeout": self.config.embedding.timeout or 30.0},
                    "auth": {"method": "none"},
                }
                self._embedding_client = EmbeddingServiceAsyncClient.from_config_dict(
                    emb_cfg
                )
                logger.info(
                    f"Initialized embedding client: {self.config.embedding.protocol}://"
                    f"{self.config.embedding.url}:{self.config.embedding.port}"
                )
            except Exception as e:
                logger.error(f"Failed to initialize embedding client: {e}")
                self._embedding_client = None

    async def chunk_text(self, text: str, **params) -> Optional[List[Any]]:
        """
        Chunk text using the chunker service with retry logic and circuit breaker.

        Args:
            text: Text to chunk
            **params: Additional parameters for chunking

        Returns:
            List of chunks or None if chunker is not available or all retries failed
        """
        if not self._chunker_client:
            logger.warning("Chunker client is not available")
            return None

        # Check circuit breaker before attempting
        if not self._chunker_circuit.should_attempt():
            backoff_delay = self._chunker_circuit.get_backoff_delay()
            logger.debug(
                f"Circuit breaker is OPEN for chunker service, "
                f"skipping request (backoff: {backoff_delay:.1f}s)"
            )
            return None

        # Get retry configuration from server config
        retry_attempts = 3
        retry_delay = 5.0
        if self.config and self.config.chunker:
            retry_attempts = self.config.chunker.retry_attempts
            retry_delay = self.config.chunker.retry_delay

        for attempt in range(1, retry_attempts + 1):
            try:
                logger.info(
                    f"📤 Sending chunking request (attempt {attempt}/{retry_attempts}): "
                    f"text_length={len(text)}, params={params}"
                )
                logger.debug(
                    f"📤 Chunking request text preview (first 200 chars): {text[:200]}"
                )
                logger.debug(
                    f"📤 Full text to chunker ({len(text)} chars): {repr(text)}"
                )
                result = await self._chunker_client.chunk_text(text, **params)
                logger.debug(
                    f"📥 Received response from chunker: "
                    f"type={type(result)}, length={len(result) if result else 0}"
                )
                if result:
                    # Record success in circuit breaker
                    self._chunker_circuit.record_success()
                    logger.info(
                        f"Chunk_text succeeded (attempt {attempt}): received {len(result)} chunks, "
                        f"text_length={len(text)}"
                    )
                    # Log details about first chunk if available
                    if len(result) > 0:
                        first_chunk = result[0]
                        has_emb = (
                            hasattr(first_chunk, "embedding")
                            and getattr(first_chunk, "embedding", None) is not None
                        )
                        has_bm25 = (
                            hasattr(first_chunk, "bm25")
                            and getattr(first_chunk, "bm25", None) is not None
                        )
                        logger.debug(
                            f"First chunk: has_embedding={has_emb}, has_bm25={has_bm25}, "
                            f"type={getattr(first_chunk, 'type', 'N/A')}"
                        )
                    return result
                else:
                    logger.warning(
                        f"Chunk_text returned None/empty (attempt {attempt}/{retry_attempts}) "
                        f"for text_length={len(text)}"
                    )
                    if attempt < retry_attempts:
                        logger.info(f"Retrying in {retry_delay}s...")
                        await asyncio.sleep(retry_delay)
                    else:
                        return None
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)

                # Enhanced logging for SVOServerError
                if error_type == "SVOServerError":
                    # Check if it's a Model RPC server error (infrastructure issue)
                    is_model_rpc_error = (
                        "Model RPC server" in error_msg
                        or "failed after 3 attempts" in error_msg
                        or (hasattr(e, "code") and getattr(e, "code") == -32603)
                    )

                    # Record failure in circuit breaker
                    self._chunker_circuit.record_failure()

                    if is_model_rpc_error:
                        # Model RPC server is down - use warning level (infrastructure issue)
                        log_level = (
                            logger.warning if attempt < retry_attempts else logger.error
                        )
                        log_level(
                            f"Model RPC server unavailable (attempt {attempt}/{retry_attempts}, "
                            f"length={len(text)}): {error_msg}. "
                            f"Check Model RPC server status."
                        )
                    else:
                        # Other SVO server errors - log as error
                        logger.error(
                            f"Chunker service error (attempt {attempt}/{retry_attempts}, "
                            f"length={len(text)}): {error_type}: {error_msg}",
                            exc_info=True,
                        )

                    # Log error code if available
                    if hasattr(e, "code"):
                        logger.debug(f"Chunker error code: {getattr(e, 'code', 'N/A')}")
                    if hasattr(e, "message"):
                        logger.debug(
                            f"Chunker error message: {getattr(e, 'message', 'N/A')}"
                        )
                else:
                    logger.error(
                        f"Chunker service error (attempt {attempt}/{retry_attempts}, "
                        f"length={len(text)}, type={error_type}): {error_msg}",
                        exc_info=True,
                    )

                # Record failure in circuit breaker
                self._chunker_circuit.record_failure()

                if attempt < retry_attempts:
                    logger.info(f"Retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        f"All retry attempts failed for chunker (length={len(text)}, "
                        f"type={error_type}): {error_msg}",
                        exc_info=True,
                    )

        return None

    async def get_embeddings(self, chunks: List[Any], **params) -> Optional[List[Any]]:
        """
        Get embeddings for chunks using chunker service.

        The chunker service handles both chunking and embeddings.
        It returns chunks with embeddings, bm25, and other metadata.

        Args:
            chunks: List of chunks (SemanticChunk objects with text/body attributes)
            **params: Additional parameters for chunking

        Returns:
            List of chunks with embeddings or None if chunker is not available
        """
        if not self._chunker_client:
            logger.warning("Chunker client is not available")
            return None

        # Check circuit breaker before attempting
        if not self._chunker_circuit.should_attempt():
            backoff_delay = self._chunker_circuit.get_backoff_delay()
            logger.debug(
                f"Circuit breaker is OPEN for chunker service, "
                f"skipping embedding request (backoff: {backoff_delay:.1f}s)"
            )
            return None

        try:
            # Extract text from chunks if they are SemanticChunk objects
            texts = []
            for chunk in chunks:
                if hasattr(chunk, "text") and chunk.text:
                    texts.append(chunk.text)
                elif hasattr(chunk, "body") and chunk.body:
                    texts.append(chunk.body)
                elif isinstance(chunk, str):
                    texts.append(chunk)
                else:
                    logger.debug(f"Skipping chunk with no text: {type(chunk)}")
                    continue

            if not texts:
                logger.warning("No valid text found in chunks")
                return None

            # Join texts and chunk with chunker service
            # The chunker service chunk_text returns chunks with embeddings, bm25, etc.
            # CRITICAL: Worker should ONLY use chunker service, not embedding service directly
            combined_text = "\n\n".join(texts)

            # Ensure type parameter is passed to chunker for proper embedding generation
            chunker_params = params.copy()
            if "type" not in chunker_params:
                chunker_params["type"] = "DocBlock"  # Default type for docstrings

            try:
                result = await self._chunker_client.chunk_text(
                    combined_text, **chunker_params
                )
                # Record success if we got a result
                if result:
                    self._chunker_circuit.record_success()
            except Exception as chunker_error:
                # Record failure in circuit breaker
                self._chunker_circuit.record_failure()
                error_type = type(chunker_error).__name__
                error_msg = str(chunker_error)
                logger.error(
                    f"Chunker service error when getting embeddings: {error_type}: {error_msg}",
                    exc_info=True,
                )
                # Log additional error details if available
                if hasattr(chunker_error, "code"):
                    logger.error(
                        f"Chunker error code: {getattr(chunker_error, 'code', 'N/A')}"
                    )
                if hasattr(chunker_error, "message"):
                    logger.error(
                        f"Chunker error message: {getattr(chunker_error, 'message', 'N/A')}"
                    )
                return None

            # Chunker should always return embeddings - if not, log warning
            if result:
                has_embeddings = any(
                    getattr(c, "embedding", None) is not None for c in result
                )
                if not has_embeddings:
                    logger.warning(
                        f"Chunker returned {len(result)} chunks but no embeddings. "
                        f"This may indicate a configuration issue with the chunker service. "
                        f"Text length: {len(combined_text)}, params: {chunker_params}"
                    )
            elif result is None:
                logger.warning(
                    f"Chunker returned None (no chunks). "
                    f"Text length: {len(combined_text)}, params: {chunker_params}"
                )
            return result
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(
                f"Error getting embeddings from chunker: {error_type}: {error_msg}",
                exc_info=True,
            )
            return None

    async def chunk_and_embed(self, text: str, **chunk_params) -> Optional[List[Any]]:
        """
        Chunk text and get embeddings in one call.

        Args:
            text: Text to chunk and embed
            **chunk_params: Additional parameters for chunking

        Returns:
            List of chunks with embeddings or None if services are not available
        """
        chunks = await self.chunk_text(text, **chunk_params)
        if not chunks:
            return None

        return await self.get_embeddings(chunks)

    async def health_check(self) -> dict:
        """
        Check health of chunker service.

        Returns:
            Dictionary with health status
        """
        result = {
            "chunker": {"available": False, "error": None, "circuit_state": None},
        }

        if self._chunker_client:
            try:
                await self._chunker_client.health()
                result["chunker"]["available"] = True
                self._chunker_circuit.record_success()
            except Exception as e:
                result["chunker"]["error"] = str(e)
                self._chunker_circuit.record_failure()

        result["chunker"]["circuit_state"] = self._chunker_circuit.get_state().value
        return result

    def get_circuit_state(self) -> str:
        """
        Get current circuit breaker state.

        Returns:
            Circuit state as string
        """
        return self._chunker_circuit.get_state().value

    def get_backoff_delay(self) -> float:
        """
        Get current backoff delay.

        Returns:
            Backoff delay in seconds
        """
        return self._chunker_circuit.get_backoff_delay()

    async def close(self) -> None:
        """Close chunker client connection."""
        if self._chunker_client:
            await self._chunker_client.close()
        if self._embedding_client:
            await self._embedding_client._adapter_transport.close()

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
