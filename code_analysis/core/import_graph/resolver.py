"""
Module → project file path resolution (shared core utility).

``export_graph`` emits bare module stems and never resolves them to project
files. Both ``analyze_tree`` and the comprehensive_analysis circular-import check
need the opposite: given an import row, decide whether it points at a file
*inside the project* (and where), or at the standard library, or third-party.

This resolver builds a one-shot index over the project's file list (relative
paths) and resolves an import to a project-relative path using a longest-suffix
match with a same-directory preference. It is pure (no DB, no disk) so it is
fully unit-testable, and lives in ``core`` so command and integrity layers share
exactly one resolution implementation (see TZ-CA-INDEX-INTEGRITY-001 C-3).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Iterable, Optional


def _stdlib_top_levels() -> frozenset[str]:
    """Top-level stdlib package names for the running interpreter."""
    names = getattr(sys, "stdlib_module_names", None)
    if names:
        return frozenset(names)
    return frozenset(
        {
            "os", "sys", "re", "json", "io", "abc", "enum", "typing", "pathlib",
            "logging", "functools", "itertools", "collections", "dataclasses",
            "datetime", "time", "math", "hashlib", "subprocess", "threading",
            "asyncio", "contextlib", "uuid", "tempfile", "shutil", "sqlite3",
        }
    )


STDLIB_TOP_LEVELS = _stdlib_top_levels()


def is_stdlib_module(module: str) -> bool:
    """True when ``module``'s top-level package is part of the standard library."""
    if not module:
        return False
    top = module.split(".", 1)[0]
    return top in STDLIB_TOP_LEVELS


@dataclass(frozen=True)
class ResolvedImport:
    """Outcome of resolving one import row.

    Exactly one of ``rel_path`` (project file) is set, otherwise the import is
    external and ``kind`` is ``"stdlib"`` or ``"third_party"`` with ``module``
    holding the unresolved dotted name.
    """

    kind: str  # "project" | "stdlib" | "third_party"
    module: str  # dotted module name as seen in the import row (best effort)
    rel_path: Optional[str] = None  # set when kind == "project"


class ModulePathResolver:
    """Resolve dotted module names to project-relative file paths."""

    def __init__(self, rel_paths: Iterable[str]) -> None:
        self._rel_paths: list[str] = sorted(
            {p.replace("\\", "/").lstrip("./") for p in rel_paths if p}
        )
        self._py = [p for p in self._rel_paths if p.endswith(".py")]
        self._set = set(self._py)

    @staticmethod
    def _module_to_tails(module: str) -> list[str]:
        """Path tails a dotted module could map to (module file, then package)."""
        base = module.replace(".", "/")
        return [f"{base}.py", f"{base}/__init__.py"]

    def _match_tail(self, tail: str, importer_rel: Optional[str]) -> Optional[str]:
        """Best project file whose path is, or ends with, ``tail``."""
        if tail in self._set:
            return tail
        suffix = "/" + tail
        candidates = [p for p in self._py if p.endswith(suffix)]
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        importer_top = (
            importer_rel.split("/", 1)[0] if importer_rel and "/" in importer_rel else None
        )

        def sort_key(path: str) -> tuple[int, int, str]:
            same_top = 0 if (importer_top and path.startswith(importer_top + "/")) else 1
            return (same_top, path.count("/"), path)

        return sorted(candidates, key=sort_key)[0]

    def resolve(
        self,
        *,
        module: Optional[str],
        name: Optional[str],
        import_type: Optional[str] = None,
        importer_rel: Optional[str] = None,
    ) -> ResolvedImport:
        """Resolve one import row to a project file or an external classification."""
        dotted_attempts: list[str] = []
        primary_module = (module or "").strip()
        nm = (name or "").strip()
        if primary_module:
            if nm:
                dotted_attempts.append(f"{primary_module}.{nm}")
            dotted_attempts.append(primary_module)
        elif nm:
            dotted_attempts.append(nm)

        for dotted in dotted_attempts:
            for tail in self._module_to_tails(dotted):
                hit = self._match_tail(tail, importer_rel)
                if hit:
                    return ResolvedImport(kind="project", module=dotted, rel_path=hit)

        external_module = primary_module or nm or ""
        kind = "stdlib" if is_stdlib_module(external_module) else "third_party"
        return ResolvedImport(kind=kind, module=external_module)
