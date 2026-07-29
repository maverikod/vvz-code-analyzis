"""
Whitelist of non-Python text file formats eligible for lightweight indexing.

Bug cluster (688d2d01 / 13945588 / 597ea8c5 / fe1cf739): ``update_indexes`` walked
only ``.py`` files (see ``core.venv_path_policy.collect_python_files_for_indexing``),
so every other project file -- ``pyproject.toml``, shell scripts, ``.gitignore``,
plain text -- never got a ``files`` row (no ``file_id`` -> unlockable for AI Editor)
and never got ``code_content`` (invisible to fulltext search).

This whitelist drives a LIGHTWEIGHT indexing path
(``update_indexes_analyzer.analyze_file``'s ``use_lightweight_text_pipeline``
branch): the file gets a real ``files`` row and its body is mirrored into
``code_content`` / ``code_content_fts`` for fulltext visibility, but it NEVER
enters the Python CST/AST/entity-extraction pipeline (``sync_file_to_db_atomic``)
-- that pipeline assumes valid Python source and stays exclusively reachable
from ``.py`` files, unchanged by this feature.

The four formats already covered by the pre-existing, config-gated
``docs_indexing`` feature (``.md``/``.json``/``.yaml``/``.yml`` -- see
``core.docs_indexing_defaults``/``core.docs_indexing_eligibility``) are also
listed here on purpose: that feature is OFF by default and scoped to
``docs_indexing.roots``/``include`` (typically just ``docs/`` + ``README.md``).
When a caller does not supply a ``docs_indexing`` snapshot at all (the
``update_indexes`` command today) or the path falls outside its configured
scope, this whitelist is the fallback that still gives the file a lockable
row and fulltext-visible content -- see ``analyze_file`` for the precedence
rule (an explicit docs-eligibility REJECTION from a caller that DID supply
``docs_indexing`` is never overridden by this whitelist).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Final, FrozenSet

# Extensions (lowercase, with leading dot) indexed with content but WITHOUT
# Python CST/AST/entity analysis. Superset of the docs_indexing suffixes
# (.md/.json/.yaml/.yml) -- see module docstring for the precedence rule with
# that feature.
TEXT_INDEX_FILE_SUFFIXES: Final[FrozenSet[str]] = frozenset(
    {
        ".toml",
        ".sh",
        ".md",
        ".txt",
        ".yaml",
        ".yml",
        ".json",
        ".cfg",
        ".ini",
    }
)

# Extensionless dotfile basenames indexed the same way. ``Path.suffix`` is
# empty for these (``.gitignore`` has no further ``.`` after the leading dot,
# so pathlib treats the whole name as the stem), hence the separate set.
TEXT_INDEX_DOTFILE_BASENAMES: Final[FrozenSet[str]] = frozenset({".gitignore"})

# Size bound: files larger than this are left unindexed by this feature (not
# truncated -- a partial code_content row would be misleading for fulltext
# hits). Matches DEFAULT_READ_PROJECT_TEXT_JSON_STRUCTURED_MAX_BYTES (1 MiB),
# the existing bound this codebase already applies to structured text reads
# (see core/constants.py) -- reused here for consistency rather than picking
# a new number. Applies only to the always-non-docs whitelist members (see
# ``is_text_index_eligible`` / ``analyze_file`` -- the docs-suffix formats
# keep the pre-existing docs_indexing read path, unguarded, unchanged).
TEXT_INDEX_MAX_BYTES: Final[int] = 1_048_576

# Bytes sniffed from the head of a candidate file to detect binary content
# before it is decoded as text (a NUL byte in this sample is treated as
# binary and the file is skipped).
TEXT_INDEX_BINARY_SNIFF_BYTES: Final[int] = 8192


def is_text_index_eligible(relative_path: str) -> bool:
    """True if ``relative_path``'s extension/basename is on the text whitelist.

    Args:
        relative_path: Project-relative path (POSIX or native separators
            both tolerated -- only the final path segment is inspected).

    Returns:
        True when the lowercase extension is in :data:`TEXT_INDEX_FILE_SUFFIXES`,
        or the file has no extension and its basename is in
        :data:`TEXT_INDEX_DOTFILE_BASENAMES` (e.g. ``.gitignore``).
    """
    name = str(relative_path).replace("\\", "/").rsplit("/", 1)[-1]
    p = PurePosixPath(name)
    suf = p.suffix.lower()
    if suf in TEXT_INDEX_FILE_SUFFIXES:
        return True
    if not suf and p.name.lower() in TEXT_INDEX_DOTFILE_BASENAMES:
        return True
    return False


def looks_binary(sample: bytes) -> bool:
    """True if ``sample`` (a head-of-file byte slice) looks like binary content.

    Uses a simple, well-established heuristic: presence of a NUL byte. Real
    UTF-8/ASCII text (the only content this whitelist ever mirrors into
    ``code_content``) never legitimately contains one.

    Args:
        sample: Leading bytes of a candidate file.

    Returns:
        True when ``sample`` contains a NUL byte.
    """
    return b"\x00" in sample
