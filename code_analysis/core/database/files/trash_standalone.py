"""
File trash via a :class:`~.trash_codedatabase_adapter.TrashSqlDriver` (RPC
:class:`~code_analysis.core.database_driver_pkg.drivers.base.BaseDatabaseDriver` or
CodeDatabase facade).

Ports :mod:`~code_analysis.core.database.files.trash` for use inside the driver RPC
process (no :class:`~code_analysis.core.database.CodeDatabase` wrapper).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from code_analysis.core.sql_portable import (
    WHERE_FILES_TRASHED,
    sql_julian_timestamp_now_expr,
)

from .trash_codedatabase_adapter import TrashSqlDriver
from .trash_standalone_support import (
    clear_file_data_via_driver,
    driver_execute_write,
    driver_fetchall,
    driver_fetchone,
)

logger = logging.getLogger(__name__)


def _database_for_julian_expr(driver: Any) -> Any:
    """Resolve object with ``_driver_type`` (CodeDatabase on TrashCodeDatabaseDriverFacade)."""
    facade_db = getattr(driver, "_db", None)
    if facade_db is not None:
        return facade_db
    return driver


def _get_project_row(
    driver: TrashSqlDriver, project_id: str
) -> Optional[Dict[str, Any]]:
    """Return get project row."""
    return driver_fetchone(driver, "SELECT * FROM projects WHERE id = ?", (project_id,))


def mark_file_deleted_via_driver(
    driver: TrashSqlDriver,
    file_path: str,
    project_id: str,
    version_dir: Optional[str] = None,
    reason: Optional[str] = None,
    trash_dir: Optional[str] = None,
) -> bool:
    """Return mark file deleted via driver."""
    import shutil

    if trash_dir is not None:
        from ...storage_paths import get_file_trash_dir

        file_trash_root = get_file_trash_dir(Path(trash_dir), project_id)
    elif version_dir is not None:
        file_trash_root = Path(version_dir) / project_id
    else:
        logger.error("mark_file_deleted_via_driver: trash_dir or version_dir required")
        return False

    project_root = None
    try:
        db_project = _get_project_row(driver, project_id)
        if db_project:
            project_root = Path(db_project["root_path"])
    except Exception as e:
        logger.debug("Could not get project root from database: %s", e)

    abs_path = None
    if project_root and project_root.exists():
        try:
            from ...path_normalization import normalize_file_path
            from ...exceptions import ProjectIdMismatchError

            candidate_path = (
                str((project_root / file_path).resolve())
                if not Path(file_path).is_absolute()
                else file_path
            )
            normalized = normalize_file_path(candidate_path, project_root=project_root)
            abs_path = normalized.absolute_path

            if normalized.project_id != project_id:
                raise ProjectIdMismatchError(
                    message=(
                        f"Project ID mismatch: file {abs_path} belongs to project "
                        f"{normalized.project_id} (from projectid file) "
                        f"but was provided with project_id {project_id}"
                    ),
                    file_project_id=normalized.project_id,
                    db_project_id=project_id,
                )
        except ProjectIdMismatchError:
            raise
        except FileNotFoundError:
            from ...path_normalization import normalize_path_simple

            if Path(file_path).is_absolute():
                abs_path = normalize_path_simple(file_path)
            else:
                abs_path = normalize_path_simple(project_root / file_path)
        except Exception as e:
            logger.debug("Path normalization failed, simple path: %s", e)
            from ...path_normalization import normalize_path_simple

            if Path(file_path).is_absolute():
                abs_path = normalize_path_simple(file_path)
            elif project_root:
                abs_path = normalize_path_simple(project_root / file_path)
            else:
                abs_path = normalize_path_simple(file_path)
    else:
        from ...path_normalization import normalize_path_simple

        if project_root:
            if Path(file_path).is_absolute():
                abs_path = normalize_path_simple(file_path)
            else:
                abs_path = normalize_path_simple(project_root / file_path)
        else:
            abs_path = normalize_path_simple(file_path)

    row = driver_fetchone(
        driver,
        "SELECT id FROM files WHERE project_id = ? AND path = ?",
        (project_id, abs_path),
    )
    if not row:
        return False

    file_id = row["id"]
    original_path = Path(abs_path)
    _now = sql_julian_timestamp_now_expr(_database_for_julian_expr(driver))

    if not original_path.exists():
        logger.warning("File not found at %s, DB-only delete", file_path)
        driver_execute_write(
            driver,
            f"""
            UPDATE files
            SET deleted = 1, original_path = ?, version_dir = ?, updated_at = {_now}
            WHERE id = ?
            """,
            (str(original_path), str(file_trash_root), file_id),
        )
        return True

    try:
        project_row = driver_fetchone(
            driver, "SELECT root_path FROM projects WHERE id = ?", (project_id,)
        )
        if project_row:
            project_root = Path(project_row["root_path"])
            try:
                relative_path = original_path.relative_to(project_root)
                target_path = file_trash_root / relative_path
            except ValueError:
                import hashlib

                path_hash = hashlib.md5(str(original_path).encode()).hexdigest()[:8]
                target_path = file_trash_root / f"{path_hash}_{original_path.name}"
        else:
            import hashlib

            path_hash = hashlib.md5(str(original_path).encode()).hexdigest()[:8]
            target_path = file_trash_root / f"{path_hash}_{original_path.name}"
    except Exception as e:
        logger.warning("Error calculating relative path: %s, using hash", e)
        import hashlib

        path_hash = hashlib.md5(str(original_path).encode()).hexdigest()[:8]
        target_path = file_trash_root / f"{path_hash}_{original_path.name}"

    try:
        if target_path.exists():
            target_path.unlink()
            logger.debug("Replaced existing file at %s", target_path)
        existing = driver_fetchone(
            driver,
            f"""
            SELECT id, path FROM files
            WHERE project_id = ? AND original_path = ? AND {WHERE_FILES_TRASHED} AND id != ?
            """,
            (project_id, str(original_path), file_id),
        )
        if existing:
            old_path = Path(existing["path"])
            if old_path.exists():
                old_path.unlink()
                logger.debug("Removed previous trashed copy at %s", old_path)
    except Exception as e:
        logger.warning("Replace-if-exists cleanup: %s", e)

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error("Failed to create trash directory %s: %s", target_path.parent, e)
        return False

    try:
        shutil.move(str(original_path), str(target_path))
        logger.info("Moved file from %s to %s", original_path, target_path)
    except Exception as e:
        logger.error(
            "Failed to move file from %s to %s: %s", original_path, target_path, e
        )
        return False

    driver_execute_write(
        driver,
        f"""
        UPDATE files
        SET deleted = 1, original_path = ?, version_dir = ?, path = ?, updated_at = {_now}
        WHERE id = ?
        """,
        (str(original_path), str(file_trash_root), str(target_path), file_id),
    )
    logger.info(
        "Marked file deleted: %s -> %s (reason: %s)",
        file_path,
        target_path,
        reason or "N/A",
    )
    return True


def unmark_file_deleted_via_driver(
    driver: TrashSqlDriver,
    file_path: str,
    project_id: str,
    out_error: Optional[Dict[str, str]] = None,
) -> bool:
    """Return unmark file deleted via driver."""
    import shutil

    from ...path_normalization import normalize_path_simple

    project_root = None
    try:
        db_project = _get_project_row(driver, project_id)
        if db_project:
            root_value = (
                db_project.get("root_path")
                if isinstance(db_project, dict)
                else getattr(db_project, "root_path", None)
            )
            if root_value:
                project_root = Path(str(root_value))
    except Exception:
        project_root = None

    candidate = Path(file_path)
    if project_root and not candidate.is_absolute():
        abs_path = normalize_path_simple(project_root / candidate)
    else:
        abs_path = normalize_path_simple(file_path)
    row = driver_fetchone(
        driver,
        """
        SELECT id, path, original_path, version_dir
        FROM files
        WHERE project_id = ? AND (path = ? OR original_path = ?)
        ORDER BY last_modified DESC
        LIMIT 1
        """,
        (project_id, abs_path, abs_path),
    )
    if not row:
        if out_error is not None:
            out_error["error_code"] = "FILE_NOT_FOUND"
            out_error["message"] = f"File not found: {file_path}"
        return False

    file_id, current_path, original_path_str = (
        row["id"],
        row["path"],
        row["original_path"],
    )

    if not original_path_str:
        if out_error is not None:
            out_error["error_code"] = "NO_ORIGINAL_PATH"
            out_error["message"] = "File has no original_path, cannot restore"
        logger.warning("File %s has no original_path, cannot restore", file_id)
        return False

    original_path = Path(original_path_str)

    if original_path.exists():
        if out_error is not None:
            out_error["error_code"] = "FILE_EXISTS_AT_TARGET"
            out_error["message"] = (
                f"File already exists at {original_path}. "
                "Delete or rename it before restoring."
            )
        logger.warning("Restore skipped: target already exists at %s", original_path)
        return False

    current_path_obj = Path(current_path)

    if not current_path_obj.exists():
        if out_error is not None:
            out_error["error_code"] = "TRASH_FILE_NOT_FOUND"
            out_error["message"] = (
                f"Trash file is missing at {current_path_obj}, cannot restore"
            )
        logger.error("File not found at %s, cannot restore", current_path_obj)
        return False

    try:
        original_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(
            "Failed to create original directory %s: %s", original_path.parent, e
        )
        return False

    try:
        shutil.move(str(current_path_obj), str(original_path))
        logger.info("Moved file from %s back to %s", current_path_obj, original_path)
    except Exception as e:
        logger.error(
            "Failed to move file from %s to %s: %s",
            current_path_obj,
            original_path,
            e,
        )
        return False

    _now = sql_julian_timestamp_now_expr(_database_for_julian_expr(driver))
    driver_execute_write(
        driver,
        f"""
        UPDATE files
        SET deleted = 0, path = ?, original_path = NULL, version_dir = NULL,
            updated_at = {_now}
        WHERE id = ?
        """,
        (str(original_path), file_id),
    )
    logger.info("Unmarked file deleted and restored: %s", original_path)
    return True


def get_deleted_files_via_driver(
    driver: TrashSqlDriver, project_id: str
) -> List[Dict[str, Any]]:
    """Return get deleted files via driver."""
    return cast(
        List[Dict[str, Any]],
        driver_fetchall(
            driver,
            f"""
        SELECT * FROM files
        WHERE project_id = ? AND {WHERE_FILES_TRASHED}
        ORDER BY updated_at DESC
        """,
            (project_id,),
        ),
    )


def hard_delete_file_via_driver(driver: TrashSqlDriver, file_id: str | int) -> None:
    """Return hard delete file via driver."""
    fid = file_id

    row = driver_fetchone(
        driver,
        "SELECT path, version_dir FROM files WHERE id = ?",
        (fid,),
    )
    file_path_str = row["path"] if row else None
    version_dir_val = row["version_dir"] if row else None

    if file_path_str and version_dir_val:
        try:
            file_path_obj = Path(file_path_str)
            if file_path_obj.exists():
                file_path_obj.unlink()
                logger.info("Deleted physical file: %s", file_path_str)
                try:
                    parent = file_path_obj.parent
                    if parent.exists() and not any(parent.iterdir()):
                        parent.rmdir()
                except Exception:
                    pass
        except Exception as e:
            logger.warning("Failed to delete physical file %s: %s", file_path_str, e)

    clear_file_data_via_driver(driver, str(fid))

    driver_execute_write(driver, "DELETE FROM files WHERE id = ?", (fid,))
    logger.info("Hard deleted file ID %s", fid)
