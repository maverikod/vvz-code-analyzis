"""
Tests for SQLite query journal: write, replay, and recovery.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from code_analysis.core.database_driver_pkg.sqlite_query_journal import (
    SQLiteQueryJournal,
    replay_journal,
)


@pytest.fixture
def journal_path(tmp_path: Path) -> Path:
    """Path to a temporary journal file."""
    return tmp_path / "queries.jsonl"


@pytest.fixture
def journal(journal_path: Path) -> SQLiteQueryJournal:
    """Open journal for tests; closed in teardown."""
    j = SQLiteQueryJournal(journal_path)
    yield j
    j.close()


class TestSQLiteQueryJournal:
    """Unit tests for SQLiteQueryJournal."""

    def test_write_success_entry(
        self, journal: SQLiteQueryJournal, journal_path: Path
    ) -> None:
        """Write a successful entry and check file content."""
        journal.write("INSERT INTO t (a) VALUES (?)", params=(1,), success=True)
        journal.close()
        lines = journal_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["sql"] == "INSERT INTO t (a) VALUES (?)"
        assert entry["params"] == [1]
        assert entry["success"] is True
        assert "ts" in entry

    def test_write_with_dict_params(
        self, journal: SQLiteQueryJournal, journal_path: Path
    ) -> None:
        """Write entry with named params."""
        journal.write(
            "UPDATE t SET a = :val WHERE id = :id",
            params={"val": 2, "id": 1},
            success=True,
        )
        journal.close()
        entry = json.loads(journal_path.read_text(encoding="utf-8").strip())
        assert entry["params"] == {"val": 2, "id": 1}

    def test_write_failure_entry(
        self, journal: SQLiteQueryJournal, journal_path: Path
    ) -> None:
        """Write a failed entry with error message."""
        journal.write(
            "DELETE FROM missing_table",
            success=False,
            error="no such table: missing_table",
        )
        journal.close()
        entry = json.loads(journal_path.read_text(encoding="utf-8").strip())
        assert entry["success"] is False
        assert "no such table" in entry["error"]

    def test_write_after_close_is_noop(
        self, journal: SQLiteQueryJournal, journal_path: Path
    ) -> None:
        """Writing after close does not raise and does not write."""
        journal.write("SELECT 1", success=True)
        journal.close()
        journal.write("SELECT 2", success=True)
        lines = journal_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1

    def test_path_property(
        self, journal: SQLiteQueryJournal, journal_path: Path
    ) -> None:
        """path property returns resolved Path."""
        assert journal.path == journal_path.resolve()

    def test_multiple_entries(
        self, journal: SQLiteQueryJournal, journal_path: Path
    ) -> None:
        """Multiple writes produce multiple lines."""
        for i in range(3):
            journal.write("INSERT INTO t VALUES (?)", params=(i,), success=True)
        journal.close()
        lines = [
            ln
            for ln in journal_path.read_text(encoding="utf-8").split("\n")
            if ln.strip()
        ]
        assert len(lines) == 3

    def test_rotation_when_over_max_bytes(self, tmp_path: Path) -> None:
        """When file reaches max_bytes, it is rotated to .1 and new file is opened."""
        journal_path = tmp_path / "rot.jsonl"
        j = SQLiteQueryJournal(journal_path, max_bytes=200, backup_count=2)
        long_sql = "INSERT INTO t VALUES (" + ",".join("?" * 50) + ")"
        params = list(range(50))
        for _ in range(10):
            j.write(long_sql, params=params, success=True)
        j.close()
        if journal_path.exists():
            assert journal_path.stat().st_size < 400
        rot1 = Path(str(journal_path) + ".1")
        assert rot1.exists()
        lines_in_rot1 = [
            ln for ln in rot1.read_text(encoding="utf-8").split("\n") if ln.strip()
        ]
        assert len(lines_in_rot1) >= 1


class TestReplayJournal:
    """Unit tests for replay_journal."""

    def test_replay_missing_file(self, tmp_path: Path) -> None:
        """Replay on missing file returns error."""
        result = replay_journal(tmp_path / "nonexistent.jsonl", lambda s, p: None)
        assert result["replayed"] == 0
        assert result["failed"] == 0
        assert "Journal file not found" in result["errors"]

    def test_replay_only_success(self, journal_path: Path) -> None:
        """only_success=True skips failed entries."""
        with open(journal_path, "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": "2026-01-01T00:00:00Z",
                        "sql": "SELECT 1",
                        "params": None,
                        "success": True,
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "ts": "2026-01-01T00:00:01Z",
                        "sql": "SELECT 2",
                        "params": None,
                        "success": False,
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "ts": "2026-01-01T00:00:02Z",
                        "sql": "SELECT 3",
                        "params": None,
                        "success": True,
                    }
                )
                + "\n"
            )
        executed: list = []

        def capture(sql: str, params) -> None:
            executed.append((sql, params))

        result = replay_journal(journal_path, capture, only_success=True)
        assert result["replayed"] == 2
        assert result["failed"] == 0
        assert len(executed) == 2
        assert executed[0][0] == "SELECT 1"
        assert executed[1][0] == "SELECT 3"

    def test_replay_limit(self, journal_path: Path) -> None:
        """limit caps number of replayed entries."""
        with open(journal_path, "w", encoding="utf-8") as f:
            for i in range(5):
                f.write(
                    json.dumps(
                        {
                            "ts": "2026-01-01Z",
                            "sql": f"SELECT {i}",
                            "params": None,
                            "success": True,
                        }
                    )
                    + "\n"
                )
        executed: list = []
        replay_journal(
            journal_path,
            lambda s, p: executed.append((s, p)),
            only_success=True,
            limit=2,
        )
        assert len(executed) == 2

    def test_replay_invalid_json(self, journal_path: Path) -> None:
        """Invalid JSON line increments failed and is recorded in errors."""
        with open(journal_path, "w", encoding="utf-8") as f:
            f.write('{"sql": "SELECT 1", "success": true}\n')
            f.write("not json\n")
            f.write('{"sql": "SELECT 2", "success": true}\n')
        executed: list = []
        result = replay_journal(
            journal_path, lambda s, p: executed.append((s, p)), only_success=True
        )
        assert result["replayed"] == 2
        assert result["failed"] == 1
        assert any("Invalid JSON" in e for e in result["errors"])

    def test_replay_missing_sql(self, journal_path: Path) -> None:
        """Entry without sql is skipped and counted as failed."""
        with open(journal_path, "w", encoding="utf-8") as f:
            f.write(
                json.dumps({"ts": "2026-01-01Z", "params": [], "success": True}) + "\n"
            )
        result = replay_journal(journal_path, lambda s, p: None, only_success=True)
        assert result["replayed"] == 0
        assert result["failed"] == 1
        assert any("Missing sql" in e for e in result["errors"])

    def test_replay_execute_raises(self, journal_path: Path) -> None:
        """When execute_fn raises, failed is incremented and error is recorded."""
        with open(journal_path, "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": "Z",
                        "sql": "INSERT INTO t VALUES (1)",
                        "params": None,
                        "success": True,
                    }
                )
                + "\n"
            )

        def raise_on_insert(sql: str, params) -> None:
            if "INSERT" in sql:
                raise RuntimeError("table locked")

        result = replay_journal(journal_path, raise_on_insert, only_success=True)
        assert result["replayed"] == 0
        assert result["failed"] == 1
        assert any("table locked" in e for e in result["errors"])


class TestRecovery:
    """Recovery: write operations to journal, replay into another DB, verify data."""

    def test_recovery_replay_writes_into_empty_db(
        self,
        tmp_path: Path,
    ) -> None:
        """Record writes in a journal, then replay into a new DB and verify data."""
        journal_path = tmp_path / "queries.jsonl"
        db_primary = tmp_path / "primary.db"
        db_restored = tmp_path / "restored.db"

        # Create primary DB and table, run writes, and record them in journal
        conn_primary = sqlite3.connect(str(db_primary))
        conn_primary.execute("CREATE TABLE data (id INTEGER PRIMARY KEY, value TEXT)")
        conn_primary.commit()

        journal = SQLiteQueryJournal(journal_path)
        # Simulate what the driver would log: each execute and its params
        journal.write(
            "INSERT INTO data (id, value) VALUES (?, ?)",
            params=(1, "one"),
            success=True,
        )
        journal.write(
            "INSERT INTO data (id, value) VALUES (?, ?)",
            params=(2, "two"),
            success=True,
        )
        journal.write(
            "UPDATE data SET value = ? WHERE id = ?",
            params=("ONE", 1),
            success=True,
        )
        journal.close()
        conn_primary.close()

        # Create restored DB with same schema (empty)
        conn_restored = sqlite3.connect(str(db_restored))
        conn_restored.execute("CREATE TABLE data (id INTEGER PRIMARY KEY, value TEXT)")
        conn_restored.commit()

        def execute_into_restored(sql: str, params) -> None:
            if params is None:
                conn_restored.execute(sql)
            else:
                conn_restored.execute(sql, params)
            conn_restored.commit()

        result = replay_journal(journal_path, execute_into_restored, only_success=True)
        assert result["failed"] == 0
        assert result["replayed"] == 3

        # Verify restored data
        rows = conn_restored.execute(
            "SELECT id, value FROM data ORDER BY id"
        ).fetchall()
        conn_restored.close()
        assert rows == [(1, "ONE"), (2, "two")]

    def test_recovery_skips_failed_entries(
        self,
        tmp_path: Path,
    ) -> None:
        """Replay with only_success=True skips failed entries; only successful writes applied."""
        journal_path = tmp_path / "queries.jsonl"
        with open(journal_path, "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": "2026-01-01Z",
                        "sql": "INSERT INTO t (id) VALUES (?)",
                        "params": [1],
                        "success": True,
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "ts": "2026-01-01Z",
                        "sql": "INSERT INTO t (id) VALUES (?)",
                        "params": [2],
                        "success": False,
                        "error": "duplicate",
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "ts": "2026-01-01Z",
                        "sql": "INSERT INTO t (id) VALUES (?)",
                        "params": [3],
                        "success": True,
                    }
                )
                + "\n"
            )

        db_path = tmp_path / "restored.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        conn.commit()

        def run(sql: str, params) -> None:
            if params is None:
                conn.execute(sql)
            else:
                conn.execute(sql, tuple(params))
            conn.commit()

        result = replay_journal(journal_path, run, only_success=True)
        conn.close()
        assert result["replayed"] == 2
        assert result["failed"] == 0
        rows = (
            sqlite3.connect(str(db_path))
            .execute("SELECT id FROM t ORDER BY id")
            .fetchall()
        )
        assert [r[0] for r in rows] == [1, 3]

    def test_driver_writes_journal_and_replay_restores(
        self,
        tmp_path: Path,
    ) -> None:
        """Integration: driver with query_log_path writes to journal; replay restores into new DB."""
        db_path = tmp_path / "source.db"
        journal_path = tmp_path / "driver_queries.jsonl"
        restored_path = tmp_path / "restored.db"

        from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver

        driver = SQLiteDriver()
        driver.connect(
            {
                "path": str(db_path),
                "query_log_path": str(journal_path),
            }
        )

        # Create table and run writes (these get logged)
        driver.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
        driver.execute("INSERT INTO items (id, name) VALUES (?, ?)", (1, "a"))
        driver.execute("INSERT INTO items (id, name) VALUES (?, ?)", (2, "b"))
        driver.execute("UPDATE items SET name = ? WHERE id = ?", ("A", 1))

        driver.disconnect()

        # Ensure journal was written
        assert journal_path.exists()
        lines = [
            ln
            for ln in journal_path.read_text(encoding="utf-8").split("\n")
            if ln.strip()
        ]
        assert (
            len(lines) >= 4
        )  # CREATE + 2 INSERT + UPDATE (and possibly internal driver ops)

        # Restored DB: same schema, then replay only INSERT/UPDATE (skip CREATE if we filter, or include all)
        conn = sqlite3.connect(str(restored_path))
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
        conn.commit()

        replayed_count = 0

        def run(sql: str, params) -> None:
            nonlocal replayed_count
            # Replay only data-modifying statements (driver may log CREATE and other internal SQL)
            if "INSERT INTO items" in sql or "UPDATE items" in sql:
                if params is None:
                    conn.execute(sql)
                else:
                    conn.execute(
                        sql, tuple(params) if isinstance(params, list) else params
                    )
                conn.commit()
                replayed_count += 1

        result = replay_journal(journal_path, run, only_success=True)
        conn.close()
        assert replayed_count == 3
        assert result["failed"] == 0
        rows = (
            sqlite3.connect(str(restored_path))
            .execute("SELECT id, name FROM items ORDER BY id")
            .fetchall()
        )
        assert rows == [(1, "A"), (2, "b")]
