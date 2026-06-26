"""
Unit tests for the analyze_tree checksum staleness gate (R2).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.commands.analyze_tree import staleness as st


def test_sha_match_when_checksums_equal():
    """Verify test sha match when checksums equal."""
    assert (
        st.classify_file(
            in_db=True,
            stored_checksum="abc",
            current_checksum="abc",
            active_session=False,
        )
        == st.SHA_MATCH
    )


def test_mismatch_no_session_is_rebuilt():
    # R2: diverging disk checksum from tree_checksum moves the file to `rebuilt`.
    """Verify test mismatch no session is rebuilt."""
    assert (
        st.classify_file(
            in_db=True,
            stored_checksum="abc",
            current_checksum="DIFFERENT",
            active_session=False,
        )
        == st.REBUILT
    )


def test_mismatch_active_session_is_skipped():
    """Verify test mismatch active session is skipped."""
    assert (
        st.classify_file(
            in_db=True,
            stored_checksum="abc",
            current_checksum="DIFFERENT",
            active_session=True,
        )
        == st.SKIPPED_ACTIVE_SESSION
    )


def test_no_stored_checksum_is_rebuilt():
    """Verify test no stored checksum is rebuilt."""
    assert (
        st.classify_file(
            in_db=True,
            stored_checksum=None,
            current_checksum="abc",
            active_session=False,
        )
        == st.REBUILT
    )


def test_not_in_db():
    """Verify test not in db."""
    assert (
        st.classify_file(
            in_db=False,
            stored_checksum=None,
            current_checksum="abc",
            active_session=False,
        )
        == st.NOT_IN_DB
    )


def test_unreadable_content_conservative():
    # Cannot confirm the index is current → not sha_match.
    """Verify test unreadable content conservative."""
    assert (
        st.classify_file(
            in_db=True,
            stored_checksum="abc",
            current_checksum=None,
            active_session=False,
        )
        == st.REBUILT
    )


def test_empty_counts_has_all_buckets():
    """Verify test empty counts has all buckets."""
    counts = st.empty_counts()
    assert set(counts) == set(st.STALENESS_BUCKETS)
    assert all(v == 0 for v in counts.values())
