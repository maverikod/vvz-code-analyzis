"""
Module datasets.

This module provides functions for managing datasets table.
Datasets support multi-root indexing within a project.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional

from ..project_resolution import normalize_root_dir

logger = logging.getLogger(__name__)


def get_or_create_dataset(
    self, project_id: str, root_path: str, name: Optional[str] = None
) -> str:
    """
    Get or create dataset by project_id and root_path.

    Datasets support multi-root indexing within a project.
    Each dataset represents a separate indexed root directory.

    Args:
        project_id: Project ID (UUID4 string)
        root_path: Root directory path (will be normalized to absolute)
        name: Optional dataset name

    Returns:
        Dataset ID (UUID4 string)
    """
    # Normalize root_path to absolute resolved path
    normalized_root = str(normalize_root_dir(root_path))

    # Check if dataset exists
    existing = self._fetchone(
        "SELECT id FROM datasets WHERE project_id = ? AND root_path = ?",
        (project_id, normalized_root),
    )
    if existing:
        return existing["id"]

    # Create new dataset
    dataset_id = str(uuid.uuid4())
    dataset_name = name or Path(normalized_root).name
    self._execute(
        """
        INSERT INTO datasets (id, project_id, root_path, name, updated_at)
        VALUES (?, ?, ?, ?, julianday('now'))
        """,
        (dataset_id, project_id, normalized_root, dataset_name),
    )
    self._commit()
    logger.info(
        f"Created dataset {dataset_id} for project {project_id} at {normalized_root}"
    )
    return dataset_id


def get_dataset_id(self, project_id: str, root_path: str) -> Optional[str]:
    """
    Get dataset ID by project_id and root_path.

    Args:
        project_id: Project ID (UUID4 string)
        root_path: Root directory path (will be normalized to absolute)

    Returns:
        Dataset ID (UUID4 string) or None if not found
    """
    normalized_root = str(normalize_root_dir(root_path))
    row = self._fetchone(
        "SELECT id FROM datasets WHERE project_id = ? AND root_path = ?",
        (project_id, normalized_root),
    )
    return row["id"] if row else None


def get_dataset_by_root_path(
    self, project_id: str, root_path: str
) -> Optional[Dict[str, Any]]:
    """
    Get dataset by project_id and root_path.

    Args:
        project_id: Project ID (UUID4 string)
        root_path: Root directory path (will be normalized to absolute)

    Returns:
        Dataset record as dictionary or None if not found
    """
    normalized_root = str(normalize_root_dir(root_path))
    row = self._fetchone(
        "SELECT * FROM datasets WHERE project_id = ? AND root_path = ?",
        (project_id, normalized_root),
    )
    return row if row else None


def get_dataset(self, dataset_id: str) -> Optional[Dict[str, Any]]:
    """
    Get dataset by ID.

    Args:
        dataset_id: Dataset ID (UUID4 string)

    Returns:
        Dataset record as dictionary or None if not found
    """
    row = self._fetchone("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
    return row if row else None


def get_project_datasets(self, project_id: str) -> List[Dict[str, Any]]:
    """
    Get all datasets for a project.

    Args:
        project_id: Project ID (UUID4 string)

    Returns:
        List of dataset records as dictionaries
    """
    rows = self._fetchall(
        "SELECT * FROM datasets WHERE project_id = ? ORDER BY created_at",
        (project_id,),
    )
    return rows if rows else []


def delete_dataset(self, dataset_id: str) -> bool:
    """
    Delete dataset and all associated files.

    This will cascade delete all files in the dataset.

    Args:
        dataset_id: Dataset ID (UUID4 string)

    Returns:
        True if dataset was found and deleted, False otherwise
    """
    row = self._fetchone("SELECT id FROM datasets WHERE id = ?", (dataset_id,))
    if not row:
        return False

    # Files will be cascade deleted due to FOREIGN KEY constraint
    self._execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
    self._commit()
    logger.info(f"Deleted dataset {dataset_id}")
    return True

