"""
SQLite database driver proxy.

This proxy driver sends database operations to a separate process
via queuemgr, ensuring thread/process safety.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from queuemgr.async_simple_api import AsyncQueueSystem
from queuemgr.exceptions import ProcessControlError, TimeoutError as QueueTimeoutError

from .base import BaseDatabaseDriver
from .sqlite_worker_job import SQLiteDatabaseJob

logger = logging.getLogger(__name__)


class SQLiteDriverProxy(BaseDatabaseDriver):
    """
    Proxy driver that sends SQLite operations to a separate process via queuemgr.

    This driver implements the BaseDatabaseDriver interface but delegates
    all operations to SQLiteDatabaseJob running in a separate process.
    """

    @property
    def is_thread_safe(self) -> bool:
        """Proxy driver is thread-safe as operations are serialized through queue."""
        return True

    def __init__(self) -> None:
        """Initialize SQLite proxy driver."""
        self.conn: Optional[Any] = None  # Not used, kept for compatibility
        self.db_path: Optional[Path] = None
        self._queue_system: Optional[AsyncQueueSystem] = None
        self._queue_initialized: bool = False
        self.command_timeout: float = 30.0
        self.registry_path: str = "data/queuemgr_registry.jsonl"

    def connect(self, config: Dict[str, Any]) -> None:
        """
        Establish connection to queue system.

        Args:
            config: Configuration dict with:
                - path: Path to SQLite database file
                - worker_config (optional): Configuration for queue system:
                    - registry_path: Path to queuemgr registry file
                    - command_timeout: Timeout for commands in seconds
        """
        if "path" not in config:
            raise ValueError("SQLite proxy driver requires 'path' in config")

        self.db_path = Path(config["path"]).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Get worker config
        worker_config = config.get("worker_config", {})
        self.registry_path = worker_config.get("registry_path", self.registry_path)
        self.command_timeout = worker_config.get("command_timeout", self.command_timeout)

        # Initialize queue system synchronously
        # We need to ensure queue is ready before returning
        try:
            loop = asyncio.get_running_loop()
            # We're in async context - this is problematic
            # We'll need to initialize in a separate thread
            import threading
            import queue as thread_queue
            
            init_queue = thread_queue.Queue()
            exception_queue = thread_queue.Queue()
            
            def init_in_thread():
                try:
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        new_loop.run_until_complete(self._initialize_queue_async())
                        init_queue.put(True)
                    finally:
                        new_loop.close()
                except Exception as e:
                    exception_queue.put(e)
            
            thread = threading.Thread(target=init_in_thread)
            thread.start()
            thread.join(timeout=10.0)  # 10 second timeout
            
            if not exception_queue.empty():
                raise exception_queue.get()
            if init_queue.empty():
                raise RuntimeError("Queue initialization timed out")
        except RuntimeError:
            # No running loop, create new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._initialize_queue_async())
            finally:
                loop.close()

        logger.info(f"SQLite proxy driver connected to database: {self.db_path}")

    async def _initialize_queue_async(self) -> None:
        """Initialize queue system asynchronously."""
        if self._queue_initialized:
            return

        try:
            self._queue_system = AsyncQueueSystem(
                registry_path=self.registry_path,
                shutdown_timeout=30.0,
                command_timeout=self.command_timeout,
            )
            await self._queue_system.start()
            self._queue_initialized = True
            logger.info("Queue system initialized for SQLite proxy driver")
            
            # Register queue system in WorkerManager
            try:
                from ..worker_manager import get_worker_manager
                worker_manager = get_worker_manager()
                worker_manager.register_worker(
                    "sqlite_queue",
                    {
                        "queue_system": self._queue_system,
                        "name": f"sqlite_queue_{id(self._queue_system)}",
                        "db_path": str(self.db_path),
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to register SQLite queue in WorkerManager: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize queue system: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize queue system: {e}") from e

    def _ensure_queue_initialized(self) -> None:
        """Ensure queue system is initialized."""
        if not self._queue_initialized or self._queue_system is None:
            # Try to initialize synchronously
            try:
                loop = asyncio.get_running_loop()
                # If we're in async context, we need to wait
                # This is a limitation - we should be called from async context
                raise RuntimeError(
                    "Queue system not initialized. "
                    "Ensure connect() was called and completed."
                )
            except RuntimeError:
                # No running loop, create new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self._initialize_queue_async())
                finally:
                    loop.close()

    async def _execute_operation(
        self, operation: str, **kwargs: Any
    ) -> Any:
        """
        Execute database operation via queue.

        Args:
            operation: Operation type (execute, fetchone, fetchall, commit, rollback, lastrowid, get_table_info)
            **kwargs: Operation-specific parameters

        Returns:
            Operation result

        Raises:
            RuntimeError: If operation fails
            TimeoutError: If operation times out
        """
        self._ensure_queue_initialized()

        if not self._queue_system:
            raise RuntimeError("Queue system not initialized")

        # Generate unique job ID
        job_id = f"sqlite_{operation}_{uuid.uuid4().hex[:8]}"

        # Prepare job params
        params: Dict[str, Any] = {
            "operation": operation,
            "db_path": str(self.db_path),
            **kwargs
        }

        try:
            # Add job to queue
            await self._queue_system.add_job(SQLiteDatabaseJob, job_id, params)

            # Start job
            await self._queue_system.start_job(job_id)

            # Wait for completion
            max_wait = self.command_timeout
            start_time = time.time()
            poll_interval = 0.1  # Poll every 100ms

            while time.time() - start_time < max_wait:
                status = await self._queue_system.get_job_status(job_id)

                job_status = status.get("status", "unknown")
                
                if job_status == "completed":
                    result = status.get("result", {})
                    if isinstance(result, dict) and result.get("success"):
                        return result.get("result")
                    else:
                        error = result.get("error", "Unknown error") if isinstance(result, dict) else "Unknown error"
                        raise RuntimeError(f"Database operation failed: {error}")
                elif job_status == "error":
                    error_msg = status.get("error", "Unknown error")
                    raise RuntimeError(f"Job failed: {error_msg}")
                elif job_status in ("pending", "running"):
                    # Job is still running, wait a bit
                    await asyncio.sleep(poll_interval)
                    continue
                else:
                    # Unknown status
                    await asyncio.sleep(poll_interval)
                    continue

            # Timeout
            try:
                await self._queue_system.stop_job(job_id)
            except Exception:
                pass  # Ignore errors when stopping
            raise TimeoutError(
                f"Database operation '{operation}' timed out after {max_wait}s"
            )

        except ProcessControlError as e:
            raise RuntimeError(f"Queue system error: {e}") from e
        except Exception as e:
            # Clean up job on error
            try:
                await self._queue_system.delete_job(job_id, force=True)
            except Exception:
                pass  # Ignore cleanup errors
            raise

    def _run_async(self, coro: Any) -> Any:
        """
        Run async coroutine in current context.

        Args:
            coro: Coroutine to run

        Returns:
            Coroutine result
        """
        try:
            loop = asyncio.get_running_loop()
            # We're in async context - this is a problem
            # For now, we'll create a new event loop in a thread
            # This is not ideal but works for the transition period
            import concurrent.futures
            import threading
            
            result = None
            exception = None
            
            def run_in_thread():
                nonlocal result, exception
                try:
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        result = new_loop.run_until_complete(coro)
                    finally:
                        new_loop.close()
                except Exception as e:
                    exception = e
            
            thread = threading.Thread(target=run_in_thread)
            thread.start()
            thread.join()
            
            if exception:
                raise exception
            return result
        except RuntimeError:
            # No running loop, create new one
            return asyncio.run(coro)

    def disconnect(self) -> None:
        """Close connection to queue system."""
        if self._queue_system and self._queue_initialized:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule shutdown
                    asyncio.create_task(self._queue_system.stop())
                else:
                    loop.run_until_complete(self._queue_system.stop())
            except RuntimeError:
                # No loop, create new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self._queue_system.stop())
                finally:
                    loop.close()

            self._queue_initialized = False
            self._queue_system = None
            logger.info("Queue system disconnected for SQLite proxy driver")

    def execute(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> None:
        """Execute SQL statement."""
        self._run_async(
            self._execute_operation("execute", sql=sql, params=params)
        )

    def fetchone(
        self, sql: str, params: Optional[Tuple[Any, ...]] = None
    ) -> Optional[Dict[str, Any]]:
        """Execute SELECT query and return first row."""
        return self._run_async(
            self._execute_operation("fetchone", sql=sql, params=params)
        )

    def fetchall(
        self, sql: str, params: Optional[Tuple[Any, ...]] = None
    ) -> List[Dict[str, Any]]:
        """Execute SELECT query and return all rows."""
        result = self._run_async(
            self._execute_operation("fetchall", sql=sql, params=params)
        )
        return result if result is not None else []

    def commit(self) -> None:
        """Commit current transaction."""
        self._run_async(self._execute_operation("commit"))

    def rollback(self) -> None:
        """Rollback current transaction."""
        self._run_async(self._execute_operation("rollback"))

    def lastrowid(self) -> Optional[int]:
        """Get last inserted row ID."""
        return self._run_async(self._execute_operation("lastrowid"))

    def create_schema(self, schema_sql: List[str]) -> None:
        """
        Create database schema.

        Args:
            schema_sql: List of SQL statements for schema creation
        """
        # Execute each statement sequentially
        for sql in schema_sql:
            self.execute(sql)
        self.commit()

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Get information about table columns."""
        result = self._run_async(
            self._execute_operation("get_table_info", table_name=table_name)
        )
        return result if result is not None else []

