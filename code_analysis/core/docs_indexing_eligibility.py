"""
Documentation file indexing eligibility (Markdown, JSON, YAML; project-relative paths).

Matcher semantics align with ``relative_path_list_pattern``: ``fnmatch`` when the
pattern contains ``*?[]``, otherwise exact path or directory-prefix match. Used by
later watcher / indexing waves; does not consult ``vectorize`` (gated elsewhere).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple, Union, cast

from .docs_indexing_defaults import DOCS_INDEX_FILE_SUFFIXES

# Stable reason codes for diagnostics / tests
REASON_DISABLED = "DISABLED"
REASON_PATH_TRAVERSAL = "PATH_TRAVERSAL"
REASON_NOT_ALLOWED_DOCS_SUFFIX = "NOT_ALLOWED_DOCS_SUFFIX"
# Backward-compatible alias (same value as before for non-md paths)
REASON_NOT_MARKDOWN_SUFFIX = REASON_NOT_ALLOWED_DOCS_SUFFIX
REASON_FILE_DELETED = "FILE_DELETED"
REASON_FILE_MISSING = "FILE_MISSING"
REASON_NOT_INCLUDED = "NOT_INCLUDED"
REASON_EXCLUDED = "EXCLUDED"
REASON_OUT_OF_ROOT_SCOPE = "OUT_OF_ROOT_SCOPE"


@dataclass(frozen=True)
class DocsMarkdownEligibilityVerdict:
    """Result of :func:`is_docs_markdown_eligible` (Markdown / JSON / YAML docs)."""

    eligible: bool
    reasons: Tuple[str, ...]

    @property
    def reason_codes(self) -> Tuple[str, ...]:
        """Alias for ``reasons`` (explicit diagnostics naming)."""
        return self.reasons


def _normalize_listing_pattern(raw: str) -> str:
    """Return normalize listing pattern."""
    s = str(raw).strip().replace("\\", "/")
    if s.startswith("./"):
        s = s[2:]
    return s


def _pattern_has_fnmatch_magic(pattern: str) -> bool:
    """Return pattern has fnmatch magic."""
    return any(ch in pattern for ch in "*?[]")


def project_relative_path_matches_glob(relative_posix: str, file_pattern: str) -> bool:
    """
    Match ``file_pattern`` against a project-relative POSIX path.

    Same contract as ``relative_path_matches_listing_pattern`` in commands (duplicated
    in core to avoid importing ``code_analysis.commands`` from core).
    """
    pat = _normalize_listing_pattern(file_pattern)
    if not pat:
        return True
    if not _pattern_has_fnmatch_magic(pat):
        if relative_posix == pat:
            return True
        pat_core = pat.rstrip("/")
        if pat_core:
            return relative_posix == pat_core or relative_posix.startswith(
                pat_core + "/"
            )
        return False
    return fnmatch.fnmatch(relative_posix, pat)


def normalize_project_relative_posix(
    raw_path: str,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Normalize user/FS input to a single project-relative POSIX path.

    Returns:
        ``(normalized, None)`` on success, or ``(None, REASON_PATH_TRAVERSAL)`` if invalid.
    """
    s = _normalize_listing_pattern(raw_path)
    if not s:
        return None, REASON_PATH_TRAVERSAL
    if s.startswith("/"):
        return None, REASON_PATH_TRAVERSAL
    if ":" in s and len(s) > 1 and s[1] == ":":  # Windows drive
        return None, REASON_PATH_TRAVERSAL
    parts = s.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return None, REASON_PATH_TRAVERSAL
    return s, None


def _literal_prefix_before_magic(pattern: str) -> str:
    """Return literal prefix before magic."""
    pat = _normalize_listing_pattern(pattern)
    for i, c in enumerate(pat):
        if c in "*?[":
            return pat[:i].rstrip("/")
    return pat.rstrip("/")


def _pattern_confined_to_doc_roots(pattern: str, roots: Sequence[str]) -> bool:
    """
    True if the pattern only matches under configured ``roots`` (rough static check).

    Patterns with an empty literal prefix before the first wildcard (e.g. ``**/*.md``)
    are not confined. Literal ``README.md`` is not confined under ``docs`` only.
    """
    pref = _literal_prefix_before_magic(pattern)
    if not pref:
        return False
    return any(pref == r or pref.startswith(r + "/") for r in roots)


