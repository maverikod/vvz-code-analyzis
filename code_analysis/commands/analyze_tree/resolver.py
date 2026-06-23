"""
Module → project file path resolution for analyze_tree.

``export_graph`` emits bare module stems (the raw ``imports.module`` column) and
never resolves them to project files. analyze_tree needs the opposite: given an
import row, decide whether it points at a file *inside the project* (and where),
or at the standard library, or at a third-party package.

This resolver builds a one-shot index over the project's file list (relative
paths) and resolves an import to a project-relative path using a longest-suffix
match with a same-directory preference. It is pure (no DB, no disk) so it is
fully unit-testable.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Iterable, Optional


def _stdlib_top_levels() -> frozenset[str]:
    """Top-level stdlib package names for the running interpreter.

    ``sys.stdlib_module_names`` exists on 3.10+; fall back to a small static set
    for older interpreters so classification still degrades gracefully.
    """
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
    """Resolve dotted module names to project-relative file paths.

    Construction indexes every project ``.py`` file by the candidate dotted
    suffixes it can satisfy. Resolution converts a module name to a path tail
    (``a.b.c`` → ``a/b/c.py`` or ``a/b/c/__init__.py``) and looks it up, breaking
    ties by shortest full path and, when provided, a shared top directory with
    the importing file.
    """

    def __init__(self, rel_paths: Iterable[str]) -> None:
        # Normalize to forward slashes; keep only python sources.
        self._rel_paths: list[str] = sorted(
            {p.replace("\\", "/").lstrip("./") for p in rel_paths if p}
        )
        # Map each candidate path tail → list of full rel_paths that end with it.
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
        # Tie-break: prefer a candidate sharing the importer's top directory,
        # then the shortest path (closest to a project-root layout).
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
        """Resolve one import row to a project file or an external classification.

        Mapping of the ``imports`` row shape:
        - ``from a.b import c`` → module=``a.b``, name=``c``. The dependency is on
          the module imported *from*; if ``a.b.c`` is itself a submodule file we
          prefer that, otherwise we fall back to the file ``a/b.py``.
        - ``import a.b.c`` → module is null, name=``a.b.c``; dependency is that path.
        """
        # Build the list of dotted names to try, in priority order.
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

        # Unresolved → external. Classify by the most specific dotted name we have.
        external_module = primary_module or nm or ""
        kind = "stdlib" if is_stdlib_module(external_module) else "third_party"
        return ResolvedImport(kind=kind, module=external_module)
