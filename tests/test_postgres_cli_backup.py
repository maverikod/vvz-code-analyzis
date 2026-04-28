"""Tests for postgres_cli_backup helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.postgres_cli_backup import (
    PostgresCliBackupError,
    backup_postgres_custom_format,
    load_postgres_cli_config,
    reset_postgres_public_schema,
)


def test_load_postgres_cli_config_requires_password() -> None:
    with pytest.raises(PostgresCliBackupError, match="password"):
        load_postgres_cli_config(
            {
                "host": "h",
                "port": 5432,
                "dbname": "d",
                "user": "u",
            }
        )


def test_backup_postgres_custom_format_success(tmp_path: Path) -> None:
    driver_cfg = {
        "host": "127.0.0.1",
        "port": 5432,
        "dbname": "appdb",
        "user": "u",
        "password": "secret",
    }

    def fake_run(
        argv, env=None, capture_output=False, text=False, timeout=None, check=False
    ):
        out_idx = list(argv).index("-f") + 1
        Path(argv[out_idx]).write_bytes(b"PGDMP")
        m = MagicMock()
        m.returncode = 0
        m.stderr = ""
        m.stdout = ""
        return m

    with patch(
        "code_analysis.core.postgres_cli_backup.shutil.which",
        return_value="/bin/pg_dump",
    ):
        with patch(
            "code_analysis.core.postgres_cli_backup.subprocess.run",
            side_effect=fake_run,
        ):
            paths = backup_postgres_custom_format(driver_cfg, backup_dir=tmp_path)
    assert len(paths) == 1
    assert paths[0].endswith(".dump")
    assert Path(paths[0]).is_file()


def test_reset_postgres_public_schema_uses_psycopg() -> None:
    pytest.importorskip("psycopg")
    import psycopg

    driver_cfg = {
        "host": "127.0.0.1",
        "port": 5432,
        "dbname": "d",
        "user": "u",
        "password": "p",
    }
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_conn.cursor.return_value.__exit__.return_value = None
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    mock_ctx.__exit__.return_value = None

    with patch.object(psycopg, "connect", return_value=mock_ctx):
        reset_postgres_public_schema(driver_cfg)

    assert mock_cur.execute.call_count == 3
