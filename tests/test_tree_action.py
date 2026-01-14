"""
Tests for TreeAction enum.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest

from code_analysis.core.database_client.objects.tree_action import TreeAction


class TestTreeAction:
    """Test TreeAction enum."""

    def test_tree_action_values(self):
        """Test TreeAction enum values."""
        assert TreeAction.REPLACE == "replace"
        assert TreeAction.DELETE == "delete"
        assert TreeAction.INSERT == "insert"

    def test_tree_action_from_string(self):
        """Test creating TreeAction from string."""
        assert TreeAction("replace") == TreeAction.REPLACE
        assert TreeAction("delete") == TreeAction.DELETE
        assert TreeAction("insert") == TreeAction.INSERT

    def test_tree_action_invalid_value(self):
        """Test invalid TreeAction value raises error."""
        with pytest.raises(ValueError):
            TreeAction("invalid")

    def test_tree_action_comparison(self):
        """Test TreeAction comparison."""
        assert TreeAction.REPLACE == "replace"
        assert TreeAction.DELETE != "replace"
        assert TreeAction.INSERT == "insert"
