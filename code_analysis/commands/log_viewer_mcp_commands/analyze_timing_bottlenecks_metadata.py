"""
Metadata for analyze_timing_bottlenecks command (AI/man page style).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict


def get_analyze_timing_bottlenecks_metadata(cls: Any) -> Dict[str, Any]:
    """Build metadata dict for AnalyzeTimingBottlenecksMCPCommand."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "parameters_summary": (
            "Log-based params only: log_path, worker_type, from_time, to_time, tail, limit, top_n. "
            "No project_id; command analyzes worker log files."
        ),
        "detailed_description": (
            "SCOPE — This command is about THIS SERVER's own internal operations (the code-analysis "
            "server process: its workers, chunking, embedding, DB access, etc.). It does NOT analyze "
            "or time user projects that the server indexes or serves. Use it to find performance "
            "bottlenecks in the server implementation, not in client/watched project code.\n\n"
            "The analyze_timing_bottlenecks command reads a worker log file produced by this server, "
            "collects every line that contains a [TIMING] entry (format: [TIMING] op_name duration=X.XXXs "
            "[key=value ...]), and aggregates them by operation name. It reports total time, average time, "
            "count, min, and max per operation, and returns two bottleneck lists: by total time "
            "(operations that consume the most time overall) and by average time (slowest per call).\n\n"
            "Operation flow:\n"
            "1. Resolve log file path: use log_path if provided, otherwise resolve from worker_type "
            "and server config.\n"
            "2. Open log file for reading (UTF-8, errors replaced).\n"
            "3. If tail is set: read only the last tail lines (and cap at limit).\n"
            "4. Otherwise: read lines sequentially up to limit; optionally filter by from_time and to_time.\n"
            "5. For each line, detect [TIMING] and parse op_name and duration=X.XXXs with a regex.\n"
            "6. Aggregate by op_name: collect all durations, then compute count, sum, avg, min, max.\n"
            "7. Sort operations by total_sec descending; take first top_n as bottlenecks_by_total.\n"
            "8. Sort operations by avg_sec descending; take first top_n as bottlenecks_by_avg.\n"
            "9. Return all operations plus the two bottleneck lists and summary counts.\n\n"
            "When to use: Enable log_all_operations_timing in code_analysis.worker config so that [TIMING] "
            "lines are written. Then run this command on the server's worker log to find which internal "
            "operations dominate total time or have the highest per-call latency. Use tail for recent "
            "activity; use from_time/to_time for a specific time window.\n\n"
            "Log format: Lines must contain [TIMING] and the pattern 'op_name duration=X.XXXs'."
        ),
        "parameters": {
            "log_path": {
                "description": "Path to THIS SERVER's worker log file. Optional if worker_type set.",
                "type": "string",
                "required": False,
                "examples": ["logs/vectorization_worker.log"],
            },
            "worker_type": {
                "description": "Type of worker whose log to analyze. Default: vectorization.",
                "type": "string",
                "required": False,
                "enum": [
                    "file_watcher",
                    "vectorization",
                    "indexing",
                    "database_driver",
                    "analysis",
                ],
                "default": "vectorization",
            },
            "from_time": {
                "description": "Start of time window. ISO or YYYY-MM-DD HH:MM:SS. Ignored when tail set.",
                "type": "string",
                "required": False,
            },
            "to_time": {
                "description": "End of time window. Same formats as from_time.",
                "type": "string",
                "required": False,
            },
            "tail": {
                "description": "If set, only the last N lines are read. When set, from_time and to_time are ignored.",
                "type": "integer",
                "required": False,
                "examples": [1000, 50000],
            },
            "limit": {
                "description": "Maximum number of log lines to scan when not using tail. Default 50000.",
                "type": "integer",
                "required": False,
                "default": 50000,
            },
            "top_n": {
                "description": "Number of top operations in bottlenecks_by_total and bottlenecks_by_avg. 1-100. Default 10.",
                "type": "integer",
                "required": False,
                "default": 10,
                "minimum": 1,
                "maximum": 100,
            },
        },
        "usage_examples": [
            {
                "description": "Analyze last 10k lines of vectorization log",
                "command": {"worker_type": "vectorization", "tail": 10000},
                "explanation": "Reads last 10000 lines and reports bottlenecks.",
            },
            {
                "description": "Analyze by time window",
                "command": {
                    "log_path": "logs/vectorization_worker.log",
                    "from_time": "2025-02-08 00:00:00",
                    "to_time": "2025-02-08 23:59:59",
                },
                "explanation": "Analyzes only lines within the given day.",
            },
            {
                "description": "Top 20 bottlenecks",
                "command": {"worker_type": "vectorization", "tail": 50000, "top_n": 20},
                "explanation": "Last 50k lines, top 20 by total and by average time.",
            },
        ],
        "error_cases": {
            "TIMING_DISABLED": {
                "description": "log_all_operations_timing is false in config.",
                "solution": "Set log_all_operations_timing to true and restart server/worker.",
            },
            "MISSING_LOG_PATH": {
                "description": "Neither log_path nor worker_type provided or path could not be resolved.",
                "solution": "Provide log_path or worker_type and ensure config is available.",
            },
            "LOG_FILE_NOT_FOUND": {
                "description": "The resolved log file does not exist or is not a regular file.",
                "solution": "Check path and that the worker has written to the log.",
            },
            "LOG_READ_ERROR": {
                "description": "OS error while reading the log file.",
                "solution": "Ensure file is readable and disk is accessible.",
            },
        },
        "return_value": {
            "success": {
                "description": "Command executed successfully.",
                "data": {
                    "log_path": "Resolved path of the analyzed log file.",
                    "from_time": "from_time parameter (or null).",
                    "to_time": "to_time parameter (or null).",
                    "tail": "tail parameter (or null).",
                    "lines_scanned": "Number of log lines read.",
                    "timing_events": "Number of [TIMING] lines parsed and aggregated.",
                    "total_duration_sec": "Sum of all operation durations (seconds).",
                    "operations": "List of all operations with op_name, count, total_sec, avg_sec, min_sec, max_sec. Sorted by total_sec descending.",
                    "bottlenecks_by_total": "First top_n operations by total_sec.",
                    "bottlenecks_by_avg": "First top_n operations by avg_sec.",
                    "message": "Human-readable summary.",
                },
                "example": {
                    "log_path": "logs/vectorization_worker.log",
                    "tail": 10000,
                    "lines_scanned": 10000,
                    "timing_events": 1523,
                    "total_duration_sec": 456.789,
                    "operations": [
                        {
                            "op_name": "Step0_get_chunks_batch",
                            "count": 100,
                            "total_sec": 120.5,
                            "avg_sec": 1.205,
                            "min_sec": 0.5,
                            "max_sec": 3.2,
                        }
                    ],
                    "bottlenecks_by_total": "[... top_n by total_sec ...]",
                    "bottlenecks_by_avg": "[... top_n by avg_sec ...]",
                    "message": "Parsed 1523 timing events from 10000 lines; total time 456.8s across 12 operations.",
                },
            },
            "error": {
                "description": "Command failed.",
                "code": "One of TIMING_DISABLED, MISSING_LOG_PATH, LOG_FILE_NOT_FOUND, LOG_READ_ERROR.",
                "message": "Human-readable error message.",
            },
        },
        "best_practices": [
            "Remember: this analyzes the server's own code (workers, chunking, DB), not user projects.",
            "Enable log_all_operations_timing in worker config before collecting data.",
            "Use tail for recent bottleneck analysis; use from_time/to_time for a specific window.",
            "Compare bottlenecks_by_total (where time is spent) with bottlenecks_by_avg (slow per call).",
            "Let the worker run for a while to accumulate timing data before analyzing.",
        ],
    }
