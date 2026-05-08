"""
Helpers for storing/querying pgvector columns (PostgreSQL ``vector`` type).

Embeddings are serialized as pgvector text input ``[f1,f2,...]`` and cast with
``%s::vector`` so pool connections do not require per-connection type registration.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Sequence


def numpy_embedding_to_pgvector_text(embedding: Any) -> str:
    """
    Format a 1-D float embedding for PostgreSQL ``::vector`` cast.

    Accepts a sequence of floats or a numpy ndarray (including ``float32``).
    """
    try:
        import numpy as np

        if hasattr(embedding, "reshape"):
            flat = np.asarray(embedding, dtype="float64").reshape(-1)
            return "[" + ",".join(str(float(x)) for x in flat.tolist()) + "]"
    except Exception:
        pass
    seq = list(embedding)
    return "[" + ",".join(str(float(x)) for x in seq) + "]"


def normalize_embedding_sequence(values: Sequence[float]) -> list[float]:
    """L2-normalize a sequence (same convention as FAISS / semantic_search query)."""
    try:
        import numpy as np

        v = np.asarray(values, dtype="float32").reshape(-1)
        n = float(np.linalg.norm(v))
        if n <= 0:
            return []
        return (v / n).astype("float32").tolist()
    except Exception:
        return []
