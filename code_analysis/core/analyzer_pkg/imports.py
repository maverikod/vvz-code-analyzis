"""
Module imports.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
from pathlib import Path
from typing import Optional


def _analyze_import(
    self, node: ast.Import, file_path: Path, file_id: Optional[int] = None
) -> None:
    """Analyze import statement."""
    file_path_str = str(file_path)
    for alias in node.names:
        import_key = f"{file_path}:{alias.name}"
        import_info = {
            "name": alias.name,
            "file": file_path_str,
            "line": node.lineno,
            "type": "import",
        }
        self.code_map["imports"][import_key] = import_info

        # Save to database
        if self.database and file_id:
            self.database.add_import(file_id, alias.name, None, "import", node.lineno)

    # Check for invalid imports
    if self.issue_detector:
        self.issue_detector.check_invalid_import(node, file_path)


def _analyze_import_from(
    self, node: ast.ImportFrom, file_path: Path, file_id: Optional[int] = None
) -> None:
    """Analyze import from statement."""
    file_path_str = str(file_path)
    module = node.module or ""
    for alias in node.names:
        import_key = f"{file_path}:{alias.name}"
        import_info = {
            "name": alias.name,
            "file": file_path_str,
            "line": node.lineno,
            "type": "import_from",
            "module": module,
        }
        self.code_map["imports"][import_key] = import_info

        # Save to database
        if self.database and file_id:
            self.database.add_import(
                file_id, alias.name, module, "import_from", node.lineno
            )

    # Check for invalid imports
    if self.issue_detector:
        self.issue_detector.check_invalid_import_from(node, file_path)
