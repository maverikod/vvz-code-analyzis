"""
Bug report writer: append structured reports to docs/bug_reports/ for diagnostics.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def write_bug_report(
    tag: str,
    message: str,
    *,
    file_path: Optional[str] = None,
    file_id: Optional[int] = None,
    line: Optional[int] = None,
    doc_ref: Optional[str] = None,
    **extra: Any,
) -> None:
    """
    Append a structured bug report to docs/bug_reports/ for later analysis.

    Args:
        tag: Short identifier (e.g. CHUNKER_MISSING_MODEL).
        message: Human-readable description.
        file_path: Optional file path context.
        file_id: Optional file ID context.
        line: Optional line number context.
        doc_ref: Optional reference to documentation.
        **extra: Additional key-value context.
    """
    try:
        # Resolve docs/bug_reports relative to project root (cwd or parent of code_analysis)
        base = Path(__file__).resolve().parent.parent.parent
        reports_dir = base / "docs" / "bug_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "tag": tag,
            "message": message,
            "ts": datetime.now(tz=timezone.utc).isoformat(),
        }
        if file_path is not None:
            report["file_path"] = file_path
        if file_id is not None:
            report["file_id"] = file_id
        if line is not None:
            report["line"] = line
        if doc_ref is not None:
            report["doc_ref"] = doc_ref
        report.update(extra)
        log_path = reports_dir / "reports.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(report, ensure_ascii=False) + "\n")
        logger.debug("Bug report written: tag=%s path=%s", tag, log_path)
    except Exception as e:
        logger.warning("Failed to write bug report (%s): %s", tag, e)
