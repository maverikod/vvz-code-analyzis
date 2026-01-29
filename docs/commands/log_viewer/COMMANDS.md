# Log Viewer Commands

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Both in `commands/log_viewer_mcp_commands.py`. Internal: `ListLogFilesCommand`, `LogViewerCommand` in `commands/log_viewer.py`.

## view_worker_logs

View log content for a worker (file_watcher, vectorization). Supports time range, level, search text. Returns log lines or tail.

## list_worker_logs

List available worker log files or identifiers for the server.
