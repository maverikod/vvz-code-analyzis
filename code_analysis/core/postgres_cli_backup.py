"""
PostgreSQL logical backup/restore via client tools (pg_dump / pg_restore / psql).

``pg_dump`` / ``pg_restore`` are **not** Python wheels: install the OS package
(Debian/Ubuntu: ``postgresql-client``) or set ``pg_dump_path`` / ``pg_restore_path``
in ``code_analysis.database.driver.config``. Project docs: ``requirements.txt`` (comment
block) and optional extra ``postgres-backup`` in ``pyproject.toml`` (marker only).

Password from ``password`` or ``password_env`` in ``code_analysis.database.driver.config``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


class PostgresCliBackupError(RuntimeError):
    """Raised when pg_dump / pg_restore / schema reset fails."""


@dataclass(frozen=True)
class PostgresDriverCliConfig:
    """Subset of driver config used for CLI tools."""

    host: str
    port: int
    dbname: str
    user: str
    password: str
    sslmode: Optional[str]
    pg_dump_path: Optional[str]
    pg_restore_path: Optional[str]


def _cfg_str(cfg: Mapping[str, Any], key: str, default: str) -> str:
    v = cfg.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        return default
    return str(v).strip()


def _cfg_int(cfg: Mapping[str, Any], key: str, default: int) -> int:
    v = cfg.get(key, default)
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def resolve_pg_password(driver_cfg: Mapping[str, Any]) -> str:
    """Return password from inline ``password`` or ``os.environ[password_env]``."""
    pw = driver_cfg.get("password")
    if pw is not None and str(pw) != "":
        return str(pw)
    env_name = driver_cfg.get("password_env")
    if env_name:
        v = os.environ.get(str(env_name))
        if v is not None:
            return str(v)
    raise PostgresCliBackupError(
        "PostgreSQL driver config must set `password` or `password_env` "
        "(with the environment variable populated) for backup/restore CLI."
    )


def load_postgres_cli_config(driver_cfg: Mapping[str, Any]) -> PostgresDriverCliConfig:
    """Build CLI config from ``code_analysis.database.driver.config`` mapping."""
    host = _cfg_str(driver_cfg, "host", "127.0.0.1")
    port = _cfg_int(driver_cfg, "port", 5432)
    dbname = _cfg_str(driver_cfg, "dbname", "postgres")
    user = _cfg_str(driver_cfg, "user", "postgres")
    password = resolve_pg_password(driver_cfg)
    sslmode = driver_cfg.get("sslmode")
    sslmode_s = str(sslmode).strip() if sslmode not in (None, "") else None
    dump_p = driver_cfg.get("pg_dump_path")
    rest_p = driver_cfg.get("pg_restore_path")
    return PostgresDriverCliConfig(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        sslmode=sslmode_s,
        pg_dump_path=str(dump_p).strip() if dump_p else None,
        pg_restore_path=str(rest_p).strip() if rest_p else None,
    )


def _pg_subprocess_env(cli: PostgresDriverCliConfig) -> Dict[str, str]:
    env = os.environ.copy()
    env["PGHOST"] = cli.host
    env["PGPORT"] = str(cli.port)
    env["PGUSER"] = cli.user
    env["PGDATABASE"] = cli.dbname
    env["PGPASSWORD"] = cli.password
    if cli.sslmode:
        env["PGSSLMODE"] = cli.sslmode
    return env


def _resolve_binary(preferred: Optional[str], default_name: str) -> str:
    if preferred and Path(preferred).expanduser().is_file():
        return str(Path(preferred).expanduser().resolve())
    path = shutil.which(default_name)
    if path:
        return path
    raise PostgresCliBackupError(
        f"PostgreSQL client `{default_name}` not found in PATH. "
        f"Install postgresql-client or set e.g. `pg_dump_path` in driver config."
    )


def _run_checked(
    argv: Sequence[str],
    *,
    env: Dict[str, str],
    timeout: Optional[float],
    label: str,
) -> None:
    logger.info(
        "Running %s: %s", label, " ".join(argv[:6]) + (" ..." if len(argv) > 6 else "")
    )
    try:
        proc = subprocess.run(
            list(argv),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise PostgresCliBackupError(f"{label} timed out after {timeout}s") from e
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        raise PostgresCliBackupError(f"{label} failed (code {proc.returncode}): {err}")


def backup_postgres_custom_format(
    driver_cfg: Mapping[str, Any],
    *,
    backup_dir: Path,
    timeout_seconds: float = 7200.0,
) -> Tuple[str, ...]:
    """
    Run ``pg_dump -Fc`` into ``backup_dir`` with a timestamped filename.

    Args:
        driver_cfg: ``code_analysis.database.driver.config`` dict.
        backup_dir: Directory for the dump file (created if missing).
        timeout_seconds: Subprocess timeout (large DBs may need more).

    Returns:
        Tuple of one path: the created ``.dump`` file.
    """
    cli = load_postgres_cli_config(driver_cfg)
    backup_root = backup_dir.resolve()
    backup_root.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    out_file = backup_root / f"{cli.dbname}-pgdump-{ts}.dump"
    dump_bin = _resolve_binary(cli.pg_dump_path, "pg_dump")
    env = _pg_subprocess_env(cli)
    argv = [
        dump_bin,
        "-h",
        cli.host,
        "-p",
        str(cli.port),
        "-U",
        cli.user,
        "-d",
        cli.dbname,
        "-Fc",
        "--no-owner",
        "--no-acl",
        "-f",
        str(out_file),
    ]
    _run_checked(argv, env=env, timeout=timeout_seconds, label="pg_dump")
    if not out_file.is_file() or out_file.stat().st_size == 0:
        raise PostgresCliBackupError(f"pg_dump produced no usable file: {out_file}")
    return (str(out_file),)


def restore_postgres_from_custom_dump(
    driver_cfg: Mapping[str, Any],
    dump_path: Path,
    *,
    clean: bool = True,
    timeout_seconds: float = 7200.0,
) -> None:
    """
    Run ``pg_restore`` into the configured database (optionally ``--clean``).

    Args:
        driver_cfg: ``code_analysis.database.driver.config`` dict.
        dump_path: Path to ``-Fc`` archive from :func:`backup_postgres_custom_format`.
        clean: If True, pass ``--clean --if-exists`` (drops objects before restore).
        timeout_seconds: Subprocess timeout.
    """
    if not dump_path.is_file():
        raise PostgresCliBackupError(f"Dump file not found: {dump_path}")
    cli = load_postgres_cli_config(driver_cfg)
    rest_bin = _resolve_binary(cli.pg_restore_path, "pg_restore")
    env = _pg_subprocess_env(cli)
    argv: list[str] = [
        rest_bin,
        "-h",
        cli.host,
        "-p",
        str(cli.port),
        "-U",
        cli.user,
        "-d",
        cli.dbname,
        "--no-owner",
        "--no-acl",
        "-v",
    ]
    if clean:
        argv.extend(["--clean", "--if-exists"])
    argv.append(str(dump_path.resolve()))
    _run_checked(argv, env=env, timeout=timeout_seconds, label="pg_restore")


def reset_postgres_public_schema(driver_cfg: Mapping[str, Any]) -> None:
    """
    Drop and recreate ``public`` schema (empty), same role as SQLite file delete.

    Uses ``psycopg`` (already a dependency for the postgres driver). Connects with
    the same host/db/user/password as CLI tools.
    """
    try:
        import psycopg
    except ImportError as e:
        raise PostgresCliBackupError(
            "psycopg is required for PostgreSQL schema reset. "
            "Install with: pip install 'psycopg[binary]>=3.1'"
        ) from e

    cli = load_postgres_cli_config(driver_cfg)
    try:
        from psycopg.conninfo import make_conninfo

        kw: Dict[str, Any] = {
            "host": cli.host,
            "port": cli.port,
            "dbname": cli.dbname,
            "user": cli.user,
            "password": cli.password,
        }
        if cli.sslmode:
            kw["sslmode"] = cli.sslmode
        conninfo = make_conninfo(**kw)
    except Exception as e:
        raise PostgresCliBackupError(
            f"Invalid PostgreSQL connection params: {e}"
        ) from e
    logger.info(
        "Resetting PostgreSQL schema public on %s:%s db=%s",
        cli.host,
        cli.port,
        cli.dbname,
    )
    try:
        with psycopg.connect(conninfo, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("DROP SCHEMA IF EXISTS public CASCADE")
                cur.execute("CREATE SCHEMA public")
                cur.execute("GRANT ALL ON SCHEMA public TO PUBLIC")
    except Exception as e:
        raise PostgresCliBackupError(f"Failed to reset public schema: {e}") from e
