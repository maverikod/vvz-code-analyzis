"""
UUID migration for projects table (schema_creation split).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def run_migrate_to_uuid_projects(db: Any) -> None:
    """Migrate projects table from INTEGER to UUID4 if needed."""
    table_info = db._get_table_info("projects")
    columns = {col["name"]: col["type"] for col in table_info}
    if "id" in columns and columns["id"] == "INTEGER":
        logger.info("Migrating projects table to UUID4...")
        db._execute(
            """
            CREATE TABLE IF NOT EXISTS projects_new (
                id TEXT PRIMARY KEY,
                root_path TEXT UNIQUE NOT NULL,
                name TEXT,
                comment TEXT,
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now'))
            )
        """
        )
        old_projects = db._fetchall(
            "SELECT id, root_path, name, created_at, updated_at FROM projects"
        )
        for row in old_projects:
            old_id = row["id"]
            root_path = row["root_path"]
            name = row["name"]
            created_at = row["created_at"]
            updated_at = row["updated_at"]
            new_id = str(uuid.uuid4())
            db._execute(
                """
                INSERT INTO projects_new (
                    id, root_path, name, comment, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    new_id,
                    root_path,
                    name,
                    f"Migrated from project_id {old_id}",
                    created_at,
                    updated_at,
                ),
            )
            db._execute(
                "UPDATE files SET project_id = ? WHERE project_id = ?",
                (new_id, old_id),
            )
        db._execute("DROP TABLE projects")
        db._execute("ALTER TABLE projects_new RENAME TO projects")
        db._execute("PRAGMA foreign_keys = OFF")
        db._execute(
            """
            CREATE TABLE IF NOT EXISTS files_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                path TEXT NOT NULL,
                lines INTEGER,
                last_modified REAL,
                has_docstring BOOLEAN,
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(project_id, path)
            )
        """
        )
        db._execute(
            """
            INSERT INTO files_new (id, project_id, path, lines, last_modified, has_docstring, created_at, updated_at)
            SELECT id, project_id, path, lines, last_modified, has_docstring, created_at, updated_at FROM files
            """
        )
        db._execute("DROP TABLE files")
        db._execute("ALTER TABLE files_new RENAME TO files")
        db._execute("PRAGMA foreign_keys = ON")
        db._commit()
        logger.info("Migration to UUID4 completed")
    if "comment" not in columns:
        try:
            db._execute("ALTER TABLE projects ADD COLUMN comment TEXT")
            db._commit()
        except Exception:
            pass
