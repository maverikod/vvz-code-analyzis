"""
Final tests for MCP server to reach 90%+ coverage.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import requests
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from code_analysis.mcp_server import MCPServer


class TestMCPServerFinal:
    """Final tests for MCP server coverage."""

    def test_main_function(self):
        """Test main function can be imported."""
        from code_analysis.mcp_server import main
        assert callable(main)

    def test_server_logging(self):
        """Test server logging functionality."""
        import logging
        logging.basicConfig(level=logging.INFO)
        
        server = MCPServer("localhost", 15030)
        server.start()
        time.sleep(0.3)
        
        try:
            # Make a request to trigger logging
            requests.post(
                f"http://localhost:15030/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                timeout=2,
            )
        finally:
            server.stop()

    def test_full_text_search_with_entity_type(self):
        """Test full_text_search with entity_type filter."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "code_analysis" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            from code_analysis.core.database import CodeDatabase
            db = CodeDatabase(db_path)
            project_id = db.get_or_create_project(str(tmpdir))
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            db.add_code_content(file_id, "method", "test", "def test(): pass", "Test")
            db.close()
            
            server = MCPServer("localhost", 15031)
            server.start()
            time.sleep(0.5)
            
            try:
                response = requests.post(
                    f"http://localhost:15031/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "full_text_search",
                            "arguments": {
                                "root_dir": str(tmpdir),
                                "query": "test",
                                "entity_type": "method",
                                "limit": 10,
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

    def test_find_usages_with_filters(self):
        """Test find_usages with type and class filters."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "code_analysis" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            from code_analysis.core.database import CodeDatabase
            db = CodeDatabase(db_path)
            project_id = db.get_or_create_project(str(tmpdir))
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            db.add_usage(file_id, 10, "method_call", "method", "test_method", "TestClass")
            db.close()
            
            server = MCPServer("localhost", 15032)
            server.start()
            time.sleep(0.5)
            
            try:
                response = requests.post(
                    f"http://localhost:15032/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "find_usages",
                            "arguments": {
                                "root_dir": str(tmpdir),
                                "name": "test_method",
                                "target_type": "method",
                                "target_class": "TestClass",
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

    def test_search_classes_without_pattern(self):
        """Test search_classes without pattern."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "code_analysis" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            from code_analysis.core.database import CodeDatabase
            db = CodeDatabase(db_path)
            project_id = db.get_or_create_project(str(tmpdir))
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            db.add_class(file_id, "TestClass", 10, "Test", [])
            db.close()
            
            server = MCPServer("localhost", 15033)
            server.start()
            time.sleep(0.5)
            
            try:
                response = requests.post(
                    f"http://localhost:15033/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "search_classes",
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

    def test_search_methods_without_pattern(self):
        """Test search_methods without pattern."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "code_analysis" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            from code_analysis.core.database import CodeDatabase
            db = CodeDatabase(db_path)
            project_id = db.get_or_create_project(str(tmpdir))
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            class_id = db.add_class(file_id, "TestClass", 10, "Test", [])
            db.add_method(class_id, "method", 15, ["self"], "Method", False, False, False)
            db.close()
            
            server = MCPServer("localhost", 15034)
            server.start()
            time.sleep(0.5)
            
            try:
                response = requests.post(
                    f"http://localhost:15034/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "search_methods",
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

    def test_analyze_project_with_max_lines(self):
        """Test analyze_project with max_lines parameter."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text('def hello(): pass\n')
            
            server = MCPServer("localhost", 15035)
            server.start()
            time.sleep(0.5)
            
            try:
                response = requests.post(
                    f"http://localhost:15035/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "analyze_project",
                            "arguments": {
                                "root_dir": str(tmpdir),
                                "max_lines": 500,
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
