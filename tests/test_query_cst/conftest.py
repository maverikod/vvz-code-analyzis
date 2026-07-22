"""
Fixtures for query_cst command tests.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def project_root(tmp_path):
    """Project root as tmp_path."""
    return tmp_path


@pytest.fixture
def mock_db(project_root, monkeypatch):
    """Mock database for query_cst (resolve project, index_file after replace).

    ``query_cst_handler`` calls the driver-direct ``index_file_via_driver`` free
    function (stage-2 layer collapse) instead of ``database.index_file(...)`` - patch
    it at the handler's import site so this lightweight ``MagicMock`` double (which
    does not implement real SQL primitives) is not exercised by it.
    """
    db = MagicMock()
    db.get_project.return_value = {
        "id": "test-proj",
        "root_path": str(project_root),
    }
    db.index_file.return_value = {"success": True}
    db.disconnect.return_value = None
    monkeypatch.setattr(
        "code_analysis.commands.query_cst_handler.index_file_via_driver",
        lambda database, file_path, project_id: database.index_file(
            file_path=file_path, project_id=project_id
        ),
    )
    return db
