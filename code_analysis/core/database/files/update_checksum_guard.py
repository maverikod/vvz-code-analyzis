"""
Indexer checksum skip guard for update_file_data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _is_fk_or_integrity_error(exc: Exception) -> bool:
    """True if the exception is FK or integrity-related (no silent swallow)."""
    s = str(exc).lower()
    return "foreign key" in s or "integrity" in s


def try_skip_reindex_by_checksum(
    database: Any,
    *,
    abs_path: str,
    file_id: str,
    file_record: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Return skip result dict if source SHA-256 equals stored tree_checksum; else None.

    When checksums match (C-006 / C-022), clears vectors and sets needs_chunking=1,
    then returns success with skipped=True. On DB error during skip path, returns
    error dict. When stored_checksum is None or differs, returns None to proceed
    with full reindex.
    """
    source_checksum = hashlib.sha256(Path(abs_path).read_bytes()).hexdigest()
    stored_checksum = file_record.get("tree_checksum")
    if stored_checksum is None or stored_checksum != source_checksum:
        return None

    try:
        database._clear_file_vectors(file_id)
        database._execute(
            "UPDATE files SET needs_chunking = 1 WHERE id = ?",
            (file_id,),
        )
        database._commit()
    except Exception as e:
        logger.error(
            "Error clearing vectors / setting needs_chunking on skip: %s",
            e,
            exc_info=True,
        )
        if _is_fk_or_integrity_error(e):
            err_msg = f"Database foreign key constraint error: {e}"
        else:
            err_msg = f"Failed on skip path: {e}"
        return {
            "success": False,
            "error": err_msg,
            "file_path": abs_path,
            "file_id": file_id,
        }

    return {
        "success": True,
        "file_path": abs_path,
        "file_id": file_id,
        "skipped": True,
    }
