"""
Tests for find_dependencies response contract: file_path and cst_node_id in each entity.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import uuid
from unittest.mock import patch

import pytest

from code_analysis.commands.ast.dependencies import (
    FindDependenciesMCPCommand,
    _is_valid_uuid4,
)


class TestDependenciesResponseContract:
    """Validate find_dependencies response includes file_path and valid cst_node_id."""

    def test_is_valid_uuid4_accepts_valid(self):
        """_is_valid_uuid4 accepts canonical UUID4 string."""
        valid = str(uuid.uuid4())
        assert _is_valid_uuid4(valid) is True

    def test_is_valid_uuid4_rejects_empty(self):
        """_is_valid_uuid4 rejects empty or None."""
        assert _is_valid_uuid4("") is False
        assert _is_valid_uuid4(None) is False

    def test_is_valid_uuid4_rejects_invalid(self):
        """_is_valid_uuid4 rejects non-UUID4."""
        assert _is_valid_uuid4("not-a-uuid") is False
        assert _is_valid_uuid4("00000000-0000-0000-0000-000000000000") is False  # v4

    @pytest.mark.asyncio
    async def test_find_dependencies_response_has_file_path_and_cst_node_id(self):
        """Each dependency in the response has file_path and valid UUID4 cst_node_id."""
        project_id = "test-project-id"
        entity_name = "SomeClass"

        class MockDB:
            def execute(self, sql, params=None):
                if params is None:
                    params = ()
                # Inheritance query: returns classes with file_path, cst_node_id
                if "bases LIKE" in sql:
                    return {
                        "data": [
                            {
                                "file_path": "src/foo.py",
                                "line": 10,
                                "name": "Child",
                                "bases": '["SomeClass"]',
                                "cst_node_id": str(uuid.uuid4()),
                            }
                        ]
                    }
                # Containing-entity query (for import/usage resolution)
                if "ORDER BY line DESC LIMIT 1" in sql and "cst_node_id" in sql:
                    return {"data": [{"cst_node_id": str(uuid.uuid4())}]}
                # Imports / usages: return empty so we only get inheritance
                return {"data": []}

            def disconnect(self):
                pass

        mock_db = MockDB()
        with patch.object(
            FindDependenciesMCPCommand, "_resolve_project_root", return_value=None
        ), patch.object(
            FindDependenciesMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ):
            cmd = FindDependenciesMCPCommand()
            result = await cmd.execute(
                project_id=project_id,
                entity_name=entity_name,
                entity_type="class",
            )

        data = getattr(result, "data", None) or {}
        deps = data.get("dependencies", [])
        assert len(deps) >= 1, "Expected at least one dependency from mock"
        for d in deps:
            assert "file_path" in d, f"Missing file_path in {d}"
            assert "cst_node_id" in d, f"Missing cst_node_id in {d}"
            assert d["cst_node_id"], "cst_node_id must be non-empty"
            assert _is_valid_uuid4(
                d["cst_node_id"]
            ), f"cst_node_id must be valid UUID4: {d['cst_node_id']!r}"
