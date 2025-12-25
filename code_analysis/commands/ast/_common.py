"""
Shared helpers for MCP AST command wrappers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Optional

from ...core.database import CodeDatabase

logger = logging.getLogger(__name__)


def open_database(root_dir: str) -> CodeDatabase:
    root_path = Path(root_dir).resolve()
    data_dir = root_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "code_analysis.db"
    return CodeDatabase(db_path)


def get_project_id(
    db: CodeDatabase, root_dir: Path, project_id: Optional[str]
) -> Optional[str]:
    if project_id:
        project = db.get_project(project_id)
        return project_id if project else None
    return db.get_or_create_project(str(root_dir), name=root_dir.name)
