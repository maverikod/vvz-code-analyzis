"""
Logging helpers for SVO client manager (chunker and vectorization trace).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Optional

# Separate logger for chunker requests
_chunker_logger: Optional[logging.Logger] = None

# Trace logger: what vectorizer sends/receives
_vectorization_trace_logger: Optional[logging.Logger] = None
TRACE_PREVIEW_LEN = 200


def _get_vectorization_trace_logger(
    root_dir: Optional[Path] = None,
) -> logging.Logger:
    """
    Logger for vectorization request/response trace.

    Writes to logs/vectorization_chunker_trace.log.
    """
    global _vectorization_trace_logger
    if _vectorization_trace_logger is None:
        _vectorization_trace_logger = logging.getLogger(
            "code_analysis.vectorization_chunker_trace"
        )
        _vectorization_trace_logger.setLevel(logging.INFO)
        _vectorization_trace_logger.propagate = False
        if not _vectorization_trace_logger.handlers:
            if root_dir:
                log_dir = Path(root_dir) / "logs"
            else:
                current_path = Path.cwd()
                log_dir = (
                    current_path / "logs"
                    if (current_path / "config.json").exists()
                    else Path("logs")
                )
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "vectorization_chunker_trace.log"
            handler = logging.FileHandler(log_file, encoding="utf-8")
            handler.setLevel(logging.INFO)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
                )
            )
            _vectorization_trace_logger.addHandler(handler)
    return _vectorization_trace_logger


def log_vectorization_trace(
    text_preview: str,
    result: bool,
    error: str = "",
    root_dir: Optional[Path] = None,
) -> None:
    """Write one line to vectorization trace log."""
    trace_log = _get_vectorization_trace_logger(root_dir)
    preview_escaped = (
        (text_preview or "").replace("\n", " ").replace("\r", " ")[:TRACE_PREVIEW_LEN]
    )
    err_escaped = (error or "").replace("\n", " ").replace("\r", " ")[:500]
    trace_log.info(
        "text=%s | result=%s | error=%s",
        preview_escaped,
        result,
        err_escaped,
    )


def _get_chunker_logger(root_dir: Optional[Path] = None) -> logging.Logger:
    """Get or create logger for chunker requests (logs/chunker_requests.log)."""
    global _chunker_logger

    if _chunker_logger is None:
        _chunker_logger = logging.getLogger("code_analysis.chunker_requests")
        _chunker_logger.setLevel(logging.INFO)
        _chunker_logger.propagate = False

        if not _chunker_logger.handlers:
            if root_dir:
                log_dir = Path(root_dir) / "logs"
            else:
                current_path = Path.cwd()
                log_dir = (
                    current_path / "logs"
                    if (current_path / "config.json").exists()
                    else Path("logs")
                )
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "chunker_requests.log"
            handler = logging.FileHandler(log_file, encoding="utf-8")
            handler.setLevel(logging.INFO)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(levelname)s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            _chunker_logger.addHandler(handler)

    return _chunker_logger
