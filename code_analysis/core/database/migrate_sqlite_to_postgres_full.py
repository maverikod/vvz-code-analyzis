"""
Полный перенос SQLite → PostgreSQL: опционально CREATE DATABASE, сброс public,
копирование схемы и данных, сверка числа строк.

FAISS-индексы (*.bin в data/) остаются на диске; при том же каталоге data/ сервер
продолжит их использовать после переключения config на postgres.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def reset_public_schema(conn: Any) -> None:
    """DROP SCHEMA public CASCADE; CREATE SCHEMA public; права по умолчанию."""
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS public CASCADE")
            cur.execute("CREATE SCHEMA public")
            cur.execute("GRANT ALL ON SCHEMA public TO CURRENT_USER")
            cur.execute("GRANT ALL ON SCHEMA public TO public")
    finally:
        conn.autocommit = False


def create_database_if_not_exists(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    new_dbname: str,
    maintenance_dbname: str = "postgres",
) -> bool:
    """
    Создать базу new_dbname, если её ещё нет (подключение к maintenance_dbname).

    Returns:
        True если CREATE DATABASE выполнен, False если база уже была.
    """
    import psycopg
    from psycopg import sql

    conn = psycopg.connect(
        host=host,
        port=port,
        dbname=maintenance_dbname,
        user=user,
        password=password,
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (new_dbname,),
            )
            if cur.fetchone():
                return False
            try:
                cur.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(new_dbname))
                )
            except Exception as e:
                if getattr(e, "pgcode", None) == "42P04":  # duplicate_database
                    return False
                raise
        return True
    finally:
        conn.close()


def _connect_from_params(
    *,
    dsn: Optional[str],
    host: str,
    port: int,
    dbname: str,
    user: str,
    password: str,
):
    """Return connect from params."""
    import psycopg

    if dsn:
        return psycopg.connect(conninfo=dsn)
    return psycopg.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
    )


def verify_row_counts(
    sqlite_path: Path,
    pg_conn: Any,
    schema_definition: Dict[str, Any],
) -> Dict[str, Any]:
    """Сравнить число строк по таблицам (SQLite vs PostgreSQL)."""
    from .schema_sync_sql import tables_recreate_order
    from .sqlite_to_postgres import sqlite_code_chunks_expected_row_count_for_postgres

    sl = sqlite3.connect(str(sqlite_path))
    try:
        schema_tables = set(schema_definition["tables"].keys())
        cur = sl.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        sqlite_tables = {str(r[0]) for r in cur.fetchall()}
        names = schema_tables & sqlite_tables
        ordered = tables_recreate_order(schema_definition, names)
        vt = {v["name"] for v in schema_definition.get("virtual_tables", [])}
        ordered = [t for t in ordered if t not in vt]

        mismatches: List[Dict[str, Any]] = []
        checked: Dict[str, Dict[str, int]] = {}

        with pg_conn.cursor() as pg_cur:
            for table in ordered:
                try:
                    n_sl_raw = sl.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                except sqlite3.Error as e:
                    mismatches.append({"table": table, "error_sqlite": str(e)})
                    continue
                if table == "code_chunks":
                    n_sl = sqlite_code_chunks_expected_row_count_for_postgres(sl)
                else:
                    n_sl = int(n_sl_raw)
                try:
                    pg_cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                    n_pg = pg_cur.fetchone()[0]
                except Exception as e:
                    mismatches.append({"table": table, "error_postgres": str(e)})
                    continue
                entry: Dict[str, Any] = {"sqlite": int(n_sl), "postgres": int(n_pg)}
                if table == "code_chunks" and int(n_sl_raw) != int(n_sl):
                    entry["sqlite_source_rows"] = int(n_sl_raw)
                checked[table] = entry
                if int(n_sl) != int(n_pg):
                    mm: Dict[str, Any] = {
                        "table": table,
                        "sqlite": int(n_sl),
                        "postgres": int(n_pg),
                    }
                    if table == "code_chunks":
                        mm["sqlite_source_rows"] = int(n_sl_raw)
                    mismatches.append(mm)

        return {
            "ok": len(mismatches) == 0,
            "tables_checked": len(checked),
            "counts": checked,
            "mismatches": mismatches,
        }
    finally:
        sl.close()


def run_full_migration(
    sqlite_path: str | Path,
    *,
    dsn: Optional[str] = None,
    host: str = "127.0.0.1",
    port: int = 5432,
    dbname: str = "postgres",
    user: str = "postgres",
    password: str = "",
    create_database: bool = False,
    reset_target_schema: bool = False,
    schema_only: bool = False,
    verify: bool = True,
    maintenance_dbname: str = "postgres",
) -> Dict[str, Any]:
    """
    Полный сценарий: при необходимости CREATE DATABASE, сброс схемы, migrate_sqlite_to_postgresql, verify.

    При ``create_database=True`` параметры host/port/user/password используются
    (не поддерживается вместе с произвольным ``dsn`` — задайте только dsn и целевой db в URI).
    """
    from .schema_definition import get_schema_definition
    from .sqlite_to_postgres import migrate_sqlite_to_postgresql

    sqlite_path = Path(sqlite_path).resolve()
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"SQLite file not found: {sqlite_path}")

    schema_definition = get_schema_definition()
    result: Dict[str, Any] = {
        "sqlite_path": str(sqlite_path),
        "target": {
            "dsn_set": bool(dsn),
            "host": host,
            "port": port,
            "dbname": dbname,
        },
        "create_database_ran": False,
        "reset_schema_ran": False,
        "migration": {},
        "verification": None,
    }

    if create_database:
        if dsn:
            raise ValueError(
                "create_database is not supported together with --dsn; "
                "use --host/--port/--user/--password/--dbname or create DB manually."
            )
        created = create_database_if_not_exists(
            host=host,
            port=port,
            user=user,
            password=password,
            new_dbname=dbname,
            maintenance_dbname=maintenance_dbname,
        )
        result["create_database_ran"] = created
        logger.info(
            "CREATE DATABASE %s: %s",
            dbname,
            "created" if created else "already existed",
        )

    conn = _connect_from_params(
        dsn=dsn,
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
    )
    conn.autocommit = False
    try:
        if reset_target_schema:
            logger.info("Resetting public schema in database %s", dbname)
            reset_public_schema(conn)
            result["reset_schema_ran"] = True

        summary = migrate_sqlite_to_postgresql(
            sqlite_path,
            conn,
            schema_definition=schema_definition,
            create_schema=True,
            copy_data=not schema_only,
        )
        result["migration"] = summary

        if verify and not schema_only:
            result["verification"] = verify_row_counts(
                sqlite_path, conn, schema_definition
            )
            if not result["verification"].get("ok"):
                logger.warning(
                    "Row count verification found mismatches: %s",
                    result["verification"].get("mismatches"),
                )

        return result
    finally:
        conn.close()
