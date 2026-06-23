"""
Per-file checksum staleness gate for analyze_tree.

Mirrors ``ChecksumSyncPolicy`` (C-006): analysis must run on a VALID tree, never
on stale DB rows. For each file we compare the current on-disk content checksum
against the DB-indexed ``files.tree_checksum`` and the active-edit-session state,
then bucket the file. This module is pure (no disk, no DB) so it is unit-testable;
the caller supplies the already-read checksums and session flag.

Buckets (the ``staleness`` block reports counts per bucket):
- ``sha_match``              — DB row is current; served from the index (fast path).
- ``rebuilt``               — checksum mismatch / no stored checksum / not indexed
                              content: the DB row is stale and would be rebuilt
                              from disk. (analyze_tree is read-only; it flags these
                              rather than writing sidecars.)
- ``skipped_active_session`` — an edit session holds the file; its tree is truth,
                              so we neither trust the DB row nor rebuild.
- ``not_in_db``             — file exists on disk but has no project file row.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from code_analysis.commands.universal_file_edit.sha_sync_policy import ShaSyncBranch
from code_analysis.core.tree_lifecycle.checksum import ChecksumSyncPolicy

SHA_MATCH = "sha_match"
REBUILT = "rebuilt"
SKIPPED_ACTIVE_SESSION = "skipped_active_session"
NOT_IN_DB = "not_in_db"

STALENESS_BUCKETS = (SHA_MATCH, REBUILT, SKIPPED_ACTIVE_SESSION, NOT_IN_DB)


def classify_file(
    *,
    in_db: bool,
    stored_checksum: str | None,
    current_checksum: str | None,
    active_session: bool,
) -> str:
    """Return the staleness bucket for one file.

    Args:
        in_db: True when a project file row exists for this path.
        stored_checksum: ``files.tree_checksum`` from the index (or None).
        current_checksum: SHA-256 of the current on-disk content, or None when
            the file could not be read (treated conservatively as ``rebuilt``).
        active_session: True when an edit session currently holds the file.
    """
    if not in_db:
        return NOT_IN_DB
    if current_checksum is None:
        # Cannot confirm the index is current → do not trust it.
        return SKIPPED_ACTIVE_SESSION if active_session else REBUILT

    decision = ChecksumSyncPolicy.decide(
        tree_file_present=stored_checksum is not None,
        stored_checksum=stored_checksum,
        current_checksum=current_checksum,
        active_session=active_session,
    )
    branch = decision.branch
    if branch == ShaSyncBranch.SHA_MATCH:
        return SHA_MATCH
    if branch == ShaSyncBranch.SHA_MISMATCH_ACTIVE_SESSION:
        return SKIPPED_ACTIVE_SESSION
    # NO_SIDECAR / SHA_MISMATCH_NO_SESSION → the index is stale.
    return REBUILT


def empty_counts() -> dict[str, int]:
    """Zeroed counts dict keyed by every bucket."""
    return {bucket: 0 for bucket in STALENESS_BUCKETS}
