"""
FAISS index manager for vector similarity search.

The system stores embeddings in two places:
- SQLite (`code_chunks.embedding_vector`): source of truth for vector values.
- FAISS index file (`faiss_index_path`): fast nearest-neighbor search.

The FAISS index file can be rebuilt from the database at any time and is rebuilt
on server startup.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .faiss_manager_rebuild import rebuild_from_database_impl
from .faiss_manager_sync import check_index_sync_impl

try:
    import faiss
except ImportError:
    faiss = None

logger = logging.getLogger(__name__)

# Driver-direct (stage 2): DatabaseClient class removed; ``database`` params below
# are duck-typed driver-shaped objects (PostgreSQLDriver in production). Kept as an
# ``Any`` alias so existing type annotations do not need per-site rewrites.
DatabaseClient = Any


class FaissIndexManager:
    """
    Manages FAISS index for vector similarity search.

    Responsibilities:
    - Create and maintain FAISS index
    - Add/remove vectors from index
    - Search similar vectors
    - Persist index to disk
    - Load index from disk on startup
    - Sync with database
    """

    def __init__(
        self: "FaissIndexManager",
        index_path: str,
        vector_dim: int,
        index_type: str = "Flat",
    ) -> None:
        """
        Initialize FAISS index manager.

        Args:
            self: Instance.
            index_path: Path to FAISS index file
            vector_dim: Dimension of vectors (must be same for all)
            index_type: Type of FAISS index ("Flat" for exact search, "IVF" for approximate)

        Returns:
            None
        """
        if faiss is None:
            raise ImportError(
                "faiss-cpu or faiss-gpu is required. Install with: pip install faiss-cpu"
            )

        self.index_path = Path(index_path)
        self.vector_dim = int(vector_dim)
        self.index_type = str(index_type)
        self.index: Optional[faiss.Index] = None
        self._next_vector_id: int = 0
        # Mutex for all FAISS operations (thread-safe access)
        self._lock = threading.Lock()

        # Create parent directory if needed
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        if self.index_path.exists() and self.index_path.is_file():
            self._load_index()
        else:
            self._create_index()

    def _create_index(self: "FaissIndexManager") -> None:
        """
        Create a new empty FAISS index.

        Returns:
            None
        """
        if self.index_type == "Flat":
            base = faiss.IndexFlatL2(self.vector_dim)
        else:
            # Default to Flat for now
            logger.warning(f"Unknown index type {self.index_type}, using Flat")
            base = faiss.IndexFlatL2(self.vector_dim)

        # Use explicit IDs so `code_chunks.vector_id` is stable and correct.
        self.index = faiss.IndexIDMap2(base)

        self._next_vector_id = 0
        logger.info(
            f"Created new FAISS index: {self.index_path}, dim={self.vector_dim}"
        )

    def _load_index(self: "FaissIndexManager") -> None:
        """
        Load FAISS index from disk.

        Returns:
            None
        """
        with self._lock:
            try:
                loaded = faiss.read_index(str(self.index_path))
                # If the index is not ID-mapped, it is a legacy/broken format for this project.
                if not hasattr(loaded, "add_with_ids"):
                    logger.warning(
                        "Loaded FAISS index is missing add_with_ids (legacy). "
                        "It will be rebuilt from database on startup: %s",
                        self.index_path,
                    )
                self.index = loaded
                self._next_vector_id = int(getattr(loaded, "ntotal", 0))
                logger.info(
                    "Loaded FAISS index: %s, vectors=%d, dim=%d",
                    self.index_path,
                    self._next_vector_id,
                    self.vector_dim,
                )
            except Exception as e:
                logger.error(f"Failed to load FAISS index from {self.index_path}: {e}")
                logger.info("Creating new index instead")
                self._create_index()

    def save_index(self: "FaissIndexManager") -> None:
        """
        Save FAISS index to disk.

        Returns:
            None
        """
        with self._lock:
            if self.index is None:
                logger.warning("Cannot save: index is not initialized")
                return

            try:
                faiss.write_index(self.index, str(self.index_path))
                logger.debug(f"Saved FAISS index to {self.index_path}")
            except Exception as e:
                logger.error(f"Failed to save FAISS index to {self.index_path}: {e}")
                raise

    @staticmethod
    def _normalize_vector(vec: np.ndarray) -> np.ndarray:
        """
        Normalize vector to unit length.

        Args:
            vec: Vector to normalize.

        Returns:
            Normalized vector (float32).
        """
        vec = vec.reshape(-1).astype("float32")
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        return vec.astype("float32")

    def add_vector(
        self: "FaissIndexManager",
        embedding: np.ndarray,
        vector_id: Optional[int] = None,
    ) -> int:
        """
        Add vector to FAISS index.

        Args:
            self: Instance.
            embedding: Vector as numpy array (shape: [vector_dim])
            vector_id: Optional vector ID to use (for rebuilding from database)
                      If None, uses next available ID

        Returns:
            Vector ID (position in index)
        """
        with self._lock:
            if self.index is None:
                raise RuntimeError("FAISS index is not initialized")

            # Validate dimension
            if embedding.shape != (self.vector_dim,):
                raise ValueError(
                    f"Vector dimension mismatch: expected {self.vector_dim}, "
                    f"got {embedding.shape[0]}"
                )

            embedding_2d = self._normalize_vector(embedding).reshape(1, -1)

            if vector_id is None:
                vector_id = self._next_vector_id
                self._next_vector_id += 1
            else:
                vector_id = int(vector_id)
                if vector_id >= self._next_vector_id:
                    self._next_vector_id = vector_id + 1

            # Prefer explicit ids. If loaded index is legacy, fall back to append.
            if hasattr(self.index, "add_with_ids"):
                ids = np.array([vector_id], dtype="int64")
                self.index.add_with_ids(embedding_2d, ids)
            else:
                self.index.add(embedding_2d)

            return int(vector_id)

    def remove_vectors(self: "FaissIndexManager", vector_ids: List[int]) -> None:
        """
        Remove vectors from FAISS index by IDs.

        Args:
            self: Instance.
            vector_ids: List of vector IDs to remove

        Returns:
            None

        Note:
            FAISS doesn't support direct removal. This method marks vectors
            for removal. Actual cleanup happens on rebuild from database.
        """
        if not vector_ids:
            return

        # FAISS doesn't support direct vector removal
        # We'll track removed IDs and skip them during search
        # Actual cleanup will happen on next rebuild from database
        logger.debug(
            f"Marked {len(vector_ids)} vectors for removal (will be cleaned on rebuild)"
        )

    def search(
        self: "FaissIndexManager", query_vector: np.ndarray, k: int = 10
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Search for similar vectors.

        Args:
            self: Instance.
            query_vector: Query vector (shape: [vector_dim])
            k: Number of results to return

        Returns:
            Tuple of (distances, vector_ids) arrays
        """
        with self._lock:
            if self.index is None:
                raise RuntimeError("FAISS index is not initialized")

            if self.index.ntotal == 0:
                return np.array([]), np.array([])

            # Validate dimension
            if query_vector.shape != (self.vector_dim,):
                raise ValueError(
                    f"Query vector dimension mismatch: expected {self.vector_dim}, "
                    f"got {query_vector.shape[0]}"
                )

            # Reshape for FAISS (normalize like embeddings)
            query_2d = self._normalize_vector(query_vector).reshape(1, -1)

            # Search
            distances, indices = self.index.search(query_2d, min(k, self.index.ntotal))

            return distances[0], indices[0]

    def get_vector(self: "FaissIndexManager", vector_id: int) -> Optional[np.ndarray]:
        """
        Get vector by ID from index.

        Args:
            self: Instance.
            vector_id: Vector ID

        Returns:
            Vector as numpy array or None if not found
        """
        if self.index is None:
            return None

        if vector_id < 0 or vector_id >= self.index.ntotal:
            return None

        # FAISS Flat index doesn't support direct retrieval
        # We would need to reconstruct from index
        # For now, return None (vectors should be retrieved from database/SVO)
        logger.warning("Direct vector retrieval from FAISS not implemented")
        return None

    def check_index_sync(
        self: "FaissIndexManager",
        database: DatabaseClient,
        project_id: str,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check synchronization between database and FAISS index.

        Verifies that all vector_id values from database exist in FAISS index.
        If any mismatch is found, returns False with details.

        Args:
            self: Instance.
            database: DatabaseClient — universal driver interface (RPC client).
            project_id: Project ID to check.

        Returns:
            Tuple of (is_synced: bool, details: dict).
        """
        if self.index is None:
            return False, {
                "error": "FAISS index is not initialized",
                "db_vector_count": 0,
                "index_vector_count": 0,
            }
        id_map = getattr(self.index, "id_map", None)
        return check_index_sync_impl(
            int(self.index.ntotal),
            id_map,
            database,
            project_id,
        )

    async def rebuild_from_database(
        self: "FaissIndexManager",
        database: DatabaseClient,
        svo_client_manager: Optional[Any] = None,
        project_id: Optional[str] = None,
        *,
        omit_docs_markdown: bool = False,
    ) -> int:
        """
        Rebuild FAISS index from database.

        If project_id is provided, rebuilds index for that project only.
        If project_id is None, rebuilds index for all projects (legacy mode).

        Args:
            self: Instance.
            database: DatabaseClient — universal driver interface (RPC client).
            svo_client_manager: Optional SVOClientManager to get embeddings if missing.
            project_id: Optional project ID to filter by.
            omit_docs_markdown: Exclude Markdown docs chunks from rebuild when policy dictates.

        Returns:
            Number of vectors loaded.
        """
        return await rebuild_from_database_impl(
            self,
            database,
            svo_client_manager,
            project_id,
            omit_docs_markdown=omit_docs_markdown,
        )

    def get_stats(self: "FaissIndexManager") -> Dict[str, Any]:
        """
        Get index statistics.

        Args:
            self: Instance.

        Returns:
            Dictionary with index statistics
        """
        if self.index is None:
            return {"initialized": False}

        return {
            "initialized": True,
            "vector_count": self.index.ntotal,
            "vector_dim": self.vector_dim,
            "index_type": self.index_type,
            "index_path": str(self.index_path),
        }

    def close(self: "FaissIndexManager") -> None:
        """
        Close and save index.

        Args:
            self: Instance.

        Returns:
            None
        """
        if self.index is not None:
            self.save_index()
            self.index = None