def _under_any_root(rel: str, roots: Sequence[str]) -> bool:
    """Return under any root."""
    for r in roots:
        if rel == r or rel.startswith(r + "/"):
            return True
    return False


def _scope_ok(rel: str, roots: Sequence[str], include: Sequence[str]) -> bool:
    """
    Path is under configured roots, or allowed by an include pattern not confined
    to those roots (e.g. ``README.md``, ``**/*.md``).
    """
    if _under_any_root(rel, roots):
        return True
    for pat in include:
        if not project_relative_path_matches_glob(rel, pat):
            continue
        if not _pattern_confined_to_doc_roots(pat, roots):
            return True
    return False


def _coerce_docs_indexing(
    docs_indexing: Union[Mapping[str, Any], Any, None],
) -> Optional[Mapping[str, Any]]:
    """Return coerce docs indexing."""
    if docs_indexing is None:
        return None
    if hasattr(docs_indexing, "model_dump"):
        raw = docs_indexing.model_dump()
        return cast(Mapping[str, Any], raw)
    if isinstance(docs_indexing, Mapping):
        return docs_indexing
    return None


def is_docs_markdown_eligible(
    *,
    docs_indexing: Union[Mapping[str, Any], Any, None],
    relative_path: str,
    file_exists: bool = True,
    is_deleted: bool = False,
) -> DocsMarkdownEligibilityVerdict:
    """
    Return whether ``relative_path`` is eligible for documentation indexing.

    ``vectorize`` is ignored here (planned for a separate gate). ``exclude`` wins over
    ``include``. Allowed suffixes (case-insensitive): from
    :data:`code_analysis.core.docs_indexing_defaults.DOCS_INDEX_FILE_SUFFIXES`
    (``.md``, ``.json``, ``.yaml``, ``.yml``).
    """
    cfg = _coerce_docs_indexing(docs_indexing)

    enabled = bool(cfg.get("enabled")) if cfg else False
    if not enabled:
        return DocsMarkdownEligibilityVerdict(False, (REASON_DISABLED,))

    norm, terr = normalize_project_relative_posix(relative_path)
    if terr:
        return DocsMarkdownEligibilityVerdict(False, (terr,))
    assert norm is not None

    low = norm.lower()
    if not any(low.endswith(suf) for suf in DOCS_INDEX_FILE_SUFFIXES):
        return DocsMarkdownEligibilityVerdict(False, (REASON_NOT_ALLOWED_DOCS_SUFFIX,))

    roots = cfg.get("roots") if cfg else None
    include = cfg.get("include") if cfg else None
    exclude = cfg.get("exclude") if cfg else None
    if not isinstance(roots, (list, tuple)) or not isinstance(include, (list, tuple)):
        return DocsMarkdownEligibilityVerdict(False, (REASON_NOT_INCLUDED,))
    if not isinstance(exclude, (list, tuple)):
        exclude = ()

    roots_s = [str(r).strip() for r in roots if str(r).strip()]
    inc_s = [str(p).strip() for p in include if str(p).strip()]
    exc_s = [str(p).strip() for p in exclude if str(p).strip()]

    included = any(project_relative_path_matches_glob(norm, p) for p in inc_s)
    if not included:
        return DocsMarkdownEligibilityVerdict(False, (REASON_NOT_INCLUDED,))

    excluded = any(project_relative_path_matches_glob(norm, p) for p in exc_s)
    if excluded:
        return DocsMarkdownEligibilityVerdict(False, (REASON_EXCLUDED,))

    if not _scope_ok(norm, roots_s, inc_s):
        return DocsMarkdownEligibilityVerdict(False, (REASON_OUT_OF_ROOT_SCOPE,))

    if is_deleted:
        return DocsMarkdownEligibilityVerdict(False, (REASON_FILE_DELETED,))
    if not file_exists:
        return DocsMarkdownEligibilityVerdict(False, (REASON_FILE_MISSING,))

    return DocsMarkdownEligibilityVerdict(True, ())
