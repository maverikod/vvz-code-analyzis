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
            "Supported worker types are 'file_watcher' and 'vectorization'. "
            "The worker is registered in WorkerManager and runs as a daemon process.\n\n"
            "Operation flow:\n"
            "1. Validates root_dir exists and is a directory\n"
            "2. Loads config.json to get storage paths\n"
            "3. Opens database connection\n"
            "4. For file_watcher:\n"
            "   - Projects are discovered automatically in watch_dirs\n"
            "   - Resolves watch_dirs (defaults to [root_dir] if not provided)\n"
            "   - Starts file watcher worker process\n"
            "   - Registers worker in WorkerManager\n"
            "5. For vectorization:\n"
            "   - Gets base FAISS directory (project-scoped indexes: {faiss_dir}/{project_id}.bin)\n"
            "   - Loads SVO config for embedding service\n"
            "   - Starts universal vectorization worker process\n"
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
            "Use cases:\n"
            "- Start file watcher to monitor project changes\n"
            "- Start vectorization worker to process code chunks\n"
            "- Run workers in background for continuous processing\n\n"
            "Important notes:\n"
            "- Workers run as daemon processes\n"
            "- Workers are registered in WorkerManager\n"
            "- File watcher discovers projects automatically\n"
            "- Vectorization worker is universal - processes all projects from database automatically\n"
            "- Vectorization worker uses project-scoped FAISS indexes (no dataset concept)\n"
            "- Workers write logs to specified log path\n"
            "- Use stop_worker to stop workers gracefully"
        ),
        "parameters": {
            "worker_type": {
                "description": (
                    "Type of worker to start. Options: 'file_watcher', 'vectorization'. "
                    "file_watcher monitors directories for file changes. "
                    "vectorization processes code chunks for embedding."
                ),
                "type": "string",
                "required": True,
                "enum": ["file_watcher", "vectorization", "indexing"],
            },
            "root_dir": {
                "description": (
                    "Project root directory path. Can be absolute or relative. "
                    "Must contain data/code_analysis.db file and config.json. "
                    "Used to resolve storage paths (database, FAISS directory) for vectorization worker."
                ),
                "type": "string",
                "required": True,
            },
            "watch_dirs": {
                "description": (
                    "Directories to watch (file_watcher only). Defaults to [root_dir] if not provided. "
                    "Projects are discovered automatically by finding projectid files in these directories."
                ),
                "type": "array",
                "required": False,
                "items": {"type": "string"},
            },
            "scan_interval": {
                "description": (
                    "Scan interval in seconds (file_watcher only). Default is 60. "
                    "How often the worker scans directories for changes."
                ),
                "type": "integer",
                "required": False,
                "default": 60,
            },
            "poll_interval": {
                "description": (
                    "Poll interval in seconds (vectorization only). Default is 30. "
                    "How often the worker polls database for new chunks to process."
                ),
                "type": "integer",
                "required": False,
                "default": 30,
            },
            "batch_size": {
                "description": (
                    "Batch size (vectorization only). Default is 10. "
                    "Number of chunks to process in each batch."
                ),
                "type": "integer",
                "required": False,
                "default": 10,
            },
            "vector_dim": {
                "description": (
                    "Vector dimension (vectorization only). Default is 384. "
                    "Must match embedding service vector dimension."
                ),
                "type": "integer",
                "required": False,
                "default": 384,
            },
            "worker_log_path": {
                "description": (
                    "Optional log path for worker process. "
                    "Defaults to logs/file_watcher.log or logs/vectorization_worker.log."
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
                    "root_dir": "/home/user/projects/my_project",
                    "scan_interval": 60,
                },
                "explanation": (
                    "Starts file watcher worker that monitors root_dir for file changes. "
                    "Projects are discovered automatically."
                ),
            },
            {
                "description": "Start vectorization worker",
                "command": {
                    "worker_type": "vectorization",
                    "root_dir": "/home/user/projects/my_project",
                    "poll_interval": 30,
                    "batch_size": 10,
                },
                "explanation": (
                    "Starts universal vectorization worker that processes code chunks for embedding. "
                    "Worker automatically discovers all projects from database and processes them sequentially."
                ),
            },
            {
                "description": "Start file watcher with custom watch directories",
                "command": {
                    "worker_type": "file_watcher",
                    "root_dir": "/home/user/projects",
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
            "File watcher discovers projects automatically - no need to specify project_id",
            "Vectorization requires embedding service to be configured",
            "Adjust scan_interval and poll_interval based on workload",
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
