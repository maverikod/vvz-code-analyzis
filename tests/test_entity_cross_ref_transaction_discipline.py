"""
Regression: entity_cross_ref.py writers must not commit mid-transaction
(root cause of entity_cross_ref rows being absent on a PostgreSQL-backed
deployment - live verification on 1.6.61, database_driver=postgres).

``add_entity_cross_ref`` (and ``delete_entity_cross_ref_for_file``) called
``self._commit()`` unconditionally, unlike every sibling writer in
``entities.py`` (``add_class``/``add_method``/``add_function``/``add_usage``),
which all guard with ``if not self._in_transaction(): self._commit()``.
``entity_cross_ref_builder.build_entity_cross_ref_for_file`` (and therefore
``add_entity_cross_ref``) always runs mid-transaction, from
``update_file_data_atomic`` ("must be called within an active transaction").
An unconditional commit there ends that outer transaction early without
resetting ``_transaction_active``, corrupting the transaction boundary for
the rest of the atomic file update.

This was invisible on SQLite: the in-process test facade's ``_commit()`` is
an unconditional no-op (``tests/sqlite_in_process_legacy_facade.py``, see
``SqliteLegacyRpcFacade._commit``), so no test using that facade can ever
observe whether a real commit happened. On PostgreSQL, ``CodeDatabase._commit()``
detects ``hasattr(self.driver, "commit")`` (true for ``PostgreSQLDriver``) and
calls ``driver.commit()`` -> ``self.conn.commit()``, a REAL commit. This test
therefore uses a lightweight commit-tracking stub instead of the sqlite
facade, so it actually exercises the "did commit() get called" question the
sqlite layer structurally cannot answer.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import uuid

import pytest

from code_analysis.core.database.entity_cross_ref import (
    add_entity_cross_ref,
    delete_entity_cross_ref_for_file,
)


class _CommitTrackingDB:
    """Minimal stand-in exposing exactly the leaf-writer contract
    (``_execute``/``_commit``/``_lastrowid``/``_fetchall``/``_in_transaction``),
    tracking whether ``_commit()`` was called - independent of any real driver.
    """

    def __init__(self, transaction_active: bool) -> None:
        """Initialize the instance."""
        self._transaction_active = transaction_active
        self.commit_calls = 0
        self.executed: list = []
        self._fetchall_result: list = []

    def _execute(self, sql, params=None) -> None:
        """Record the statement; no real DB behind this stub."""
        self.executed.append((sql, params))

    def _commit(self) -> None:
        """Track calls instead of touching a real connection."""
        self.commit_calls += 1

    def _lastrowid(self):
        """Return a fixed id; only call-count of _commit matters here."""
        return str(uuid.uuid4())

    def _fetchall(self, sql, params=None):
        """Return the configured fetch result (used by the DELETE lookups)."""
        return self._fetchall_result

    def _in_transaction(self) -> bool:
        """Same contract as CodeDatabase._in_transaction()."""
        return self._transaction_active


def _valid_kwargs(**overrides):
    """Return a valid add_entity_cross_ref kwargs set (one caller, one callee)."""
    base = dict(
        caller_class_id=str(uuid.uuid4()),
        caller_method_id=None,
        caller_function_id=None,
        callee_class_id=str(uuid.uuid4()),
        callee_method_id=None,
        callee_function_id=None,
        ref_type="inherit",
        file_id=str(uuid.uuid4()),
        line=1,
    )
    base.update(overrides)
    return base


def test_add_entity_cross_ref_does_not_commit_inside_active_transaction():
    """Mid-transaction (the real call pattern from build_entity_cross_ref_for_file /
    update_file_data_atomic): must NOT commit - that would end the enclosing
    atomic transaction early. This is the exact defect that made entity_cross_ref
    rows disappear on PostgreSQL."""
    db = _CommitTrackingDB(transaction_active=True)

    result = add_entity_cross_ref(db, **_valid_kwargs())

    assert result is not None
    assert db.commit_calls == 0, (
        "add_entity_cross_ref committed while _in_transaction() is True - this "
        "prematurely ends the enclosing atomic transaction on a real driver "
        "(PostgreSQL); it was only invisible because the sqlite test facade's "
        "_commit() is an unconditional no-op"
    )


def test_add_entity_cross_ref_commits_when_standalone():
    """Outside any transaction (a standalone call), it MUST still commit -
    same contract as add_class/add_method/add_function/add_usage."""
    db = _CommitTrackingDB(transaction_active=False)

    add_entity_cross_ref(db, **_valid_kwargs())

    assert db.commit_calls == 1


def test_delete_entity_cross_ref_for_file_does_not_commit_inside_transaction():
    """Same transaction-discipline bug, same fix, in the DELETE path."""
    db = _CommitTrackingDB(transaction_active=True)

    # file_id's declared type is int (legacy pre-UUID-migration signature); the
    # real runtime id can be a UUID string post-migration, but this test only
    # exercises commit discipline, not id typing, so use a plain int here.
    delete_entity_cross_ref_for_file(db, 1)

    assert db.commit_calls == 0


def test_delete_entity_cross_ref_for_file_commits_when_standalone():
    """Standalone call still commits."""
    db = _CommitTrackingDB(transaction_active=False)

    # file_id's declared type is int (legacy pre-UUID-migration signature); the
    # real runtime id can be a UUID string post-migration, but this test only
    # exercises commit discipline, not id typing, so use a plain int here.
    delete_entity_cross_ref_for_file(db, 1)

    assert db.commit_calls == 1
