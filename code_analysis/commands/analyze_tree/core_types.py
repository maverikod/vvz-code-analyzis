"""
Plain data structures shared by the analyze_tree core and its mode post-processors.

Keeping these free of DB/disk dependencies lets the modes be unit-tested by
constructing a ``CoreData`` directly.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Edge:
    """One resolved import edge.

    ``src`` is the importing file's project-relative path. ``kind`` is one of
    ``project`` / ``stdlib`` / ``third_party``. ``target_rel`` is set only when
    ``kind == "project"`` (the imported project file). ``module`` is the dotted
    name as seen in the import row (useful for external grouping).
    """

    src: str
    kind: str
    module: str
    target_rel: Optional[str] = None


@dataclass
class CoreData:
    """Result of the shared core, consumed by every mode."""

    roots: list[str]
    internal_files: list[str]
    internal_set: set[str]
    project_files: set[str]
    edges: list[Edge]
    staleness: dict
    truncated: bool = False
    # Filled only for the structure mode (rel_path → composition dict).
    structure_by_file: dict[str, dict] = field(default_factory=dict)
