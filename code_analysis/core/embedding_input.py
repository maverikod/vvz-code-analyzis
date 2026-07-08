"""
Shared embedding input adapter for semantic services.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class EmbeddingInput:
    """Container for embedding request/response data.

    Attributes:
        text: Text content to embed or that was embedded.
        id: Optional correlation key for tracking the input.
        embedding: Optional embedding vector after service response.
        embedding_model: Optional model name used to generate the embedding.
    """

    text: str
    id: Any = None
    embedding: Optional[List[float]] = None
    embedding_model: Optional[str] = None

    @property
    def body(self) -> str:
        """Return text content (alias for compatibility with get_chunk_text).

        Returns:
            The text field.
        """
        return self.text
