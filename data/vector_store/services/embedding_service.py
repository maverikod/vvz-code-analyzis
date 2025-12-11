import logging
import numpy as np
from typing import Optional, List, Dict, Any
import json
import traceback
from vector_store.services.embedding_client_adapter import EmbeddingClientAdapter

logger = logging.getLogger("vector_store.embedding")

class EmbeddingService:
    """
    Service for working with text embeddings.
    Responsible for:
    - Converting text to vectors via HTTP API (через EmbeddingClientAdapter)
    - Caching embeddings
    """

    def __init__(self, model_name: str, cache_client: Optional[Any] = None, embedding_url: Optional[str] = None, expected_dimension: Optional[int] = None, port: int = None):
        # print(f"[EmbeddingService.__init__] model_name={model_name}, embedding_url={embedding_url}, expected_dimension={expected_dimension}, port={port}")
        self.model_name = model_name
        self.cache = cache_client
        self.embedding_url = embedding_url
        self.expected_dimension = expected_dimension or 384
        self.port = port

        if not self.embedding_url:
            logger.error("КРИТИЧЕСКАЯ ОШИБКА: embedding_url не указан в конфигурации")
            raise ValueError("embedding_url is required")

        if not self.port:
            try:
                from urllib.parse import urlparse
                parsed_url = urlparse(self.embedding_url)
                if parsed_url.port:
                    self.port = parsed_url.port
            except Exception as e:
                logger.warning(f"Failed to extract port from URL: {e}")
                raise
        # Используем EmbeddingClientAdapter вместо прямого httpx

        logger.debug(f"[EmbeddingService.__init__] port={self.port}, embedding_url={self.embedding_url}, expected_dimension={self.expected_dimension}")
        logger.info(f"Инициализация сервиса эмбеддингов: модель={model_name}, URL={embedding_url}, ожидаемая размерность={self.expected_dimension}")
        logger.info(f"Кэширование: {'включено' if cache_client else 'отключено'}")

    async def get_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        # print(f"[EmbeddingService.get_embedding] text[:30]={text[:30]}, model={model}")
        client = EmbeddingClientAdapter(
            model_name=self.model_name,
            base_url=self.embedding_url,
            port=self.port,
            expected_dimension=self.expected_dimension
        )
        try:
            return await client.get_embedding(text, model)
        except Exception as e:
            logger.error(f"[EmbeddingService.get_embedding] Ошибка при получении эмбеддинга: {e}")
            raise
        finally:
            await client.close()

# Для тестирования можно использовать эту стратегию
class RandomEmbeddingStrategy:
    """Стратегия для генерации случайных эмбеддингов (для тестов)"""

    def __init__(self, vector_size=384, expected_dimension=None):
        # print(f"[RandomEmbeddingStrategy.__init__] vector_size={vector_size}, expected_dimension={expected_dimension}")
        self.vector_size = expected_dimension or vector_size
        self.expected_dimension = self.vector_size  # Для совместимости с EmbeddingService
        logger.warning("ВНИМАНИЕ: Используется RandomEmbeddingStrategy - только для тестирования!")
        logger.info(f"Инициализирована тестовая стратегия с размерностью векторов: {self.vector_size}")

    async def get_embedding(self, text: str, model=None) -> List[float]:
        # print(f"[RandomEmbeddingStrategy.get_embedding] text[:30]={text[:30]}, model={model}")
        text_hash = abs(hash(text)) & 0xFFFFFFFF
        np.random.seed(text_hash)
        vector = np.random.rand(self.vector_size).astype(np.float32).tolist()
        logger.info(f"Сгенерирован случайный вектор размерности {self.vector_size} (тестовый режим)")

        if self.expected_dimension and len(vector) != self.expected_dimension:
            error_msg = f"Ошибка размерности вектора: получено {len(vector)}, ожидается {self.expected_dimension}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        return vector
