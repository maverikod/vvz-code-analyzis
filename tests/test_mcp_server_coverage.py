"""
Additional tests for MCP server to achieve 90%+ coverage.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import json
import requests
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from code_analysis.mcp_server import MCPServer
from code_analysis.core.database import CodeDatabase


class TestMCPServerCoverage:
    """Additional tests for MCP server coverage."""

    def test_tools_call_full_text_search(self):
        """Test calling full_text_search tool."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "code_analysis" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            project_id = db.get_or_create_project(str(tmpdir))
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            db.add_code_content(file_id, "method", "test", "def test(): pass", "Test method")
            db.close()
            
            server = MCPServer("localhost", 15010)
            server.start()
            time.sleep(0.5)
            
            try:
                response = requests.post(
                    f"http://localhost:15010/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "full_text_search",
                            "arguments": {
                                "root_dir": str(tmpdir),
                                "query": "test",
                            },
                        },
                    },
                    timeout=5,
                )
                
                assert response.status_code == 200
                data = response.json()
                assert "result" in data
                
            finally:
                server.stop()

    def test_tools_call_search_classes(self):
        """Test calling search_classes tool."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "code_analysis" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            project_id = db.get_or_create_project(str(tmpdir))
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            db.add_class(file_id, "TestClass", 10, "Test", [])
            db.close()
            
            server = MCPServer("localhost", 15011)
            server.start()
            time.sleep(0.5)
            
            try:
                response = requests.post(
                    f"http://localhost:15011/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "search_classes",
                            "arguments": {
                                "root_dir": str(tmpdir),
                                "pattern": "Test",
                            },
                        },
                    },
                    timeout=5,
                )
                
                assert response.status_code == 200
                data = response.json()
                assert "result" in data
                
            finally:
                server.stop()

    def test_tools_call_search_methods(self):
        """Test calling search_methods tool."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "code_analysis" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            project_id = db.get_or_create_project(str(tmpdir))
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            class_id = db.add_class(file_id, "TestClass", 10, "Test", [])
            db.add_method(class_id, "test_method", 15, ["self"], "Method", False, False, False)
            db.close()
            
            server = MCPServer("localhost", 15012)
            server.start()
            time.sleep(0.5)
            
            try:
                response = requests.post(
                    f"http://localhost:15012/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "search_methods",
                            "arguments": {
                                "root_dir": str(tmpdir),
                                "pattern": "test",
                            },
                        },
                    },
                    timeout=5,
                )
                
                assert response.status_code == 200
                data = response.json()
                assert "result" in data
                
            finally:
                server.stop()

    def test_tools_call_get_issues(self):
        """Test calling get_issues tool."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "code_analysis" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            project_id = db.get_or_create_project(str(tmpdir))
            file_id = db.add_file("test.py", 100, 1234567890.0, False, project_id)
            db.add_issue("files_without_docstrings", "Missing docstring", file_id=file_id)
            db.close()
            
            server = MCPServer("localhost", 15013)
            server.start()
            time.sleep(0.5)
            
            try:
                response = requests.post(
                    f"http://localhost:15013/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "get_issues",
                            "arguments": {
                                "root_dir": str(tmpdir),
                            },
                        },
                    },
                    timeout=5,
                )
                
                assert response.status_code == 200
                data = response.json()
                assert "result" in data
                
            finally:
                server.stop()

    def test_tools_call_get_issues_with_type(self):
        """Test calling get_issues with issue_type filter."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "code_analysis" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            project_id = db.get_or_create_project(str(tmpdir))
            file_id = db.add_file("test.py", 100, 1234567890.0, False, project_id)
            db.add_issue("files_without_docstrings", "Missing docstring", file_id=file_id)
            db.close()
            
            server = MCPServer("localhost", 15014)
            server.start()
            time.sleep(0.5)
            
            try:
                response = requests.post(
                    f"http://localhost:15014/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "get_issues",
                            "arguments": {
                                "root_dir": str(tmpdir),
                                "issue_type": "files_without_docstrings",
                            },
                        },
                    },
                    timeout=5,
                )
                
                assert response.status_code == 200
                data = response.json()
                assert "result" in data
                
            finally:
                server.stop()

    def test_tools_call_with_relative_file_path(self):
        """Test calling tool with relative file path."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text(
                '''class TestClass:
    def method1(self):
        pass
    
    def method2(self):
        pass
'''
            )
            
            server = MCPServer("localhost", 15015)
            server.start()
            time.sleep(0.5)
            
            try:
                response = requests.post(
                    f"http://localhost:15015/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "split_class",
                            "arguments": {
                                "root_dir": str(tmpdir),
                                "file_path": "test.py",
                                "config": {
                                    "src_class": "TestClass",
                                    "dst_classes": {
                                        "DstClass1": {
                                            "props": [],
                                            "methods": ["method1"]
                                        }
                                    }
                                },
                            },
                        },
                    },
                    timeout=10,
                )
                
                assert response.status_code == 200
                data = response.json()
                assert "result" in data
                
            finally:
                server.stop()

    def test_tools_call_with_absolute_file_path(self):
        """Test calling tool with absolute file path."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text('class TestClass: pass\n')
            
            server = MCPServer("localhost", 15016)
            server.start()
            time.sleep(0.5)
            
            try:
                response = requests.post(
                    f"http://localhost:15016/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "analyze_project",
                            "arguments": {
                                "root_dir": str(tmpdir),
                            },
                        },
                    },
                    timeout=10,
                )
                
                assert response.status_code == 200
                data = response.json()
                assert "result" in data
                
            finally:
                server.stop()

    def test_tools_call_error_handling(self):
        """Test error handling in tool calls."""
        server = MCPServer("localhost", 15017)
        server.start()
        time.sleep(0.5)
        
        try:
            # Call with invalid root_dir
            response = requests.post(
                f"http://localhost:15017/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "analyze_project",
                        "arguments": {
                            "root_dir": "/nonexistent/path/xyz",
                        },
                    },
                },
                timeout=5,
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "result" in data
            # Should handle error gracefully
            
        finally:
            server.stop()

    def test_get_tools_list_structure(self):
        """Test that tools list has correct structure."""
        server = MCPServer("localhost", 15018)
        server.start()
        time.sleep(0.5)
        
        try:
            response = requests.post(
                f"http://localhost:15018/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {},
                },
                timeout=2,
            )
            
            assert response.status_code == 200
            data = response.json()
            tools = data["result"]["tools"]
            
            # Check structure of first tool
            assert "name" in tools[0]
            assert "description" in tools[0]
            assert "inputSchema" in tools[0]
            assert "properties" in tools[0]["inputSchema"]
            assert "root_dir" in tools[0]["inputSchema"]["properties"]
            
        finally:
            server.stop()
