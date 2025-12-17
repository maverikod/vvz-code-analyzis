"""
Manager for SVO chunker client.

Provides unified interface for working with chunker service which handles
both chunking and embeddings with mTLS support.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Optional, List, Any

from .config import ServerConfig, SVOServiceConfig
from .chunker_client_wrapper import create_chunker_client
from svo_client import ChunkerClient

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

    async def chunk_text(
        self, text: str, **params
    ) -> Optional[List[Any]]:
        """
        Chunk text using the chunker service with retry logic.

        Args:
            text: Text to chunk
            **params: Additional parameters for chunking

        Returns:
            List of chunks or None if chunker is not available or all retries failed
        """
        import asyncio
        
        if not self._chunker_client:
            logger.warning("Chunker client is not available")
            return None

        # Get retry configuration from server config
        retry_attempts = 3
        retry_delay = 5.0
        if self.config and self.config.chunker:
            retry_attempts = self.config.chunker.retry_attempts
            retry_delay = self.config.chunker.retry_delay

        last_error = None
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
                    logger.info(
                        f"Chunk_text succeeded (attempt {attempt}): received {len(result)} chunks, "
                        f"text_length={len(text)}"
                    )
                    # Log details about first chunk if available
                    if len(result) > 0:
                        first_chunk = result[0]
                        has_emb = hasattr(first_chunk, "embedding") and getattr(first_chunk, "embedding", None) is not None
                        has_bm25 = hasattr(first_chunk, "bm25") and getattr(first_chunk, "bm25", None) is not None
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
                last_error = e
                error_type = type(e).__name__
                error_msg = str(e)
                
                # Enhanced logging for SVOServerError
                if error_type == "SVOServerError":
                    logger.warning(
                        f"SVO server error chunking text (attempt {attempt}/{retry_attempts}, "
                        f"length={len(text)}): {error_msg}"
                    )
                    # Log error code if available
                    if hasattr(e, "code"):
                        logger.debug(f"Error code: {getattr(e, 'code', 'N/A')}")
                    if hasattr(e, "message"):
                        logger.debug(f"Error message: {getattr(e, 'message', 'N/A')}")
                else:
                    logger.warning(
                        f"Error chunking text (attempt {attempt}/{retry_attempts}, "
                        f"length={len(text)}, type={error_type}): {error_msg}"
                    )
                
                if attempt < retry_attempts:
                    logger.info(f"Retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        f"All retry attempts failed for chunk_text (length={len(text)}, "
                        f"type={error_type}): {error_msg}",
                        exc_info=True
                    )
        
        return None

    async def get_embeddings(
        self, chunks: List[Any], **params
    ) -> Optional[List[Any]]:
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
            combined_text = "\n\n".join(texts)
            result = await self._chunker_client.chunk_text(combined_text, **params)
            
            return result
        except Exception as e:
            logger.error(f"Error getting embeddings: {e}")
            return None

    async def chunk_and_embed(
        self, text: str, **chunk_params
    ) -> Optional[List[Any]]:
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
            "chunker": {"available": False, "error": None},
        }

        if self._chunker_client:
            try:
                await self._chunker_client.health()
                result["chunker"]["available"] = True
            except Exception as e:
                result["chunker"]["error"] = str(e)

        return result

    async def close(self) -> None:
        """Close chunker client connection."""
        if self._chunker_client:
            await self._chunker_client.close()

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

