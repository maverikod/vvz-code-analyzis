"""
Regression tests for query_cst write rollback path.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path

import pytest

from code_analysis.commands.query_cst_handler import _write_replace_result_atomically
from tests.test_query_cst.helpers import assert_error_result

SOURCE_CODE = '"""module"""\n\n\ndef add(a: int, b: int) -> int:\n    return a + b\n'
NEW_SOURCE_CODE = (
    '"""module"""\n\n\ndef add(a: int, b: int) -> int:\n    return a + b + 1\n'
)


class FakeDatabaseFailure:
    """Represent FakeDatabaseFailure."""

    def __init__(self) -> None:
        """Initialize the instance."""
        self.disconnected = False

    def index_file(self, file_path: str, project_id: str):
        """Return index file."""
        return {"success": False, "error": "forced index failure"}

    def disconnect(self) -> None:
        """Return disconnect."""
        self.disconnected = True


class FakeDatabaseException:
    """Represent FakeDatabaseException."""

    def __init__(self) -> None:
        """Initialize the instance."""
        self.disconnected = False

    def index_file(self, file_path: str, project_id: str):
        """Return index file."""
        raise RuntimeError("forced index exception")

    def disconnect(self) -> None:
        """Return disconnect."""
        self.disconnected = True


class FakeCommand:
    """Represent FakeCommand."""

    def __init__(self, database) -> None:
        """Initialize the instance."""
        self._database = database

    def _open_database_from_config(self, auto_analyze: bool = False):
        """Return open database from config."""
        return self._database


@pytest.mark.parametrize(
    ("database", "expected_db_error"),
    [
        (FakeDatabaseFailure(), "forced index failure"),
        (FakeDatabaseException(), "forced index exception"),
    ],
)
def test_write_replace_rolls_back_file_on_index_errors(
    tmp_path: Path, database, expected_db_error: str
):
    """Verify test write replace rolls back file on index errors."""
    target = tmp_path / "sample.py"
    target.write_text(SOURCE_CODE, encoding="utf-8")

    command = FakeCommand(database)
    backup_uuid, error = _write_replace_result_atomically(
        command=command,
        root_path=tmp_path,
        target=target,
        new_source=NEW_SOURCE_CODE,
        project_id="test-proj",
    )

    assert_error_result(error)
    assert error.code == "CST_QUERY_ERROR"
    assert expected_db_error in (error.details or {}).get("db_error", "")
    assert isinstance(backup_uuid, str) and backup_uuid
    assert target.read_text(encoding="utf-8") == SOURCE_CODE
    assert not (tmp_path / "sample.py.tmp").exists()
    assert database.disconnected is True
