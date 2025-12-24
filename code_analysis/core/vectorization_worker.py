"""
Vectorization worker for processing chunks in background.

Processes code chunks that are not yet vectorized in a separate process.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Logging:
    All DEBUG logs (including timing and docstring previews) are controlled by
    the log_level setting in config.json. Set "log_level": "DEBUG" to see:
    - Detailed timing for each operation
    - Docstring text previews
    - Full call chain information
    - FAISS vector addition details
"""

import logging
import multiprocessing
import time
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
        watch_dirs: Optional[List[Path]] = None,
        config_path: Optional[Path] = None,
        dynamic_watch_file: Optional[Path] = None,
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
        # watch_dirs is stored as list of Path; each entry may have attribute is_dynamic
        self.watch_dirs: List[Path] = []
        for p in watch_dirs or []:
            self.watch_dirs.append(Path(p))
        self.config_path = config_path
        self.dynamic_watch_file = dynamic_watch_file
        self._config_mtime: Optional[float] = None
        self._stop_event = multiprocessing.Event()

    def _refresh_config(self) -> None:
        """Reload worker watch_dirs from config file if it changed."""
        try:
            # load dynamic watch list
            dynamic_paths: List[Path] = []
            if self.dynamic_watch_file and self.dynamic_watch_file.exists():
                try:
                    import json
                    with open(self.dynamic_watch_file, "r", encoding="utf-8") as df:
                        dyn = json.load(df)
                        for p in dyn.get("watch_dirs", []):
                            if p:
                                path_obj = Path(p)
                                setattr(path_obj, "is_dynamic", True)
                                dynamic_paths.append(path_obj)
                except Exception as e:
                    logger.error(f"Failed to load dynamic watch dirs: {e}", exc_info=True)

            if not self.config_path:
                # Only dynamic paths
                combined = dynamic_paths
                if set(map(str, combined)) != set(map(str, self.watch_dirs)):
                    self.watch_dirs = combined
                return

            if not self.config_path.exists():
                logger.debug("Config path does not exist, skipping refresh")
                return
            mtime = self.config_path.stat().st_mtime
            if self._config_mtime is not None and mtime == self._config_mtime:
                return  # no changes
            import json

            with open(self.config_path, "r", encoding="utf-8") as f:
                raw_cfg = json.load(f)
            ca_cfg = raw_cfg.get("code_analysis") or raw_cfg
            worker_cfg = ca_cfg.get("worker", {})
            new_watch = worker_cfg.get("watch_dirs", [])
            new_watch_paths = [Path(p) for p in new_watch if p]

            # Remove non-dynamic paths that are no longer in config; keep dynamic ones
            current_dynamic = {str(p) for p in self.watch_dirs if getattr(p, "is_dynamic", False)}
            current_config = {str(p) for p in self.watch_dirs if not getattr(p, "is_dynamic", False)}
            new_config_set = {str(p) for p in new_watch_paths}

            # Updated list: new config paths (non-dynamic) + existing dynamic
            updated_paths: List[Path] = []
            for p in new_watch_paths:
                updated_paths.append(p)
            # keep dynamic from file
            updated_paths.extend(dynamic_paths)

            if set(map(str, updated_paths)) != set(map(str, self.watch_dirs)):
                logger.info(
                    "Worker watch_dirs updated from config: "
                    f"{[str(p) for p in self.watch_dirs]} -> {[str(p) for p in updated_paths]}"
                )
                self.watch_dirs = updated_paths
            self._config_mtime = mtime
        except Exception as e:
            logger.error(f"Failed to refresh config: {e}", exc_info=True)

    async def _enqueue_watch_dirs(self, database: "CodeDatabase") -> int:
        """
        Scan watch_dirs and ensure files are registered for chunking.
        Returns number of files enqueued (new or marked needing chunking).
        """
        enqueued = 0
        for root in self.watch_dirs:
            try:
                root_path = Path(root)
                if not root_path.exists():
                    continue
                for file_path in root_path.rglob("*.py"):
                    file_stat = file_path.stat()
                    file_mtime = file_stat.st_mtime
                    file_rec = database.get_file_by_path(str(file_path), self.project_id)
                    if not file_rec:
                        # Register file and mark as needing chunking
                        database.add_file(
                            str(file_path),
                            lines=len(file_path.read_text(encoding="utf-8").splitlines()),
                            last_modified=file_mtime,
                            has_docstring=False,
                            project_id=self.project_id,
                        )
                        database.mark_file_needs_chunking(str(file_path), self.project_id)
                        enqueued += 1
                    else:
                        db_mtime = file_rec.get("last_modified")
                        if db_mtime is None or db_mtime != file_mtime:
                            database.mark_file_needs_chunking(str(file_path), self.project_id)
                            enqueued += 1
            except Exception as e:
                logger.error(f"Error scanning watch_dir {root}: {e}", exc_info=True)
        return enqueued

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
        self._log_missing_docstring_files(database)

        try:
            logger.info(
                f"Starting continuous vectorization worker for project {self.project_id}, "
                f"poll interval: {poll_interval}s"
            )
            
            while not self._stop_event.is_set():
                cycle_count += 1
                cycle_start_time = time.time()
                logger.debug(f"[CYCLE #{cycle_count}] Starting vectorization cycle")
                cycle_activity = False

                # Refresh config to sync watch_dirs without restart
                try:
                    self._refresh_config()
                except Exception as e:
                    logger.error(f"Error refreshing worker config: {e}", exc_info=True)
                
                # Step 0: enqueue watch_dirs (filesystem scan)
                if self.watch_dirs:
                    try:
                        files_enqueued = await self._enqueue_watch_dirs(database)
                        if files_enqueued > 0:
                            cycle_activity = True
                            logger.info(f"Enqueued {files_enqueued} files from watch_dirs")
                    except Exception as e:
                        logger.error(f"Error enqueuing watch_dirs: {e}", exc_info=True)

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
                # NOTE: Automatic processing of empty chunks (chunks without embeddings) 
                # has been disabled. Use dedicated command to process them manually.
                # This step only processes chunks that have embeddings in DB but no vector_id.
                batch_processed = 0
                batch_errors = 0
                
                while not self._stop_event.is_set():
                    # Get chunks with embeddings in DB but without vector_id
                    # These are chunks where embedding was saved but FAISS add failed or wasn't done
                    step_start = time.time()
                    logger.debug(f"[TIMING] Step 2: Starting to get non-vectorized chunks from DB")
                    chunks = await database.get_non_vectorized_chunks(
                        project_id=self.project_id,
                        limit=self.batch_size,
                    )
                    step_duration = time.time() - step_start
                    logger.debug(f"[TIMING] Step 2: Retrieved {len(chunks)} chunks from DB in {step_duration:.3f}s")

                    if not chunks:
                        logger.debug("No chunks needing vector_id assignment in this cycle")
                        break

                    logger.info(
                        f"Processing batch of {len(chunks)} chunks that have embeddings but need vector_id"
                    )

                    for chunk in chunks:
                        if self._stop_event.is_set():
                            break

                        try:
                            chunk_start_time = time.time()
                            chunk_id = chunk["id"]
                            chunk_text = chunk.get("chunk_text", "")
                            
                            # Log chunk text (docstring) for debugging
                            chunk_text_preview = chunk_text[:200] + "..." if len(chunk_text) > 200 else chunk_text
                            logger.debug(
                                f"[CHUNK {chunk_id}] Processing chunk:\n"
                                f"  Text preview: {chunk_text_preview!r}\n"
                                f"  Text length: {len(chunk_text)} chars"
                            )
                            
                            # Log AST binding information for this chunk
                            ast_info = []
                            if chunk.get("class_id"):
                                ast_info.append(f"class_id={chunk['class_id']}")
                            if chunk.get("function_id"):
                                ast_info.append(f"function_id={chunk['function_id']}")
                            if chunk.get("method_id"):
                                ast_info.append(f"method_id={chunk['method_id']}")
                            if chunk.get("line"):
                                ast_info.append(f"line={chunk['line']}")
                            if chunk.get("ast_node_type"):
                                ast_info.append(f"node={chunk['ast_node_type']}")
                            ast_binding = ", ".join(ast_info) if ast_info else "no AST binding"
                            logger.debug(f"[CHUNK {chunk_id}] AST binding: {ast_binding}")
                            
                            # Check if chunk has embedding_vector in database
                            db_check_start = time.time()
                            with database._lock:
                                cursor = database.conn.cursor()
                                cursor.execute(
                                    "SELECT embedding_vector, embedding_model FROM code_chunks WHERE id = ?",
                                    (chunk_id,)
                                )
                                row = cursor.fetchone()
                            db_check_duration = time.time() - db_check_start
                            logger.debug(f"[TIMING] [CHUNK {chunk_id}] DB check took {db_check_duration:.3f}s")
                            
                            embedding_array = None
                            embedding_model = None
                            
                            if row and row[0]:  # embedding_vector exists
                                # Load embedding from database
                                load_start = time.time()
                                try:
                                    import json
                                    embedding_list = json.loads(row[0])
                                    embedding_array = np.array(embedding_list, dtype="float32")
                                    embedding_model = row[1]
                                    load_duration = time.time() - load_start
                                    logger.debug(
                                        f"[TIMING] [CHUNK {chunk_id}] Loaded embedding from DB in {load_duration:.3f}s "
                                        f"(dim={len(embedding_array)}, model={embedding_model}, {ast_binding})"
                                    )
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to parse embedding from DB for chunk {chunk_id} "
                                        f"({ast_binding}): {e}"
                                    )
                            
                            # If no embedding in DB, try to get it from SVO service
                            if embedding_array is None and self.svo_client_manager:
                                logger.info(
                                    f"Chunk {chunk_id} has no embedding in DB ({ast_binding}), "
                                    "requesting from SVO service..."
                                )
                                try:
                                    if not chunk_text:
                                        logger.warning(
                                            f"Chunk {chunk_id} has no text, skipping"
                                        )
                                        continue
                                    
                                    logger.debug(
                                        f"[CHUNK {chunk_id}] Requesting embedding from SVO service for text:\n"
                                        f"  {chunk_text_preview!r}"
                                    )
                                    
                                    # Create dummy chunk object for embedding API
                                    class DummyChunk:
                                        def __init__(self, text):
                                            self.body = text
                                            self.text = text

                                    dummy_chunk = DummyChunk(chunk_text)
                                    embedding_request_start = time.time()
                                    # Pass type parameter to chunker - it should return embeddings
                                    chunk_type = chunk.get("chunk_type", "DocBlock")
                                    chunks_with_emb = await self.svo_client_manager.get_embeddings(
                                        [dummy_chunk], 
                                        type=chunk_type
                                    )
                                    embedding_request_duration = time.time() - embedding_request_start
                                    logger.debug(
                                        f"[TIMING] [CHUNK {chunk_id}] SVO embedding request took {embedding_request_duration:.3f}s"
                                    )
                                    
                                    if chunks_with_emb and len(chunks_with_emb) > 0:
                                        embedding = getattr(chunks_with_emb[0], "embedding", None)
                                        embedding_model = getattr(chunks_with_emb[0], "embedding_model", None)
                                        
                                        if embedding:
                                            embedding_array = np.array(embedding, dtype="float32")
                                            logger.debug(
                                                f"[CHUNK {chunk_id}] Received embedding: dim={len(embedding_array)}, "
                                                f"model={embedding_model}"
                                            )
                                            
                                            # Save to DB for future use
                                            save_start = time.time()
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
                                            save_duration = time.time() - save_start
                                            logger.debug(
                                                f"[TIMING] [CHUNK {chunk_id}] Saved embedding to DB in {save_duration:.3f}s"
                                            )
                                            logger.info(
                                                f"✅ Obtained and saved embedding for chunk {chunk_id} "
                                                f"({ast_binding})"
                                            )
                                        else:
                                            logger.warning(
                                                f"Chunk {chunk_id} embedding request returned no embedding, "
                                                "skipping (use dedicated command to process empty chunks)"
                                            )
                                            continue
                                    else:
                                        logger.warning(
                                            f"Chunk {chunk_id} embedding request returned empty result, "
                                            "skipping (use dedicated command to process empty chunks)"
                                        )
                                        continue
                                except Exception as e:
                                    error_type = type(e).__name__
                                    error_msg = str(e)
                                    
                                    # Check if it's a Model RPC server error (infrastructure issue)
                                    is_model_rpc_error = (
                                        "Model RPC server" in error_msg or
                                        "failed after 3 attempts" in error_msg or
                                        (hasattr(e, "code") and getattr(e, "code") == -32603)
                                    )
                                    
                                    if is_model_rpc_error:
                                        # Model RPC server is down - log as warning (infrastructure issue, not code issue)
                                        logger.warning(
                                            f"Model RPC server unavailable for chunk {chunk_id} ({ast_binding}): {error_msg}. "
                                            f"Chunk will be retried in next cycle. Check Model RPC server status."
                                        )
                                    else:
                                        # Other errors - log as error
                                        logger.error(
                                            f"Failed to get embedding for chunk {chunk_id} ({ast_binding}): {error_type}: {error_msg}",
                                            exc_info=True
                                        )
                                    batch_errors += 1
                                    continue
                            
                            # Skip chunks without embeddings - they should be processed via dedicated command
                            if embedding_array is None:
                                logger.debug(
                                    f"Chunk {chunk_id} has no embedding ({ast_binding}), skipping "
                                    "(use dedicated command to process empty chunks)"
                                )
                                continue

                            # Add to FAISS index
                            logger.debug(
                                f"[CHUNK {chunk_id}] Adding embedding to FAISS index "
                                f"(dim={len(embedding_array)}, model={embedding_model})"
                            )
                            faiss_add_start = time.time()
                            vector_id = self.faiss_manager.add_vector(embedding_array)
                            faiss_add_duration = time.time() - faiss_add_start
                            logger.debug(
                                f"[TIMING] [CHUNK {chunk_id}] FAISS add_vector took {faiss_add_duration:.3f}s, "
                                f"assigned vector_id={vector_id}"
                            )

                            # Update database with vector_id (AST bindings are preserved)
                            db_update_start = time.time()
                            await database.update_chunk_vector_id(
                                chunk_id, vector_id, embedding_model
                            )
                            db_update_duration = time.time() - db_update_start
                            logger.debug(
                                f"[TIMING] [CHUNK {chunk_id}] Database update_chunk_vector_id took {db_update_duration:.3f}s"
                            )

                            chunk_total_duration = time.time() - chunk_start_time
                            batch_processed += 1
                            logger.info(
                                f"✅ Vectorized chunk {chunk_id} → vector_id={vector_id} "
                                f"({ast_binding}) in {chunk_total_duration:.3f}s"
                            )
                            logger.debug(
                                f"[TIMING] [CHUNK {chunk_id}] Total processing time: {chunk_total_duration:.3f}s"
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
                    if batch_processed > 0:
                        faiss_save_start = time.time()
                        try:
                            logger.debug(f"[TIMING] Saving FAISS index after processing {batch_processed} chunks")
                            self.faiss_manager.save_index()
                            faiss_save_duration = time.time() - faiss_save_start
                            logger.debug(f"[TIMING] FAISS index save took {faiss_save_duration:.3f}s")
                        except Exception as e:
                            logger.error(f"Error saving FAISS index: {e}")
                
                total_processed += batch_processed
                total_errors += batch_errors
                
                cycle_duration = time.time() - cycle_start_time
                if batch_processed > 0 or batch_errors > 0:
                    logger.info(
                        f"[CYCLE #{cycle_count}] Complete in {cycle_duration:.3f}s: "
                        f"{batch_processed} processed, {batch_errors} errors "
                        f"(total: {total_processed} processed, {total_errors} errors)"
                    )
                    logger.debug(
                        f"[TIMING] [CYCLE #{cycle_count}] Total cycle time: {cycle_duration:.3f}s"
                    )
                    if batch_processed > 0:
                        cycle_activity = True
                else:
                    logger.debug(
                        f"[CYCLE #{cycle_count}] No chunks processed in {cycle_duration:.3f}s"
                    )

                # Step 3: Fallback — try to chunk files that have no docstring chunks at all
                if not cycle_activity:
                    try:
                        missing_chunked = await self._chunk_missing_docstring_files(
                            database, limit=3
                        )
                        if missing_chunked > 0:
                            cycle_activity = True
                            logger.info(
                                f"Requested chunking for {missing_chunked} files without docstring chunks (fallback)"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to process files without docstring chunks: {e}",
                            exc_info=True,
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

    async def _chunk_missing_docstring_files(
        self, database: "CodeDatabase", limit: int = 3
    ) -> int:
        """
        Chunk files that currently have no docstring chunks in DB (fallback pass).
        """
        from .docstring_chunker import DocstringChunker
        import ast
        from pathlib import Path

        assert database.conn is not None
        cursor = database.conn.cursor()
        cursor.execute(
            """
            SELECT f.id, f.path, f.project_id
            FROM files f
            LEFT JOIN code_chunks c
              ON f.id = c.file_id AND c.source_type LIKE '%docstring%'
            WHERE f.project_id = ?
            GROUP BY f.id, f.path, f.project_id
            HAVING COUNT(c.id) = 0
            LIMIT ?
            """,
            (self.project_id, limit),
        )
        rows = cursor.fetchall()
        if not rows:
            return 0

        chunker = DocstringChunker(
            database=database,
            svo_client_manager=self.svo_client_manager,
            faiss_manager=self.faiss_manager,
            min_chunk_length=self.min_chunk_length,
        )

        processed = 0
        for row in rows:
            if self._stop_event.is_set():
                break
            file_id = row[0]
            file_path = row[1]
            project_id = row[2]

            try:
                content = Path(file_path).read_text(encoding="utf-8")
                tree = ast.parse(content, filename=file_path)
                await chunker.process_file(
                    file_id=file_id,
                    project_id=project_id,
                    file_path=file_path,
                    tree=tree,
                    file_content=content,
                )
                processed += 1
                logger.info(f"Fallback chunked missing-docstring file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed fallback chunking for {file_path}: {e}", exc_info=True)

        return processed

    def _log_missing_docstring_files(self, database: "CodeDatabase", sample: int = 10) -> None:
        """
        Log files that have no docstring chunks in the database.
        """
        try:
            assert database.conn is not None
            cursor = database.conn.cursor()
            cursor.execute(
                """
                SELECT f.path
                FROM files f
                LEFT JOIN code_chunks c
                  ON f.id = c.file_id AND c.source_type LIKE '%docstring%'
                WHERE f.project_id = ?
                GROUP BY f.id, f.path
                HAVING COUNT(c.id) = 0
                LIMIT ?
                """,
                (self.project_id, sample),
            )
            rows = cursor.fetchall()
            if rows:
                paths = [row[0] for row in rows]
                logger.warning(
                    f"⚠️  Files with no docstring chunks in DB (sample {len(paths)}/{sample}): {paths}"
                )
        except Exception as e:
            logger.warning(f"Failed to log missing docstring files: {e}", exc_info=True)

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
