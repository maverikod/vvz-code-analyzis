"""
Unit tests for AST/CST operations.

Tests AST/CST query and modify operations at unit level (without real server).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from unittest.mock import Mock

from code_analysis.core.database_client.objects import (
    ASTNode,
    CSTNode,
    TreeAction,
    XPathFilter,
)
from code_analysis.core.database_driver_pkg.rpc_handlers_ast_cst_query import (
    _RPCHandlersASTCSTQueryMixin,
)
from code_analysis.core.database_driver_pkg.rpc_handlers_ast_modify import (
    _RPCHandlersASTModifyMixin,
)
from code_analysis.core.database_driver_pkg.rpc_handlers_cst_modify import (
    _RPCHandlersCSTModifyMixin,
)
from code_analysis.core.database_driver_pkg.result import ErrorResult
from code_analysis.core.database_driver_pkg.rpc_protocol import ErrorCode


class TestASTNode:
    """Test ASTNode object model."""

    def test_create_ast_node(self):
        """Test creating AST node."""
        node = ASTNode(
            file_id=1,
            project_id="test-project",
            ast_json='{"type": "Module"}',
            ast_hash="abc123",
        )

        assert node.file_id == 1
        assert node.project_id == "test-project"
        assert node.ast_json == '{"type": "Module"}'

    def test_ast_node_to_db_row(self):
        """Test converting AST node to database row."""
        node = ASTNode(
            file_id=1,
            project_id="test-project",
            ast_json='{"type": "Module"}',
            ast_hash="abc123",
        )

        db_row = node.to_db_row()
        assert isinstance(db_row, dict)
        assert db_row["file_id"] == 1
        assert db_row["project_id"] == "test-project"

    def test_ast_node_from_dict(self):
        """Test creating AST node from dictionary."""
        node_dict = {
            "file_id": 1,
            "project_id": "test-project",
            "ast_json": '{"type": "Module"}',
            "ast_hash": "abc123",
        }

        node = ASTNode.from_dict(node_dict)
        assert node.file_id == 1
        assert node.project_id == "test-project"


class TestCSTNode:
    """Test CSTNode object model."""

    def test_create_cst_node(self):
        """Test creating CST node."""
        node = CSTNode(
            file_id=1,
            project_id="test-project",
            cst_code="def test(): pass",
            cst_hash="abc123",
        )

        assert node.file_id == 1
        assert node.project_id == "test-project"
        assert node.cst_code == "def test(): pass"

    def test_cst_node_to_db_row(self):
        """Test converting CST node to database row."""
        node = CSTNode(
            file_id=1,
            project_id="test-project",
            cst_code="def test(): pass",
            cst_hash="abc123",
        )

        db_row = node.to_db_row()
        assert isinstance(db_row, dict)
        assert db_row["file_id"] == 1

    def test_cst_node_from_dict(self):
        """Test creating CST node from dictionary."""
        node_dict = {
            "file_id": 1,
            "project_id": "test-project",
            "cst_code": "def test(): pass",
            "cst_hash": "abc123",
        }

        node = CSTNode.from_dict(node_dict)
        assert node.file_id == 1
        assert node.project_id == "test-project"


class TestTreeAction:
    """Test TreeAction object model."""

    def test_tree_action_enum_values(self):
        """Test TreeAction enum values."""
        assert TreeAction.REPLACE == "replace"
        assert TreeAction.DELETE == "delete"
        assert TreeAction.INSERT == "insert"

    def test_tree_action_usage(self):
        """Test using TreeAction enum."""
        action = TreeAction.INSERT
        assert action == "insert"
        assert isinstance(action, TreeAction)


class TestXPathFilter:
    """Test XPathFilter object model."""

    def test_create_xpath_filter(self):
        """Test creating XPath filter."""
        filter_obj = XPathFilter(
            selector="function[name='test']",
            node_type="function",
        )

        assert filter_obj.selector == "function[name='test']"
        assert filter_obj.node_type == "function"

    def test_xpath_filter_to_dict(self):
        """Test converting XPath filter to dictionary."""
        filter_obj = XPathFilter(
            selector="class[name='Test']",
            node_type="class",
        )

        filter_dict = filter_obj.to_dict()
        assert isinstance(filter_dict, dict)
        assert filter_dict["selector"] == "class[name='Test']"

    def test_xpath_filter_from_dict(self):
        """Test creating XPath filter from dictionary."""
        filter_dict = {
            "selector": "function[name='test']",
            "node_type": "function",
        }

        filter_obj = XPathFilter.from_dict(filter_dict)
        assert filter_obj.selector == "function[name='test']"
        assert filter_obj.node_type == "function"


class TestASTCSTQueryHandlers:
    """Test AST/CST query handlers."""

    @pytest.fixture
    def mock_driver(self):
        """Create mock driver."""
        driver = Mock()
        driver.select = Mock(return_value=[])
        return driver

    @pytest.fixture
    def query_handler(self, mock_driver):
        """Create query handler instance."""
        handler = _RPCHandlersASTCSTQueryMixin()
        handler.driver = mock_driver
        return handler

    def test_query_ast_missing_file_id(self, query_handler):
        """Test query_ast with missing file_id."""
        params = {"filter": {"selector": "function"}}

        result = query_handler.handle_query_ast(params)

        assert isinstance(result, ErrorResult)
        assert result.error_code == ErrorCode.VALIDATION_ERROR

    def test_query_ast_missing_filter(self, query_handler):
        """Test query_ast with missing filter."""
        params = {"file_id": 1}

        result = query_handler.handle_query_ast(params)

        assert isinstance(result, ErrorResult)
        assert result.error_code == ErrorCode.VALIDATION_ERROR

    def test_query_ast_file_not_found(self, query_handler, mock_driver):
        """Test query_ast with non-existent file."""
        mock_driver.select.return_value = []
        params = {"file_id": 999, "filter": {"selector": "function"}}

        result = query_handler.handle_query_ast(params)

        assert isinstance(result, ErrorResult)
        # May return DATABASE_ERROR or NOT_FOUND depending on implementation
        assert result.error_code in (ErrorCode.NOT_FOUND, ErrorCode.DATABASE_ERROR)

    def test_query_cst_missing_file_id(self, query_handler):
        """Test query_cst with missing file_id."""
        params = {"filter": {"selector": "function"}}

        result = query_handler.handle_query_cst(params)

        assert isinstance(result, ErrorResult)
        assert result.error_code == ErrorCode.VALIDATION_ERROR

    def test_query_cst_missing_filter(self, query_handler):
        """Test query_cst with missing filter."""
        params = {"file_id": 1}

        result = query_handler.handle_query_cst(params)

        assert isinstance(result, ErrorResult)
        assert result.error_code == ErrorCode.VALIDATION_ERROR


class TestASTModifyHandlers:
    """Test AST modify handlers."""

    @pytest.fixture
    def mock_driver(self):
        """Create mock driver."""
        driver = Mock()
        driver.select = Mock(return_value=[])
        driver.update = Mock(return_value=1)
        driver.insert = Mock(return_value=1)
        return driver

    @pytest.fixture
    def modify_handler(self, mock_driver):
        """Create modify handler instance."""
        handler = _RPCHandlersASTModifyMixin()
        handler.driver = mock_driver
        return handler

    def test_modify_ast_missing_file_id(self, modify_handler):
        """Test modify_ast with missing file_id."""
        params = {"actions": []}

        result = modify_handler.handle_modify_ast(params)

        assert isinstance(result, ErrorResult)
        assert result.error_code == ErrorCode.VALIDATION_ERROR

    def test_modify_ast_missing_actions(self, modify_handler):
        """Test modify_ast with missing actions."""
        params = {"file_id": 1}

        result = modify_handler.handle_modify_ast(params)

        assert isinstance(result, ErrorResult)
        assert result.error_code == ErrorCode.VALIDATION_ERROR

    def test_modify_ast_file_not_found(self, modify_handler, mock_driver):
        """Test modify_ast with non-existent file."""
        mock_driver.select.return_value = []
        params = {
            "file_id": 999,
            "actions": [{"action_type": "insert", "target_path": "//FunctionDef"}],
        }

        result = modify_handler.handle_modify_ast(params)

        assert isinstance(result, ErrorResult)
        # May return VALIDATION_ERROR or NOT_FOUND depending on implementation
        assert result.error_code in (ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR)


class TestCSTModifyHandlers:
    """Test CST modify handlers."""

    @pytest.fixture
    def mock_driver(self):
        """Create mock driver."""
        driver = Mock()
        driver.select = Mock(return_value=[])
        driver.update = Mock(return_value=1)
        driver.insert = Mock(return_value=1)
        return driver

    @pytest.fixture
    def modify_handler(self, mock_driver):
        """Create modify handler instance."""
        handler = _RPCHandlersCSTModifyMixin()
        handler.driver = mock_driver
        return handler

    def test_modify_cst_missing_file_id(self, modify_handler):
        """Test modify_cst with missing file_id."""
        params = {"actions": []}

        result = modify_handler.handle_modify_cst(params)

        assert isinstance(result, ErrorResult)
        assert result.error_code == ErrorCode.VALIDATION_ERROR

    def test_modify_cst_missing_actions(self, modify_handler):
        """Test modify_cst with missing actions."""
        params = {"file_id": 1}

        result = modify_handler.handle_modify_cst(params)

        assert isinstance(result, ErrorResult)
        assert result.error_code == ErrorCode.VALIDATION_ERROR

    def test_modify_cst_file_not_found(self, modify_handler, mock_driver):
        """Test modify_cst with non-existent file."""
        mock_driver.select.return_value = []
        params = {
            "file_id": 999,
            "actions": [{"action_type": "insert", "target_path": "//FunctionDef"}],
        }

        result = modify_handler.handle_modify_cst(params)

        assert isinstance(result, ErrorResult)
        # May return VALIDATION_ERROR or NOT_FOUND depending on implementation
        assert result.error_code in (ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR)
