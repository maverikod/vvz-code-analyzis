"""
Shared constants for log viewer MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# Default log filenames per worker type (one log per worker)
WORKER_LOG_FILENAMES = {
    "file_watcher": "file_watcher.log",
    "vectorization": "vectorization_worker.log",
    "indexing": "indexing_worker.log",
    "database_driver": "database_driver.log",
    "analysis": "comprehensive_analysis.log",
    "server": "mcp_server.log",
}
