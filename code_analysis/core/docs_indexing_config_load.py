"""
Load ``code_analysis.docs_indexing`` from server JSON for watcher subprocess.

Returns a snapshot dict only when ``enabled`` is true; otherwise ``None`` so scanner
behavior matches pre-docs-indexing (Markdown never admitted via suffix rules).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def load_docs_indexing_from_config_path(config_path: Path) -> Optional[Dict[str, Any]]:
    """
    Return ``code_analysis.docs_indexing`` mapping when ``enabled`` is true.

    Missing file, invalid shape, or ``enabled`` false/absent yields ``None``.
    """
    try:
        resolved = Path(config_path).expanduser().resolve()
    except OSError:
        logger.debug("Could not resolve config_path for docs_indexing: %s", config_path)
        return None
    try:
        from .storage_paths import load_raw_config

        raw = load_raw_config(resolved)
    except Exception as e:
        logger.debug(
            "Could not load raw config for docs_indexing from %s: %s", resolved, e
        )
        return None
    ca = raw.get("code_analysis") or {}
    if not isinstance(ca, dict):
        return None
    di = ca.get("docs_indexing")
    if di is None:
        return None
    if not isinstance(di, dict):
        logger.warning("docs_indexing must be an object; ignoring")
        return None
    if not bool(di.get("enabled")):
        return None
    return dict(di)
