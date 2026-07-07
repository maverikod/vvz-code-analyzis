"""
Logging helpers for SVO client manager (chunker and vectorization trace).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

# Separate logger for chunker requests
_chunker_logger: Optional[logging.Logger] = None

# Trace logger: what vectorizer sends/receives
_vectorization_trace_logger: Optional[logging.Logger] = None
TRACE_PREVIEW_LEN = 200


def _resolve_log_dir(root_dir: Optional[Path]) -> Optional[Path]:
    """Return the first writable directory for SVO client-manager logs.

    Tries, in order: ``$CASMGR_LOG_DIR``, the caller's ``root_dir/logs``
    (dev/local layout), the canonical server log dir ``/var/log/casmgr``, and a
    temp dir. Returns ``None`` when none is writable so callers fall back to a
    no-op handler instead of raising: under a packaged host ``root_dir`` is the
    read-only ``/etc/casmgr`` config dir, and a logging failure there must never
    break chunking/vectorization.
    """
    candidates = []
    env_dir = os.environ.get("CASMGR_LOG_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    if root_dir:
        candidates.append(Path(root_dir) / "logs")
    else:
        current_path = Path.cwd()
        candidates.append(
            current_path / "logs"
            if (current_path / "config.json").exists()
            else Path("logs")
        )
    candidates.append(Path("/var/log/casmgr"))
    candidates.append(Path(tempfile.gettempdir()) / "casmgr-logs")

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            if os.access(candidate, os.W_OK):
                return candidate
        except OSError:
            continue
    return None


def _build_file_handler(
    root_dir: Optional[Path], filename: str, fmt: str
) -> logging.Handler:
    """Create a FileHandler in a writable log dir, or a NullHandler on failure."""
    log_dir = _resolve_log_dir(root_dir)
    handler: logging.Handler
    if log_dir is not None:
        try:
            handler = logging.FileHandler(log_dir / filename, encoding="utf-8")
            handler.setFormatter(
                logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
            )
        except OSError:
            handler = logging.NullHandler()
    else:
        handler = logging.NullHandler()
    handler.setLevel(logging.INFO)
    return handler


def _get_vectorization_trace_logger(
    root_dir: Optional[Path] = None,
) -> logging.Logger:
    """
    Logger for vectorization request/response trace.

    Writes to ``<writable-log-dir>/vectorization_chunker_trace.log``.
    """
    global _vectorization_trace_logger
    if _vectorization_trace_logger is None:
        _vectorization_trace_logger = logging.getLogger(
            "code_analysis.vectorization_chunker_trace"
        )
        _vectorization_trace_logger.setLevel(logging.INFO)
        _vectorization_trace_logger.propagate = False
        if not _vectorization_trace_logger.handlers:
            _vectorization_trace_logger.addHandler(
                _build_file_handler(
                    root_dir,
                    "vectorization_chunker_trace.log",
                    "%(asctime)s | %(message)s",
                )
            )
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
    """Get or create logger for chunker requests (chunker_requests.log)."""
    global _chunker_logger

    if _chunker_logger is None:
        _chunker_logger = logging.getLogger("code_analysis.chunker_requests")
        _chunker_logger.setLevel(logging.INFO)
        _chunker_logger.propagate = False

        if not _chunker_logger.handlers:
            _chunker_logger.addHandler(
                _build_file_handler(
                    root_dir,
                    "chunker_requests.log",
                    "%(asctime)s | %(levelname)s | %(message)s",
                )
            )

    return _chunker_logger
