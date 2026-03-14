"""
Initialize watch directories from config for multi-project file watcher.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, List

from .multi_project_worker_specs import WatchDirSpec

logger = logging.getLogger(__name__)


def initialize_watch_dirs(database: Any, watch_dirs: List[WatchDirSpec]) -> None:
    """
    Initialize watch directories from config.

    Creates/updates watch_dirs and watch_dir_paths, discovers projects
    and creates/updates them with watch_dir_id. Sets NULL paths for
    watch_dirs not found in config or on disk.

    Args:
        database: CodeDatabase instance.
        watch_dirs: List of watch directory specs.
    """
    from ..path_normalization import normalize_path_simple
    from ..project_discovery import discover_projects_in_directory

    logger.info("Initializing watch directories...")

    config_watch_dir_ids = set()
    for spec in watch_dirs:
        watch_dir_id = spec.watch_dir_id
        watch_dir_path = spec.watch_dir.resolve()
        config_watch_dir_ids.add(watch_dir_id)

        database.execute(
            """
            INSERT OR REPLACE INTO watch_dirs (id, name, updated_at)
            VALUES (?, ?, julianday('now'))
            """,
            (watch_dir_id, watch_dir_path.name),
        )

        if watch_dir_path.exists():
            normalized_path = normalize_path_simple(str(watch_dir_path))
            database.execute(
                """
                INSERT OR REPLACE INTO watch_dir_paths (watch_dir_id, absolute_path, updated_at)
                VALUES (?, ?, julianday('now'))
                """,
                (watch_dir_id, normalized_path),
            )
            logger.debug(f"Updated watch_dir_path: {watch_dir_id} -> {normalized_path}")

            try:
                discovered_projects = discover_projects_in_directory(watch_dir_path)
                for project_root_obj in discovered_projects:
                    project_obj = database.get_project(project_root_obj.project_id)
                    if project_obj:
                        if getattr(project_obj, "watch_dir_id", None) != watch_dir_id:
                            database.execute(
                                """
                                UPDATE projects 
                                SET watch_dir_id = ?, updated_at = julianday('now')
                                WHERE id = ?
                                """,
                                (watch_dir_id, project_root_obj.project_id),
                            )
                            logger.debug(
                                f"Updated project {project_root_obj.project_id} "
                                f"watch_dir_id to {watch_dir_id}"
                            )
                    else:
                        project_name = project_root_obj.root_path.name
                        database.execute(
                            """
                            INSERT INTO projects (id, root_path, name, comment, watch_dir_id, updated_at)
                            VALUES (?, ?, ?, ?, ?, julianday('now'))
                            """,
                            (
                                project_root_obj.project_id,
                                str(project_root_obj.root_path),
                                project_name,
                                project_root_obj.description,
                                watch_dir_id,
                            ),
                        )
                        logger.info(
                            f"Created project {project_root_obj.project_id} "
                            f"at {project_root_obj.root_path} "
                            f"with watch_dir_id: {watch_dir_id}"
                        )
            except Exception as e:
                logger.error(
                    f"Error discovering projects in {watch_dir_path}: {e}",
                    exc_info=True,
                )
        else:
            database.execute(
                """
                INSERT OR REPLACE INTO watch_dir_paths (watch_dir_id, absolute_path, updated_at)
                VALUES (?, NULL, julianday('now'))
                """,
                (watch_dir_id,),
            )
            logger.warning(
                f"Watch dir path does not exist: {watch_dir_path}, "
                f"setting NULL for watch_dir_id: {watch_dir_id}"
            )

    all_watch_dirs_result = database.execute(
        "SELECT id FROM watch_dirs",
        None,
    )
    all_watch_dirs_rows = (
        all_watch_dirs_result.get("data", [])
        if isinstance(all_watch_dirs_result, dict)
        else []
    )
    for db_watch_dir in all_watch_dirs_rows:
        db_watch_dir_id = db_watch_dir["id"]
        if db_watch_dir_id not in config_watch_dir_ids:
            database.execute(
                """
                INSERT OR REPLACE INTO watch_dir_paths (watch_dir_id, absolute_path, updated_at)
                VALUES (?, NULL, julianday('now'))
                """,
                (db_watch_dir_id,),
            )
            logger.debug(
                f"Watch dir {db_watch_dir_id} not in config, setting path to NULL"
            )

    logger.info("Watch directories initialization completed")
