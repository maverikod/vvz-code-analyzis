"""
Refactoring commands implementation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

from ..core.refactorer_pkg.splitter import ClassSplitter
from ..core.refactorer_pkg.extractor import SuperclassExtractor
from ..core.refactorer_pkg.file_splitter import FileToPackageSplitter

logger = logging.getLogger(__name__)


class RefactorCommand:
    """Commands for code refactoring."""

    def __init__(
        self,
        project_id: str,
        database: Optional[Any] = None,
        root_dir: Optional[Path] = None,
    ):
        """
        Initialize refactor command.

        Args:
            project_id: Project UUID
            database: Optional database instance for updating file data
            root_dir: Optional root directory for database operations
        """
        self.project_id = project_id
        self.database = database
        self.root_dir = Path(root_dir) if root_dir else None

    async def split_class(
        self, root_dir: str, file_path: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Split a class into multiple smaller classes.

        Args:
            root_dir: Root directory of the project
            file_path: Path to Python file (relative to root_dir or absolute)
            config: Split configuration

        Returns:
            Dictionary with success status and message
        """
        logger.info(f"Splitting class in {file_path} (project: {self.project_id})")

        file_path_obj = Path(file_path)
        if not file_path_obj.is_absolute():
            file_path_obj = Path(root_dir) / file_path_obj

        logger.info(f"Using file path: {file_path_obj}")

        splitter = ClassSplitter(
            file_path_obj,
            database=self.database,
            project_id=self.project_id,
            root_dir=self.root_dir or Path(root_dir),
        )
        try:
            success, message = splitter.split_class(config)
            if success:
                logger.info(f"Class split successful: {message}")
            else:
                logger.error(f"Class split failed: {message}")
            return {
                "success": success,
                "message": message,
                "project_id": self.project_id,
            }
        except Exception as e:
            error_msg = f"Error splitting class: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "message": error_msg,
                "project_id": self.project_id,
            }

    async def extract_superclass(
        self, root_dir: str, file_path: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract common functionality into base class.

        Args:
            root_dir: Root directory of the project
            file_path: Path to Python file (relative to root_dir or absolute)
            config: Extraction configuration

        Returns:
            Dictionary with success status and message
        """
        logger.info(
            f"Extracting superclass in {file_path} (project: {self.project_id})"
        )

        file_path_obj = Path(file_path)
        if not file_path_obj.is_absolute():
            file_path_obj = Path(root_dir) / file_path_obj

        logger.info(f"Using file path: {file_path_obj}")

        extractor = SuperclassExtractor(
            file_path_obj,
            database=self.database,
            project_id=self.project_id,
            root_dir=self.root_dir or Path(root_dir),
        )
        try:
            success, message = extractor.extract_superclass(config)
            if success:
                logger.info(f"Superclass extraction successful: {message}")
            else:
                logger.error(f"Superclass extraction failed: {message}")
            return {
                "success": success,
                "message": message,
                "project_id": self.project_id,
            }
        except Exception as e:
            error_msg = f"Error extracting superclass: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "message": error_msg,
                "project_id": self.project_id,
            }

    async def split_file_to_package(
        self, root_dir: str, file_path: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Split a large Python file into a package with multiple modules.

        Args:
            root_dir: Root directory of the project
            file_path: Path to Python file (relative to root_dir or absolute)
            config: Split configuration

        Returns:
            Dictionary with success status and message
        """
        logger.info(
            f"Splitting file to package in {file_path} (project: {self.project_id})"
        )

        file_path_obj = Path(file_path)
        if not file_path_obj.is_absolute():
            file_path_obj = Path(root_dir) / file_path_obj

        logger.info(f"Using file path: {file_path_obj}")

        splitter = FileToPackageSplitter(
            file_path_obj,
            database=self.database,
            project_id=self.project_id,
            root_dir=self.root_dir or Path(root_dir),
        )
        try:
            success, message = splitter.split_file_to_package(config)
            if success:
                logger.info(f"File split to package successful: {message}")
            else:
                logger.error(f"File split to package failed: {message}")
            return {
                "success": success,
                "message": message,
                "project_id": self.project_id,
            }
        except Exception as e:
            error_msg = f"Error splitting file to package: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "message": error_msg,
                "project_id": self.project_id,
            }
