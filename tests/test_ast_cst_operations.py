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
            node_type="FunctionDef",
            name="test_function",
            start_line=1,
            end_line=10,
            start_col=0,
            end_col=20,
        )

        assert node.node_type == "FunctionDef"
        assert node.name == "test_function"
        assert node.start_line == 1
        assert node.end_line == 10

    def test_ast_node_to_dict(self):
        """Test converting AST node to dictionary."""
        node = ASTNode(
            node_type="ClassDef",
            name="TestClass",
            start_line=1,
            end_line=5,
        )

        node_dict = node.to_dict()
        assert isinstance(node_dict, dict)
        assert node_dict["node_type"] == "ClassDef"
        assert node_dict["name"] == "TestClass"

    def test_ast_node_from_dict(self):
        """Test creating AST node from dictionary."""
        node_dict = {
            "node_type": "FunctionDef",
            "name": "test_func",
            "start_line": 1,
            "end_line": 10,
        }

        node = ASTNode.from_dict(node_dict)
        assert node.node_type == "FunctionDef"
        assert node.name == "test_func"


class TestCSTNode:
    """Test CSTNode object model."""

    def test_create_cst_node(self):
        """Test creating CST node."""
        node = CSTNode(
            node_type="FunctionDef",
            name="test_function",
            start_line=1,
            end_line=10,
            start_col=0,
            end_col=20,
        )

        assert node.node_type == "FunctionDef"
        assert node.name == "test_function"
        assert node.start_line == 1

    def test_cst_node_to_dict(self):
        """Test converting CST node to dictionary."""
        node = CSTNode(
            node_type="ClassDef",
            name="TestClass",
            start_line=1,
            end_line=5,
        )

        node_dict = node.to_dict()
        assert isinstance(node_dict, dict)
        assert node_dict["node_type"] == "ClassDef"

    def test_cst_node_from_dict(self):
        """Test creating CST node from dictionary."""
        node_dict = {
            "node_type": "FunctionDef",
            "name": "test_func",
            "start_line": 1,
            "end_line": 10,
        }

        node = CSTNode.from_dict(node_dict)
        assert node.node_type == "FunctionDef"
        assert node.name == "test_func"


class TestTreeAction:
    """Test TreeAction object model."""

    def test_create_tree_action(self):
        """Test creating tree action."""
        action = TreeAction(
            action_type="insert",
            target_path="//FunctionDef[@name='test']",
            content="def new_function(): pass",
        )

        assert action.action_type == "insert"
        assert action.target_path == "//FunctionDef[@name='test']"
        assert action.content == "def new_function(): pass"

    def test_tree_action_to_dict(self):
        """Test converting tree action to dictionary."""
        action = TreeAction(
            action_type="delete",
            target_path="//FunctionDef[@name='old']",
        )

        action_dict = action.to_dict()
        assert isinstance(action_dict, dict)
        assert action_dict["action_type"] == "delete"

    def test_tree_action_from_dict(self):
        """Test creating tree action from dictionary."""
        action_dict = {
            "action_type": "replace",
            "target_path": "//FunctionDef[@name='test']",
            "content": "def new(): pass",
        }

        action = TreeAction.from_dict(action_dict)
        assert action.action_type == "replace"
        assert action.target_path == "//FunctionDef[@name='test']"


class TestXPathFilter:
    """Test XPathFilter object model."""

    def test_create_xpath_filter(self):
        """Test creating XPath filter."""
        filter_obj = XPathFilter(
            xpath="//FunctionDef",
            node_type="FunctionDef",
        )

        assert filter_obj.xpath == "//FunctionDef"
        assert filter_obj.node_type == "FunctionDef"

    def test_xpath_filter_to_dict(self):
        """Test converting XPath filter to dictionary."""
        filter_obj = XPathFilter(
            xpath="//ClassDef[@name='Test']",
            node_type="ClassDef",
        )

        filter_dict = filter_obj.to_dict()
        assert isinstance(filter_dict, dict)
        assert filter_dict["xpath"] == "//ClassDef[@name='Test']"

    def test_xpath_filter_from_dict(self):
        """Test creating XPath filter from dictionary."""
        filter_dict = {
            "xpath": "//FunctionDef",
            "node_type": "FunctionDef",
        }

        filter_obj = XPathFilter.from_dict(filter_dict)
        assert filter_obj.xpath == "//FunctionDef"
        assert filter_obj.node_type == "FunctionDef"


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
        params = {"filter": {"xpath": "//FunctionDef"}}

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
        params = {"file_id": 999, "filter": {"xpath": "//FunctionDef"}}

        result = query_handler.handle_query_ast(params)

        assert isinstance(result, ErrorResult)
        assert result.error_code == ErrorCode.NOT_FOUND

    def test_query_cst_missing_file_id(self, query_handler):
        """Test query_cst with missing file_id."""
        params = {"filter": {"xpath": "//FunctionDef"}}

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
        assert result.error_code == ErrorCode.NOT_FOUND


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
        assert result.error_code == ErrorCode.NOT_FOUND
