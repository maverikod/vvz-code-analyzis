"""
Metadata (schema) for start_worker and stop_worker MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict


def get_start_worker_metadata(
    name: str,
    version: str,
    descr: str,
    category: str,
    author: str,
    email: str,
) -> Dict[str, Any]:
    """Return full metadata dict for start_worker command."""
    return {
        "name": name,
        "version": version,
        "description": descr,
        "category": category,
        "author": author,
        "email": email,
        "detailed_description": (
            "The start_worker command starts a background worker process in a separate process. "
            "Supported worker types are 'file_watcher', 'vectorization', and 'indexing'. "
            "The worker is registered in WorkerManager and runs as a daemon process.\n\n"
            "Start kwargs are resolved through the same boot-parity resolvers the server "
            "itself uses at startup (code_analysis.core.worker_start_args): only "
            "parameters you explicitly pass override server config; everything else "
            "(batch_size, poll_interval, vector_dim, log path, enabled kill-switch) "
            "comes from code_analysis.worker / code_analysis.indexing_worker / "
            "code_analysis.file_watcher in server config, exactly like a worker "
            "started automatically at server boot. A worker whose config section "
            "disables it (e.g. indexing_worker.enabled=false) will not start; the "
            "command returns WORKER_START_SKIPPED with the reason.\n\n"
            "Operation flow:\n"
            "1. Resolves project_id to the project root (file_watcher's default "
            "watch_dirs only; vectorization and indexing are universal workers that "
            "process all projects from the database regardless of project_id)\n"
            "2. Loads config.json and resolves storage paths (database, FAISS "
            "directory, log directory)\n"
            "3. For file_watcher:\n"
            "   - Projects are discovered automatically in watch_dirs\n"
            "   - Resolves watch_dirs (defaults to a single directory at the "
            "project root resolved from project_id, if not provided)\n"
            "   - Starts file watcher worker process\n"
            "   - Registers worker in WorkerManager\n"
            "4. For vectorization:\n"
            "   - Gets base FAISS directory (project-scoped indexes: {faiss_dir}/{project_id}.bin)\n"
            "   - Loads SVO config for embedding service\n"
            "   - Starts universal vectorization worker process\n"
            "   - Registers worker in WorkerManager\n"
            "5. For indexing:\n"
            "   - Processes files with needs_chunking=1 across all projects\n"
            "   - Starts indexing worker process\n"
            "   - Registers worker in WorkerManager\n"
            "6. Returns worker start result with PID\n\n"
            "File Watcher Worker:\n"
            "- Monitors directories for file changes\n"
            "- Discovers projects automatically by finding projectid files\n"
            "- Scans at specified scan_interval\n"
            "- Processes new, changed, and deleted files\n"
            "- Uses lock files to prevent concurrent processing\n"
            "- Stores deleted files in version directory\n\n"
            "Vectorization Worker:\n"
            "- Processes code chunks for vectorization\n"
            "- Converts chunks to embeddings using embedding service\n"
            "- Stores vectors in FAISS index\n"
            "- Polls database at specified poll_interval\n"
            "   - Processes chunks in batches\n"
            "   - Uses project-scoped FAISS index ({faiss_dir}/{project_id}.bin)\n"
            "   - Automatically discovers all projects from database\n"
            "   - Processes projects sequentially, sorted by pending count\n\n"
            "Indexing Worker:\n"
            "- Processes files with needs_chunking=1 via driver index_file RPC\n"
            "- Universal - processes all projects from database automatically\n"
            "- Polls database at specified poll_interval, batch_size files per project per cycle\n\n"
            "Use cases:\n"
            "- Start file watcher to monitor project changes\n"
            "- Start vectorization worker to process code chunks\n"
            "- Start indexing worker to register/refresh files pending indexing\n"
            "- Run workers in background for continuous processing\n\n"
            "Important notes:\n"
            "- Workers run as daemon processes\n"
            "- Workers are registered in WorkerManager\n"
            "- File watcher discovers projects automatically\n"
            "- Vectorization and indexing workers are universal - they process all "
            "projects from database automatically; project_id does not scope them\n"
            "- Vectorization worker uses project-scoped FAISS indexes (no dataset concept)\n"
            "- Workers write logs to the resolved log path (config-driven by default, "
            "same location the server would use at boot)\n"
            "- Use stop_worker to stop workers gracefully"
        ),
        "parameters": {
            "worker_type": {
                "description": (
                    "Type of worker to start. Options: 'file_watcher', 'vectorization', "
                    "'indexing'. file_watcher monitors directories for file changes. "
                    "vectorization processes code chunks for embedding. indexing "
                    "registers/refreshes files pending indexing."
                ),
                "type": "string",
                "required": True,
                "enum": ["file_watcher", "vectorization", "indexing"],
            },
            "project_id": {
                "description": (
                    "Project UUID. Used to resolve the project root and storage paths "
                    "(database, FAISS directory, log directory). For file_watcher this "
                    "also supplies the default watch_dirs (the project root) when "
                    "watch_dirs is omitted. vectorization and indexing are universal "
                    "workers that process every project in the database once started; "
                    "project_id does not scope which projects they process."
                ),
                "type": "string",
                "required": True,
            },
            "watch_dirs": {
                "description": (
                    "Directories to watch (file_watcher only). Defaults to a single "
                    "directory at the project root resolved from project_id, if not "
                    "provided. Projects are discovered automatically by finding "
                    "projectid files in these directories."
                ),
                "type": "array",
                "required": False,
                "items": {"type": "string"},
            },
            "scan_interval": {
                "description": (
                    "Scan interval in seconds (file_watcher only). Omit to use "
                    "code_analysis.file_watcher.scan_interval from server config "
                    "(defaults to 60 there). How often the worker scans directories "
                    "for changes."
                ),
                "type": "integer",
                "required": False,
            },
            "poll_interval": {
                "description": (
                    "Poll interval in seconds (vectorization only; ignored for "
                    "indexing, which has its own worker loop). Omit to use "
                    "code_analysis.worker.poll_interval from server config. How often "
                    "the worker polls database for new chunks to process."
                ),
                "type": "integer",
                "required": False,
            },
            "batch_size": {
                "description": (
                    "Batch size (vectorization or indexing; ignored for file_watcher). "
                    "Omit to use the configured value for the given worker_type "
                    "(code_analysis.worker.batch_size for vectorization, "
                    "code_analysis.indexing_worker.batch_size for indexing). Number of "
                    "chunks/files to process in each batch/cycle."
                ),
                "type": "integer",
                "required": False,
            },
            "vector_dim": {
                "description": (
                    "Vector dimension (vectorization only). Omit to use "
                    "code_analysis.vector_dim from server config. Must match "
                    "embedding service vector dimension."
                ),
                "type": "integer",
                "required": False,
            },
            "worker_log_path": {
                "description": (
                    "Optional log path for worker process. Omit to use the "
                    "server-configured log path for the given worker_type, falling "
                    "back to server.log_dir when unset -- the same location the "
                    "server itself would use for this worker type at boot."
                ),
                "type": "string",
                "required": False,
            },
        },
        "usage_examples": [
            {
                "description": "Start file watcher worker",
                "command": {
                    "worker_type": "file_watcher",
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "scan_interval": 60,
                },
                "explanation": (
                    "Starts file watcher worker; without watch_dirs it defaults to "
                    "the project root resolved from project_id. Projects are "
                    "discovered automatically."
                ),
            },
            {
                "description": "Start vectorization worker",
                "command": {
                    "worker_type": "vectorization",
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "poll_interval": 30,
                    "batch_size": 5,
                },
                "explanation": (
                    "Starts universal vectorization worker that processes code chunks for embedding. "
                    "Worker automatically discovers all projects from database and processes them "
                    "sequentially; project_id is only used to resolve storage paths."
                ),
            },
            {
                "description": "Start file watcher with custom watch directories",
                "command": {
                    "worker_type": "file_watcher",
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "watch_dirs": [
                        "/home/user/projects/proj1",
                        "/home/user/projects/proj2",
                    ],
                },
                "explanation": (
                    "Starts file watcher that monitors multiple directories. "
                    "Projects are discovered in each directory."
                ),
            },
        ],
        "error_cases": {
            "WORKER_START_ERROR": {
                "description": "General error during worker start",
                "example": "Process start failure, database error, or config error",
                "solution": (
                    "Check database integrity, verify config.json exists, "
                    "ensure embedding service is configured (for vectorization), "
                    "check file permissions."
                ),
            },
            "WORKER_START_SKIPPED": {
                "description": (
                    "The resolved server config disables this worker type or is "
                    "missing required config (e.g. worker.enabled=false, "
                    "indexing_worker.enabled=false, file_watcher.enabled=false, or "
                    "no chunker configured for vectorization). The worker process "
                    "was not started; details.reason (via the error message) "
                    "explains why."
                ),
                "example": "indexing worker disabled in config",
                "solution": (
                    "Update the relevant code_analysis.* section in server config "
                    "to enable the worker type, or configure the missing section "
                    "(e.g. code_analysis.chunker for vectorization), then retry."
                ),
            },
        },
        "return_value": {
            "success": {
                "description": "Command executed successfully",
                "data": {
                    "success": "Whether worker was started successfully",
                    "worker_type": "Type of worker that was started",
                    "pid": "Process ID of the worker process",
                    "message": "Status message",
                },
                "example": {
                    "success": True,
                    "worker_type": "file_watcher",
                    "pid": 12345,
                    "message": "File watcher started (PID 12345)",
                },
            },
            "error": {
                "description": "Command failed",
                "code": "Error code (e.g., WORKER_START_ERROR)",
                "message": "Human-readable error message",
            },
        },
        "best_practices": [
            "Use stop_worker to stop workers gracefully before restarting",
            "project_id is required for all worker types (resolves storage paths; "
            "also supplies file_watcher's default watch_dirs) -- file watcher "
            "still discovers individual projects automatically within watch_dirs",
            "Vectorization requires a chunker to be configured in server config",
            "Omit scan_interval/poll_interval/batch_size/vector_dim/worker_log_path "
            "to inherit the same values the server would use starting this worker "
            "at boot; pass them only to override server config for this one start",
            "Monitor worker logs to ensure proper operation",
            "Workers run as daemon processes - they stop when parent process stops",
        ],
    }


def get_stop_worker_metadata(
    name: str,
    version: str,
    descr: str,
    category: str,
    author: str,
    email: str,
) -> Dict[str, Any]:
    """Return full metadata dict for stop_worker command."""
    return {
        "name": name,
        "version": version,
        "description": descr,
        "category": category,
        "author": author,
        "email": email,
        "detailed_description": (
            "The stop_worker command stops background worker processes by type. "
            "It stops all workers of the specified type that are registered in WorkerManager. "
            "The command attempts graceful shutdown first, then force kills if timeout is exceeded.\n\n"
            "Operation flow:\n"
            "1. Gets WorkerManager instance\n"
            "2. Retrieves all workers of specified type from registry\n"
            "3. For each worker:\n"
            "   - Attempts graceful shutdown (sends termination signal)\n"
            "   - Waits for process to terminate (up to timeout seconds)\n"
            "   - If timeout exceeded, force kills the process\n"
            "4. Unregisters workers from WorkerManager\n"
            "5. Returns stop summary with counts\n\n"
            "Shutdown Process:\n"
            "- First attempts graceful shutdown (SIGTERM)\n"
            "- Waits for process to terminate naturally\n"
            "- If timeout exceeded, force kills (SIGKILL)\n"
            "- Removes worker from registry\n\n"
            "Worker Types:\n"
            "- file_watcher: Stops all file watcher workers\n"
            "- vectorization: Stops all vectorization workers\n\n"
            "Use cases:\n"
            "- Stop workers before restarting\n"
            "- Stop workers for maintenance\n"
            "- Clean up worker processes\n\n"
            "Important notes:\n"
            "- Stops ALL workers of the specified type\n"
            "- Graceful shutdown is attempted first\n"
            "- Force kill is used if timeout exceeded\n"
            "- Workers are unregistered from WorkerManager\n"
            "- Default timeout is 10 seconds"
        ),
        "parameters": {
            "worker_type": {
                "description": (
                    "Type of worker to stop. Options: 'file_watcher', 'vectorization'. "
                    "Stops all workers of this type that are registered."
                ),
                "type": "string",
                "required": True,
                "enum": ["file_watcher", "vectorization", "indexing"],
            },
            "timeout": {
                "description": (
                    "Timeout in seconds before force kill. Default is 10. "
                    "If worker doesn't stop gracefully within timeout, it will be force killed."
                ),
                "type": "integer",
                "required": False,
                "default": 10,
            },
        },
        "usage_examples": [
            {
                "description": "Stop file watcher workers",
                "command": {"worker_type": "file_watcher", "timeout": 10},
                "explanation": (
                    "Stops all file watcher workers gracefully. "
                    "Force kills if they don't stop within 10 seconds."
                ),
            },
            {
                "description": "Stop vectorization workers",
                "command": {"worker_type": "vectorization", "timeout": 5},
                "explanation": (
                    "Stops all vectorization workers gracefully. "
                    "Force kills if they don't stop within 5 seconds."
                ),
            },
        ],
        "error_cases": {
            "WORKER_STOP_ERROR": {
                "description": "General error during worker stop",
                "example": "Process not found, permission denied, or kill failure",
                "solution": (
                    "Check if workers are running, verify process permissions, "
                    "ensure WorkerManager is accessible."
                ),
            },
        },
        "return_value": {
            "success": {
                "description": "Command executed successfully",
                "data": {
                    "worker_type": "Type of workers that were stopped",
                    "stopped_count": "Number of workers stopped",
                    "failed_count": "Number of workers that failed to stop",
                    "message": "Status message",
                },
                "example": {
                    "worker_type": "file_watcher",
                    "stopped_count": 2,
                    "failed_count": 0,
                    "message": "Stopped 2 file_watcher worker(s)",
                },
            },
            "error": {
                "description": "Command failed",
                "code": "Error code (e.g., WORKER_STOP_ERROR)",
                "message": "Human-readable error message",
            },
        },
        "best_practices": [
            "Use graceful shutdown timeout appropriate for worker workload",
            "Workers should handle SIGTERM for graceful shutdown",
            "Force kill is used as last resort if timeout exceeded",
            "Check worker status after stopping to verify shutdown",
            "Stop workers before restarting to avoid conflicts",
        ],
    }
