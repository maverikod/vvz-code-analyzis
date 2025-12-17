"""
Vectorization worker for processing chunks in background.

Processes code chunks that are not yet vectorized in a separate process.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import multiprocessing
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .svo_client_manager import SVOClientManager
    from .faiss_manager import FaissIndexManager
    from .database import CodeDatabase

logger = logging.getLogger(__name__)


class VectorizationWorker:
    """
    Worker for vectorizing code chunks in background process.
    
    Processes chunks that don't have vector_id yet, gets embeddings,
    adds them to FAISS index, and updates database.
    """

    def __init__(
        self,
        db_path: Path,
        project_id: str,
        svo_client_manager: Optional["SVOClientManager"] = None,
        faiss_manager: Optional["FaissIndexManager"] = None,
        batch_size: int = 10,
        retry_attempts: int = 3,
        retry_delay: float = 10.0,
        min_chunk_length: int = 30,
    ):
        """
        Initialize vectorization worker.

        Args:
            db_path: Path to database file
            project_id: Project ID to process
            svo_client_manager: SVO client manager for embeddings
            faiss_manager: FAISS index manager
            batch_size: Number of chunks to process in one batch
            retry_attempts: Number of retry attempts for vectorization (default: 3)
            retry_delay: Delay in seconds between retry attempts (default: 10.0)
            min_chunk_length: Minimum text length for chunking (default: 30)
        """
        self.db_path = db_path
        self.project_id = project_id
        self.svo_client_manager = svo_client_manager
        self.faiss_manager = faiss_manager
        self.batch_size = batch_size
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.min_chunk_length = min_chunk_length
        self._stop_event = multiprocessing.Event()

    async def process_chunks(self, poll_interval: int = 30) -> Dict[str, Any]:
        """
        Process non-vectorized chunks in continuous loop with polling interval.
        
        Runs indefinitely, checking for chunks to vectorize at specified intervals.
        Also requests chunking for files that need chunking.
        
        Args:
            poll_interval: Interval in seconds between polling cycles (default: 30)
        
        Returns:
            Dictionary with processing statistics (only when stopped)
        """
        import asyncio
        from .database import CodeDatabase
        
        if not self.svo_client_manager:
            logger.warning("SVO client manager not available, skipping vectorization")
            return {"processed": 0, "errors": 0}
        
        if not self.faiss_manager:
            logger.warning("FAISS manager not available, skipping vectorization")
            return {"processed": 0, "errors": 0}

        database = CodeDatabase(self.db_path)
        total_processed = 0
        total_errors = 0
        cycle_count = 0

        try:
            logger.info(
                f"Starting continuous vectorization worker for project {self.project_id}, "
                f"poll interval: {poll_interval}s"
            )
            
            while not self._stop_event.is_set():
                cycle_count += 1
                logger.debug(f"Vectorization cycle #{cycle_count} starting")
                
                # Step 1: Request chunking for files that need it
                try:
                    files_to_chunk = database.get_files_needing_chunking(
                        project_id=self.project_id,
                        limit=5,  # Process 5 files per cycle
                    )
                    
                    if files_to_chunk:
                        logger.info(
                            f"Found {len(files_to_chunk)} files needing chunking, "
                            "requesting chunking..."
                        )
                        chunked_count = await self._request_chunking_for_files(
                            database, files_to_chunk
                        )
                        logger.info(f"Requested chunking for {chunked_count} files")
                except Exception as e:
                    logger.error(f"Error requesting chunking: {e}", exc_info=True)
                
                # Step 2: Process chunks that have embeddings but no vector_id
                # This handles edge cases:
                # - Old chunks created before chunker always returned embeddings
                # - Chunks where FAISS add failed but embedding is in DB
                batch_processed = 0
                batch_errors = 0
                
                while not self._stop_event.is_set():
                    # Get chunks with embeddings but without vector_id
                    # These should be rare - chunker always returns embeddings and adds to FAISS
                    chunks = await database.get_non_vectorized_chunks(
                        project_id=self.project_id,
                        limit=self.batch_size,
                    )

                    if not chunks:
                        logger.debug("No chunks needing vector_id assignment in this cycle")
                        break

                    logger.info(
                        f"Processing batch of {len(chunks)} chunks that need vector_id "
                        "(should be rare - chunker always provides embeddings)"
                    )

                    for chunk in chunks:
                        if self._stop_event.is_set():
                            break

                        try:
                            chunk_id = chunk["id"]
                            chunk_text = chunk.get("chunk_text", "")
                            
                            # Check if chunk has embedding_vector in database
                            with database._lock:
                                cursor = database.conn.cursor()
                                cursor.execute(
                                    "SELECT embedding_vector, embedding_model FROM code_chunks WHERE id = ?",
                                    (chunk_id,)
                                )
                                row = cursor.fetchone()
                            
                            embedding_array = None
                            embedding_model = None
                            
                            if row and row[0]:  # embedding_vector exists
                                # Load embedding from database
                                try:
                                    import json
                                    embedding_list = json.loads(row[0])
                                    embedding_array = np.array(embedding_list, dtype="float32")
                                    embedding_model = row[1]
                                    logger.debug(f"Loaded embedding from DB for chunk {chunk_id}")
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to parse embedding from DB for chunk {chunk_id}: {e}"
                                    )
                            
                            # If no embedding in DB, try to get from chunker (shouldn't happen)
                            if embedding_array is None and self.svo_client_manager:
                                logger.warning(
                                    f"Chunk {chunk_id} has no embedding in DB, "
                                    "requesting from chunker (unexpected!)"
                                )
                                class DummyChunk:
                                    def __init__(self, text):
                                        self.body = text
                                        self.text = text

                                dummy_chunk = DummyChunk(chunk_text)
                                chunks_with_emb = await self.svo_client_manager.get_embeddings([dummy_chunk])
                                
                                if chunks_with_emb and len(chunks_with_emb) > 0:
                                    embedding = getattr(chunks_with_emb[0], "embedding", None)
                                    embedding_model = getattr(chunks_with_emb[0], "embedding_model", None)
                                    
                                    if embedding:
                                        embedding_array = np.array(embedding, dtype="float32")
                                        # Save to DB
                                        import json
                                        embedding_json = json.dumps(
                                            embedding.tolist() if hasattr(embedding, 'tolist') else embedding
                                        )
                                        with database._lock:
                                            cursor = database.conn.cursor()
                                            cursor.execute(
                                                "UPDATE code_chunks SET embedding_vector = ?, embedding_model = ? WHERE id = ?",
                                                (embedding_json, embedding_model, chunk_id)
                                            )
                                            database.conn.commit()
                            
                            if embedding_array is None:
                                logger.warning(
                                    f"Cannot get embedding for chunk {chunk_id}, skipping"
                                )
                                batch_errors += 1
                                continue

                            # Add to FAISS index
                            vector_id = self.faiss_manager.add_vector(embedding_array)

                            # Update database with vector_id
                            await database.update_chunk_vector_id(
                                chunk_id, vector_id, embedding_model
                            )

                            batch_processed += 1
                            logger.debug(
                                f"Assigned vector_id {vector_id} to chunk {chunk_id}"
                            )

                        except Exception as e:
                            logger.error(
                                f"Error processing chunk {chunk.get('id')}: {e}, "
                                "will retry in next cycle",
                                exc_info=True,
                            )
                            batch_errors += 1
                            continue

                    # Save FAISS index after batch
                    try:
                        self.faiss_manager.save_index()
                    except Exception as e:
                        logger.error(f"Error saving FAISS index: {e}")
                
                total_processed += batch_processed
                total_errors += batch_errors
                
                if batch_processed > 0 or batch_errors > 0:
                    logger.info(
                        f"Cycle #{cycle_count} complete: {batch_processed} processed, "
                        f"{batch_errors} errors (total: {total_processed} processed, "
                        f"{total_errors} errors)"
                    )
                
                # Wait for next cycle (with early exit check)
                if not self._stop_event.is_set():
                    logger.debug(f"Waiting {poll_interval}s before next cycle...")
                    for _ in range(poll_interval):
                        if self._stop_event.is_set():
                            break
                        await asyncio.sleep(1)

        finally:
            database.close()

        logger.info(
            f"Vectorization worker stopped: {total_processed} total processed, "
            f"{total_errors} total errors over {cycle_count} cycles"
        )
        return {"processed": total_processed, "errors": total_errors, "cycles": cycle_count}
    
    async def _request_chunking_for_files(
        self, database: "CodeDatabase", files: List[Dict[str, Any]]
    ) -> int:
        """
        Request chunking for files that need it.
        
        Args:
            database: Database instance
            files: List of file records that need chunking
            
        Returns:
            Number of files successfully chunked
        """
        from .docstring_chunker import DocstringChunker
        
        chunker = DocstringChunker(
            database=database,
            svo_client_manager=self.svo_client_manager,
            faiss_manager=self.faiss_manager,
            min_chunk_length=self.min_chunk_length,
        )
        
        chunked_count = 0
        
        for file_record in files:
            if self._stop_event.is_set():
                break
                
            try:
                file_id = file_record["id"]
                file_path = file_record["path"]
                project_id = file_record["project_id"]
                
                logger.info(f"Requesting chunking for file {file_path} (id={file_id})")
                
                # Read file content
                from pathlib import Path
                try:
                    file_content = Path(file_path).read_text(encoding="utf-8")
                except Exception as e:
                    logger.warning(f"Failed to read file {file_path}: {e}")
                    continue
                
                # Parse AST
                import ast
                try:
                    tree = ast.parse(file_content, filename=file_path)
                except Exception as e:
                    logger.warning(f"Failed to parse AST for {file_path}: {e}")
                    continue
                
                # Process file with chunker
                await chunker.process_file(
                    file_id=file_id,
                    project_id=project_id,
                    file_path=file_path,
                    tree=tree,
                    file_content=file_content,
                )
                
                chunked_count += 1
                logger.info(f"Successfully chunked file {file_path}")
                
            except Exception as e:
                logger.error(
                    f"Error chunking file {file_record.get('path')}: {e}",
                    exc_info=True,
                )
                continue
        
        return chunked_count

    def stop(self) -> None:
        """Stop the worker."""
        self._stop_event.set()


def run_vectorization_worker(
    db_path: str,
    project_id: str,
    faiss_index_path: str,
    vector_dim: int,
    svo_config: Optional[Dict[str, Any]] = None,
    batch_size: int = 10,
    poll_interval: int = 30,
    retry_attempts: int = 3,
    retry_delay: float = 10.0,
) -> Dict[str, Any]:
    """
    Run vectorization worker in separate process with continuous polling.
    
    This function is designed to be called from multiprocessing.Process.
    It runs indefinitely, checking for chunks to vectorize at specified intervals.
    
    Args:
        db_path: Path to database file
        project_id: Project ID to process
        faiss_index_path: Path to FAISS index file
        vector_dim: Vector dimension
        svo_config: SVO client configuration (optional)
        batch_size: Batch size for processing
        poll_interval: Interval in seconds between polling cycles (default: 30)
        
    Returns:
        Dictionary with processing statistics (only when stopped)
    """
    import asyncio
    from .svo_client_manager import SVOClientManager
    from .config import ServerConfig
    from .faiss_manager import FaissIndexManager

    # Use logger from adapter (configured by adapter)
    # Note: In worker process, logging is configured by adapter in main process

    logger.info(
        f"Starting continuous vectorization worker for project {project_id}, "
        f"poll interval: {poll_interval}s"
    )

    # Initialize SVO client manager if config provided
    svo_client_manager = None
    if svo_config:
        try:
            # svo_config should be a ServerConfig dict
            server_config_obj = ServerConfig(**svo_config)
            svo_client_manager = SVOClientManager(server_config_obj)
            asyncio.run(svo_client_manager.initialize())
        except Exception as e:
            logger.error(f"Failed to initialize SVO client manager: {e}")
            return {"processed": 0, "errors": 1}

    # Initialize FAISS manager
    try:
        faiss_manager = FaissIndexManager(
            index_path=faiss_index_path,
            vector_dim=vector_dim,
        )
    except Exception as e:
        logger.error(f"Failed to initialize FAISS manager: {e}")
        if svo_client_manager:
            asyncio.run(svo_client_manager.close())
        return {"processed": 0, "errors": 1}

    # Get retry config and min_chunk_length from svo_config if available
    min_chunk_length = 30  # default
    if svo_config:
        from .config import ServerConfig
        try:
            server_config_obj = ServerConfig(**svo_config)
            if hasattr(server_config_obj, 'vectorization_retry_attempts'):
                retry_attempts = server_config_obj.vectorization_retry_attempts
            if hasattr(server_config_obj, 'vectorization_retry_delay'):
                retry_delay = server_config_obj.vectorization_retry_delay
            if hasattr(server_config_obj, 'min_chunk_length'):
                min_chunk_length = server_config_obj.min_chunk_length
        except Exception:
            pass  # Use defaults

    # Create and run worker
    worker = VectorizationWorker(
        db_path=Path(db_path),
        project_id=project_id,
        svo_client_manager=svo_client_manager,
        faiss_manager=faiss_manager,
        batch_size=batch_size,
        retry_attempts=retry_attempts,
        retry_delay=retry_delay,
        min_chunk_length=min_chunk_length,
    )

    try:
        result = asyncio.run(worker.process_chunks(poll_interval=poll_interval))
        return result
    except KeyboardInterrupt:
        logger.info("Vectorization worker interrupted by signal")
        worker.stop()
        return {"processed": 0, "errors": 0, "interrupted": True}
    except Exception as e:
        logger.error(f"Error in vectorization worker: {e}", exc_info=True)
        return {"processed": 0, "errors": 1}
    finally:
        if svo_client_manager:
            asyncio.run(svo_client_manager.close())
