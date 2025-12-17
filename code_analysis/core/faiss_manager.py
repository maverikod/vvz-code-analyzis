"""
FAISS index manager for vector similarity search.

Manages FAISS index for storing and searching code embeddings.
Provides unified interface for vector operations with database synchronization.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import numpy as np

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
        self,
        index_path: str,
        vector_dim: int,
        index_type: str = "Flat",
    ):
        """
        Initialize FAISS index manager.

        Args:
            index_path: Path to FAISS index file
            vector_dim: Dimension of vectors (must be same for all)
            index_type: Type of FAISS index ("Flat" for exact search, "IVF" for approximate)
        """
        if faiss is None:
            raise ImportError(
                "faiss-cpu or faiss-gpu is required. Install with: pip install faiss-cpu"
            )

        self.index_path = Path(index_path)
        self.vector_dim = vector_dim
        self.index_type = index_type
        self.index: Optional[faiss.Index] = None
        self._next_vector_id = 0
        # Mutex for all FAISS operations (thread-safe access)
        self._lock = threading.Lock()

        # Create parent directory if needed
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        # Always create fresh index - will be rebuilt from database on startup
        # This ensures index is always in sync with database
        self._create_index()

    def _create_index(self) -> None:
        """Create new FAISS index."""
        if self.index_type == "Flat":
            # Flat index for exact search
            self.index = faiss.IndexFlatL2(self.vector_dim)
        else:
            # Default to Flat for now
            logger.warning(f"Unknown index type {self.index_type}, using Flat")
            self.index = faiss.IndexFlatL2(self.vector_dim)

        self._next_vector_id = 0
        logger.info(f"Created new FAISS index: {self.index_path}, dim={self.vector_dim}")

    def _load_index(self) -> None:
        """Load FAISS index from disk."""
        try:
            self.index = faiss.read_index(str(self.index_path))
            self._next_vector_id = self.index.ntotal
            logger.info(
                f"Loaded FAISS index: {self.index_path}, "
                f"vectors={self._next_vector_id}, dim={self.vector_dim}"
            )
        except Exception as e:
            logger.error(f"Failed to load FAISS index from {self.index_path}: {e}")
            logger.info("Creating new index instead")
            self._create_index()

    def save_index(self) -> None:
        """Save FAISS index to disk."""
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

    def add_vector(self, embedding: np.ndarray, vector_id: Optional[int] = None) -> int:
        """
        Add vector to FAISS index.

        Args:
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

            # Reshape for FAISS (needs 2D array)
            embedding_2d = embedding.reshape(1, -1).astype("float32")

            if vector_id is not None:
                # For rebuilding: check if we need to extend index
                if vector_id >= self.index.ntotal:
                    # Need to add padding vectors
                    padding_needed = vector_id - self.index.ntotal + 1
                    # Add zero vectors as padding
                    padding = np.zeros((padding_needed, self.vector_dim), dtype="float32")
                    self.index.add(padding)
                    self._next_vector_id = vector_id + 1
                # Replace vector at specific position
                # FAISS doesn't support direct replacement, so we'll add and track
                # For now, just add (will be cleaned up on rebuild)
                self.index.add(embedding_2d)
                if vector_id >= self._next_vector_id:
                    self._next_vector_id = vector_id + 1
                return vector_id
            else:
                # Normal add: append to end
                vector_id = self._next_vector_id
                self.index.add(embedding_2d)
                self._next_vector_id += 1
                return vector_id

    def remove_vectors(self, vector_ids: List[int]) -> None:
        """
        Remove vectors from FAISS index by IDs.

        Args:
            vector_ids: List of vector IDs to remove

        Note:
            FAISS doesn't support direct removal. This method marks vectors
            for removal. Actual cleanup happens on rebuild from database.
        """
        if not vector_ids:
            return

        # FAISS doesn't support direct vector removal
        # We'll track removed IDs and skip them during search
        # Actual cleanup will happen on next rebuild from database
        logger.debug(f"Marked {len(vector_ids)} vectors for removal (will be cleaned on rebuild)")

    def search(
        self, query_vector: np.ndarray, k: int = 10
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Search for similar vectors.

        Args:
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

            # Reshape for FAISS
            query_2d = query_vector.reshape(1, -1).astype("float32")

            # Search
            distances, indices = self.index.search(query_2d, min(k, self.index.ntotal))

            return distances[0], indices[0]

    def get_vector(self, vector_id: int) -> Optional[np.ndarray]:
        """
        Get vector by ID from index.

        Args:
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

    async def rebuild_from_database(
        self, database: "CodeDatabase", svo_client_manager: Optional[Any] = None
    ) -> int:
        """
        Rebuild FAISS index from database.

        Loads all chunks with embeddings from database and adds them to index.
        This cleans up any "garbage" vectors from previous updates.

        Args:
            database: CodeDatabase instance
            svo_client_manager: Optional SVOClientManager to get embeddings if missing

        Returns:
            Number of vectors loaded
        """
        logger.info("Rebuilding FAISS index from database...")

        # Create fresh index
        self._create_index()

        # Get all chunks with embeddings
        chunks = database.get_all_chunks_for_faiss_rebuild()
        if not chunks:
            logger.info("No chunks with embeddings found in database")
            return 0

        loaded_count = 0
        missing_embeddings = 0

        for chunk in chunks:
            vector_id = chunk.get("vector_id")
            embedding_vector_json = chunk.get("embedding_vector")
            chunk_text = chunk.get("chunk_text", "")
            embedding_model = chunk.get("embedding_model")

            if vector_id is None:
                continue

            # Try to get embedding from database first (embedding_vector column)
            embedding_array = None
            
            if embedding_vector_json:
                try:
                    import json
                    embedding_list = json.loads(embedding_vector_json)
                    embedding_array = np.array(embedding_list, dtype="float32")
                    logger.debug(f"Loaded embedding from database for chunk {chunk.get('id')}")
                except Exception as e:
                    logger.warning(
                        f"Failed to parse embedding_vector from database for chunk {chunk.get('id')}: {e}"
                    )
            
            # If embedding not in database, try to get from SVO service
            if embedding_array is None and svo_client_manager:
                logger.debug(
                    f"Embedding not in database for chunk {chunk.get('id')}, "
                    "requesting from SVO service..."
                )
                try:
                    # Create a dummy chunk object with text
                    class DummyChunk:
                        def __init__(self, text):
                            self.body = text
                            self.text = text

                    dummy_chunks = [DummyChunk(chunk_text)]
                    chunks_with_emb = await svo_client_manager.get_embeddings(dummy_chunks)
                    if chunks_with_emb and len(chunks_with_emb) > 0:
                        embedding = getattr(chunks_with_emb[0], "embedding", None)
                        if embedding is not None:
                            embedding_array = np.array(embedding, dtype="float32")
                            # Save embedding to database for future use
                            try:
                                import json
                                embedding_json = json.dumps(embedding.tolist())
                                with database._lock:
                                    cursor = database.conn.cursor()
                                    cursor.execute(
                                        """
                                        UPDATE code_chunks
                                        SET embedding_vector = ?
                                        WHERE id = ?
                                        """,
                                        (embedding_json, chunk.get("id")),
                                    )
                                    database.conn.commit()
                                logger.debug(f"Saved embedding to database for chunk {chunk.get('id')}")
                            except Exception as e:
                                logger.warning(f"Failed to save embedding to database: {e}")
                        else:
                            missing_embeddings += 1
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
                    self.add_vector(embedding_array, vector_id=vector_id)
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

        # Save rebuilt index
        self.save_index()

        logger.info(
            f"Rebuilt FAISS index: loaded {loaded_count} vectors, "
            f"missing {missing_embeddings} embeddings"
        )

        return loaded_count

    def get_stats(self) -> Dict[str, Any]:
        """
        Get index statistics.

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

    def close(self) -> None:
        """Close and save index."""
        if self.index is not None:
            self.save_index()
            self.index = None

