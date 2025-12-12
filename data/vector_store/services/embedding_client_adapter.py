"""
Embedding client adapter for vector store.

This module provides an adapter for the embedding service client.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Optional, List, Any
import numpy as np
import json
from embed_client.async_client import EmbeddingServiceAsyncClient, EmbeddingServiceError

logger = logging.getLogger("vector_store.embedding_client_adapter")

class EmbeddingClientAdapter:
    def __init__(self, model_name: str, base_url: str, port: int, expected_dimension: int = 384):
        # print(f"[EmbeddingClientAdapter.__init__] model_name={model_name}, base_url={base_url}, port={port}, expected_dimension={expected_dimension}")
        self.model_name = model_name

        # Убедимся, что base_url не содержит порт или '/cmd' на конце
        if base_url.endswith('/cmd'):
            base_url = base_url[:-4]

        # Убедимся, что base_url не содержит порт (порт передается отдельно)
        if ':' in base_url.split('/')[-1]:
            # Удаляем порт из URL
            parts = base_url.split(':')
            if len(parts) > 2 and parts[0].startswith('http'):
                # URL вида http://hostname:port
                base_url = f"{parts[0]}:{parts[1]}"

        self.base_url = base_url
        self.port = port
        self.expected_dimension = expected_dimension
        self._client: Optional[EmbeddingServiceAsyncClient] = None
        logger.info(f"Инициализирован EmbeddingClientAdapter: URL={self.base_url}, port={self.port}")

    async def _get_client(self) -> EmbeddingServiceAsyncClient:
        if self._client is None:
            logger.info(f"Создание нового клиента: base_url={self.base_url}, port={self.port}")
            self._client = EmbeddingServiceAsyncClient(base_url=self.base_url, port=self.port)
            await self._client.__aenter__()
        return self._client

    async def get_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        # print(f"[EmbeddingClientAdapter.get_embedding] text[:30]={text[:30]}, model={model}")
        if not text or text.strip() == "":
            logger.error("Text for embedding is empty")
            raise ValueError("Text for embedding is empty")
        used_model = model or self.model_name
        try:
            logger.info(f"Получение эмбеддинга для текста (первые 50 символов): '{text[:50]}...'")
            client = await self._get_client()
            params = {"texts": [text]}
            if used_model:
                params["model"] = used_model
            logger.info(f"Отправка запроса к сервису эмбеддингов: params={params}")
            result = await client.cmd("embed", params=params)

            # Детальное логирование для отладки структуры ответа
            logger.info(f"Получен ответ от сервиса эмбеддингов (тип: {type(result)})")
            result_str = str(result)
            logger.info(f"Сокращенный ответ: {result_str[:500]}...")

            if isinstance(result, dict):
                logger.info(f"Ключи в ответе: {list(result.keys())}")
                if "result" in result:
                    logger.info(f"Тип result: {type(result['result'])}")
                    if isinstance(result['result'], dict):
                        logger.info(f"Ключи в result: {list(result['result'].keys())}")

            # Поддержка множества форматов ответа:
            # 1. {'result': [...]} - старый формат
            # 2. {'result': {'embeddings': [...], 'model': '...', 'tokens': N}} - новый формат с embeddings
            # 3. {'result': {'result': [...]} или {'result': {'result': {'embeddings': [...]}}} - вложенные структуры

            if not result or not isinstance(result, dict):
                logger.error(f"Invalid embedding response type: {type(result)}")
                raise RuntimeError("Invalid embedding response type")

            if "result" not in result:
                logger.error(f"Missing 'result' key in response: {result}")
                raise RuntimeError("Missing 'result' key in embedding response")

            result_data = result.get("result")

            # Рекурсивно ищем ключи, которые могут содержать эмбеддинги
            embedding = self._extract_embedding(result_data)

            if embedding is None:
                logger.error(f"Failed to extract embedding from response: {result}")
                raise RuntimeError("Invalid embedding response structure")

            logger.info(f"Извлеченный embedding: тип={type(embedding)}, длина={len(embedding)}, первые 5 значений={embedding[:5]}")

            if len(embedding) != self.expected_dimension:
                logger.error(f"Embedding dimension mismatch: got {len(embedding)}, expected {self.expected_dimension}")
                raise ValueError(f"Embedding dimension mismatch: got {len(embedding)}, expected {self.expected_dimension}")

            return embedding
        except EmbeddingServiceError as e:
            logger.error(f"Embedding service error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in embedding client: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    def _extract_embedding(self, data: Any) -> Optional[List[float]]:
        # print(f"[EmbeddingClientAdapter._extract_embedding] data type={type(data)}")
        """
        Рекурсивно извлекает эмбеддинг из различных форматов ответа.
        """
        if data is None:
            logger.debug("Получен None в _extract_embedding")
            return None

        # Если это список и первый элемент похож на вектор эмбеддинга
        if isinstance(data, list) and len(data) > 0:
            logger.debug(f"Обрабатываем список длиной {len(data)}")
            # Если первый элемент похож на вектор (список чисел)
            if isinstance(data[0], list) and len(data[0]) > 0 and isinstance(data[0][0], (int, float)):
                logger.debug(f"Нашли список векторов, возвращаем первый вектор длиной {len(data[0])}")
                return data[0]  # Возвращаем первый вектор из списка векторов
            # Если сам список похож на вектор (список чисел)
            elif len(data) >= self.expected_dimension and all(isinstance(x, (int, float)) for x in data[:10]):
                logger.debug(f"Нашли вектор длиной {len(data)}")
                return data  # Возвращаем сам список как вектор

        # Если словарь, ищем по известным ключам
        if isinstance(data, dict):
            logger.debug(f"Обрабатываем словарь с ключами: {list(data.keys())}")
            # Прямой поиск по известным ключам
            for key in ['embeddings', 'embedding', 'vectors', 'vector', 'result']:
                if key in data:
                    logger.debug(f"Найден ключ '{key}' в словаре")
                    # Рекурсивно обрабатываем значение
                    embedding = self._extract_embedding(data[key])
                    if embedding:
                        return embedding

            # Если ничего не нашли, проверяем все значения в словаре
            logger.debug("Проверяем все значения в словаре")
            for key, value in data.items():
                logger.debug(f"Проверяем значение по ключу '{key}'")
                embedding = self._extract_embedding(value)
                if embedding:
                    return embedding

        logger.debug(f"Не удалось извлечь эмбеддинг из данных типа {type(data)}")
        return None

    async def close(self):
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None
