"""
Watch directory spec and builder for multi-project file watcher.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


@dataclass(frozen=True, slots=True)
class WatchDirSpec:
    """
    Watched directory specification.

    Represents a directory to scan for projects. Projects are discovered
    automatically by finding projectid files within this directory.

    Attributes:
        watch_dir: Directory to scan for projects
        watch_dir_id: UUID4 identifier for this watch directory
        ignore_patterns: Optional per-dir glob patterns; files matching these
            are not indexed. Merged with global ignore_patterns when scanning.
    """

    watch_dir: Path
    watch_dir_id: str
    ignore_patterns: Tuple[str, ...] = ()


def build_watch_dir_specs(
    watch_dirs: Sequence[Dict[str, Any]],
) -> List[WatchDirSpec]:
    """
    Build `WatchDirSpec` list from watch directory config.

    Args:
        watch_dirs: Sequence of watch directory configs. Each dict must have
            'id' and 'path' keys; optional 'ignore_patterns' (list of glob
            patterns to exclude from indexing for this directory).

    Returns:
        List of watch directory specs.
    """
    specs: List[WatchDirSpec] = []
    for watch_dir_config in watch_dirs:
        if isinstance(watch_dir_config, str):
            raise ValueError(
                "Old watch_dirs format (string array) is not supported. "
                "Use format: [{'id': 'uuid4', 'path': '/path', 'ignore_patterns': [...]}]"
            )
        watch_dir_id = watch_dir_config["id"]
        watch_dir_path = watch_dir_config["path"]
        watch_path = Path(watch_dir_path).resolve()
        raw_ignore = watch_dir_config.get("ignore_patterns")
        ignore_patterns: Tuple[str, ...] = ()
        if isinstance(raw_ignore, (list, tuple)):
            ignore_patterns = tuple(str(p) for p in raw_ignore if p)
        specs.append(
            WatchDirSpec(
                watch_dir=watch_path,
                watch_dir_id=watch_dir_id,
                ignore_patterns=ignore_patterns,
            )
        )
    return specs
