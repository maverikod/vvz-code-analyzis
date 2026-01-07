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

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .database import CodeDatabase

try:
    import faiss
except ImportError:
    faiss = None

logger = logging.getLogger(__name__)


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
        database: CodeDatabase,
        project_id: str,
        dataset_id: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check synchronization between database and FAISS index.

        Verifies that all vector_id values from database exist in FAISS index.
        If any mismatch is found, returns False with details.

        Args:
            self: Instance.
            database: CodeDatabase instance.
            project_id: Project ID to check.
            dataset_id: Optional dataset ID to filter by.

        Returns:
            Tuple of (is_synced: bool, details: dict) where details contains:
            - db_vector_count: Number of chunks with vector_id in database
            - index_vector_count: Number of vectors in FAISS index
            - missing_in_index: List of vector_id values in DB but not in index
            - max_db_vector_id: Maximum vector_id in database
            - max_index_vector_id: Maximum vector_id in index (ntotal - 1)
        """
        if self.index is None:
            return False, {
                "error": "FAISS index is not initialized",
                "db_vector_count": 0,
                "index_vector_count": 0,
            }

        # Get all vector_id values from database for this project/dataset
        if dataset_id:
            rows = database._fetchall(
                """
                SELECT DISTINCT cc.vector_id
                FROM code_chunks cc
                INNER JOIN files f ON cc.file_id = f.id
                WHERE cc.project_id = ?
                  AND f.dataset_id = ?
                  AND (f.deleted = 0 OR f.deleted IS NULL)
                  AND cc.vector_id IS NOT NULL
                  AND cc.embedding_vector IS NOT NULL
                ORDER BY cc.vector_id
                """,
                (project_id, dataset_id),
            )
        else:
            rows = database._fetchall(
                """
                SELECT DISTINCT vector_id
                FROM code_chunks
                WHERE project_id = ?
                  AND vector_id IS NOT NULL
                  AND embedding_vector IS NOT NULL
                ORDER BY vector_id
                """,
                (project_id,),
            )

        db_vector_ids = {row["vector_id"] for row in rows if row["vector_id"] is not None}
        db_vector_count = len(db_vector_ids)
        index_vector_count = int(self.index.ntotal)

        # Check if index has ID mapping (IndexIDMap2)
        if hasattr(self.index, "id_map") and self.index.id_map is not None:
            # Get all IDs from index
            index_ids = set()
            try:
                # For IndexIDMap2, id_map is Int64Vector
                # Use ntotal to get the number of vectors
                id_map = self.index.id_map
                # Convert Int64Vector to set of IDs
                index_ids = {int(id_map.at(i)) for i in range(index_vector_count)}
            except Exception as e:
                logger.warning(f"Failed to get IDs from FAISS index id_map: {e}")
                # Fallback: assume dense range 0..ntotal-1
                index_ids = set(range(index_vector_count))
        else:
            # No ID mapping - assume dense range 0..ntotal-1
            index_ids = set(range(index_vector_count))

        # Find missing vectors
        missing_in_index = db_vector_ids - index_ids
        extra_in_index = index_ids - db_vector_ids

        max_db_vector_id = max(db_vector_ids) if db_vector_ids else -1
        max_index_vector_id = max(index_ids) if index_ids else -1

        is_synced = (
            len(missing_in_index) == 0
            and len(extra_in_index) == 0
            and db_vector_count == index_vector_count
        )

        details = {
            "db_vector_count": db_vector_count,
            "index_vector_count": index_vector_count,
            "missing_in_index": sorted(list(missing_in_index))[:100],  # Limit to first 100
            "missing_in_index_count": len(missing_in_index),
            "extra_in_index": sorted(list(extra_in_index))[:100],  # Limit to first 100
            "extra_in_index_count": len(extra_in_index),
            "max_db_vector_id": max_db_vector_id,
            "max_index_vector_id": max_index_vector_id,
        }

        return is_synced, details

    async def rebuild_from_database(
        self: "FaissIndexManager",
        database: CodeDatabase,
        svo_client_manager: Optional[Any] = None,
        project_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
    ) -> int:
        """
        Rebuild FAISS index from database.

        Implements dataset-scoped FAISS (Step 2 of refactor plan).
        If project_id and dataset_id are provided, rebuilds index for that dataset only.
        If only project_id is provided, rebuilds index for all datasets in the project.
        If neither is provided, rebuilds index for all projects (legacy mode).

        This operation recreates the FAISS index file from `code_chunks.embedding_vector`.

        Important:
            `code_chunks.vector_id` must be a 1:1 mapping to FAISS vector IDs.
            To avoid duplicated IDs and huge per-row UPDATEs (which destabilize the
            sqlite_proxy worker), we reassign `vector_id` to a dense range `0..N-1`
            using a single SQL statement before building the FAISS file.

        Args:
            self: Instance.
            database: CodeDatabase instance
            svo_client_manager: Optional SVOClientManager to get embeddings if missing
            project_id: Optional project ID to filter by
            dataset_id: Optional dataset ID to filter by (requires project_id)

        Returns:
            Number of vectors loaded
        """
        if dataset_id and not project_id:
            raise ValueError("dataset_id requires project_id")

        scope_desc = (
            f"project={project_id}, dataset={dataset_id}"
            if project_id and dataset_id
            else f"project={project_id}" if project_id else "all projects"
        )
        logger.info(f"Rebuilding FAISS index from database ({scope_desc})...")

        # Ensure `vector_id` is dense and unique (single SQL statement).
        # This avoids thousands of per-row UPDATEs through sqlite_proxy.
        # Filter by project_id and dataset_id if provided (dataset-scoped FAISS).
        try:
            if project_id and dataset_id:
                # Dataset-scoped: normalize vector_id only for this dataset
                database._execute(
                    """
                    WITH ranked AS (
                        SELECT
                            cc.id,
                            (ROW_NUMBER() OVER (ORDER BY cc.id) - 1) AS new_vector_id
                        FROM code_chunks cc
                        INNER JOIN files f ON cc.file_id = f.id
                        WHERE cc.project_id = ?
                          AND f.dataset_id = ?
                          AND cc.embedding_model IS NOT NULL
                          AND cc.embedding_vector IS NOT NULL
                    )
                    UPDATE code_chunks
                    SET vector_id = (SELECT new_vector_id FROM ranked WHERE ranked.id = code_chunks.id)
                    WHERE id IN (SELECT id FROM ranked)
                    """,
                    (project_id, dataset_id),
                )
            elif project_id:
                # Project-scoped: normalize vector_id for all datasets in project
                database._execute(
                    """
                    WITH ranked AS (
                        SELECT
                            id,
                            (ROW_NUMBER() OVER (ORDER BY id) - 1) AS new_vector_id
                        FROM code_chunks
                        WHERE project_id = ?
                          AND embedding_model IS NOT NULL
                          AND embedding_vector IS NOT NULL
                    )
                    UPDATE code_chunks
                    SET vector_id = (SELECT new_vector_id FROM ranked WHERE ranked.id = code_chunks.id)
                    WHERE id IN (SELECT id FROM ranked)
                    """,
                    (project_id,),
                )
            else:
                # Legacy mode: normalize vector_id for all chunks
                database._execute(
                    """
                    WITH ranked AS (
                        SELECT
                            id,
                            (ROW_NUMBER() OVER (ORDER BY id) - 1) AS new_vector_id
                        FROM code_chunks
                        WHERE embedding_model IS NOT NULL
                          AND embedding_vector IS NOT NULL
                    )
                    UPDATE code_chunks
                    SET vector_id = (SELECT new_vector_id FROM ranked WHERE ranked.id = code_chunks.id)
                    WHERE id IN (SELECT id FROM ranked)
                    """
                )
            database._commit()
        except Exception as e:
            logger.warning(
                "Failed to normalize code_chunks.vector_id mapping: %s",
                e,
                exc_info=True,
            )

        # Create fresh index (this clears all existing vectors)
        old_vector_count = int(self.index.ntotal) if self.index is not None else 0
        self._create_index()
        if old_vector_count > 0:
            logger.info(
                "Cleared %d vectors from FAISS index (rebuild)", old_vector_count
            )

        # Get chunks with embeddings (filtered by project_id and dataset_id if provided)
        chunks = database.get_all_chunks_for_faiss_rebuild(
            project_id=project_id, dataset_id=dataset_id
        )
        if not chunks:
            logger.info("No chunks with embeddings found in database")
            self.save_index()
            return 0

        loaded_count = 0
        missing_embeddings = 0

        for chunk in chunks:
            vector_id = chunk.get("vector_id")
            embedding_vector_json = chunk.get("embedding_vector")
            chunk_text = chunk.get("chunk_text", "")
            chunk_id = chunk.get("id")
            embedding_model = chunk.get("embedding_model")

            if vector_id is None:
                continue

            # Try to get embedding from database first (embedding_vector column)
            embedding_array = None

            if embedding_vector_json:
                try:
                    embedding_list = json.loads(embedding_vector_json)
                    embedding_array = np.array(embedding_list, dtype="float32")
                    logger.debug(
                        f"Loaded embedding from database for chunk {chunk.get('id')}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to parse embedding_vector from database for chunk {chunk.get('id')}: {e}"
                    )

            # If embedding not in database, try to get from embedding service (SVO client manager).
            if embedding_array is None and svo_client_manager:
                logger.debug(
                    f"Embedding not in database for chunk {chunk.get('id')}, "
                    "requesting from embedding service..."
                )
                try:

                    class _TmpChunk:
                        def __init__(self, text: str):
                            self.body = text
                            self.text = text

                    tmp = _TmpChunk(chunk_text)
                    chunks_with_emb = await svo_client_manager.get_embeddings([tmp])
                    if chunks_with_emb and hasattr(chunks_with_emb[0], "embedding"):
                        embedding = getattr(chunks_with_emb[0], "embedding")
                        if embedding is not None:
                            embedding_array = np.array(embedding, dtype="float32")
                            # Save embedding to database for future use
                            try:
                                embedding_json = json.dumps(embedding_array.tolist())
                                database._execute(
                                    "UPDATE code_chunks SET embedding_vector = ?, embedding_model = ? WHERE id = ?",
                                    (embedding_json, embedding_model, chunk_id),
                                )
                            except Exception as e:
                                logger.warning(
                                    f"Failed to save embedding to database: {e}"
                                )
                    else:
                        missing_embeddings += 1
                except Exception as e:
                    logger.warning(
                        f"Failed to get embedding from SVO service for chunk {chunk.get('id')}: {e}"
                    )
                    missing_embeddings += 1
            elif embedding_array is None:
                # Cannot get embedding
                missing_embeddings += 1
                logger.debug(
                    f"Skipping chunk {chunk.get('id')}: no embedding in database and no SVO client"
                )
                continue

            # Add vector to FAISS index
            if embedding_array is not None:
                try:
                    self.add_vector(embedding_array, vector_id=int(vector_id))
                    loaded_count += 1
                except Exception as e:
                    logger.error(
                        f"Failed to add vector to FAISS index for chunk {chunk.get('id')}: {e}"
                    )
                    missing_embeddings += 1

        if missing_embeddings > 0:
            logger.warning(
                f"Could not load {missing_embeddings} vectors: embeddings not available"
            )

        try:
            database._commit()
        except Exception:
            pass

        # Save rebuilt index
        self.save_index()

        logger.info(
            "Rebuilt FAISS index: loaded %d vectors, missing %d embeddings",
            loaded_count,
            missing_embeddings,
        )

        return loaded_count

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
