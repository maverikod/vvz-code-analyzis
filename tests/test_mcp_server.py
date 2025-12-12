"""
Tests for MCP server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import json
import requests
import time
import threading
from pathlib import Path
from tempfile import TemporaryDirectory

from code_analysis.mcp_server import MCPServer, MCPRequestHandler
from code_analysis.core.database import CodeDatabase


class TestMCPServer:
    """Tests for MCP server."""

    def test_server_start_stop(self):
        """Test starting and stopping MCP server."""
        server = MCPServer("localhost", 15001)
        
        server.start()
        time.sleep(0.5)  # Give server time to start
        
        # Check server is running
        assert server.server is not None
        assert server.thread is not None
        assert server.thread.is_alive()
        
        server.stop()
        time.sleep(0.2)
        
        # Server should be stopped
        assert not server.thread.is_alive()

    def test_tools_list_request(self):
        """Test tools/list request."""
        server = MCPServer("localhost", 15002)
        server.start()
        time.sleep(0.5)
        
        try:
            response = requests.post(
                f"http://localhost:15002/mcp",
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
            assert "result" in data
            assert "tools" in data["result"]
            assert len(data["result"]["tools"]) > 0
            
        finally:
            server.stop()

    def test_unknown_method(self):
        """Test handling unknown method."""
        server = MCPServer("localhost", 15003)
        server.start()
        time.sleep(0.5)
        
        try:
            response = requests.post(
                f"http://localhost:15003/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "unknown/method",
                    "params": {},
                },
                timeout=2,
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "error" in data
            assert data["error"]["code"] == -32601
            
        finally:
            server.stop()

    def test_tools_call_analyze_project(self):
        """Test calling analyze_project tool."""
        with TemporaryDirectory() as tmpdir:
            # Create a simple Python file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text('def hello(): pass\n')
            
            server = MCPServer("localhost", 15004)
            server.start()
            time.sleep(0.5)
            
            try:
                response = requests.post(
                    f"http://localhost:15004/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "analyze_project",
                            "arguments": {
                                "root_dir": str(tmpdir),
                                "max_lines": 400,
                            },
                        },
                    },
                    timeout=10,
                )
                
                assert response.status_code == 200
                data = response.json()
                assert "result" in data
                assert "content" in data["result"]
                
            finally:
                server.stop()

    def test_tools_call_find_usages(self):
        """Test calling find_usages tool."""
        with TemporaryDirectory() as tmpdir:
            # Create test project with database
            db_path = Path(tmpdir) / "code_analysis" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            project_id = db.get_or_create_project(str(tmpdir))
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            db.add_usage(file_id, 10, "method_call", "method", "test_method")
            db.close()
            
            server = MCPServer("localhost", 15005)
            server.start()
            time.sleep(0.5)
            
            try:
                response = requests.post(
                    f"http://localhost:15005/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "find_usages",
                            "arguments": {
                                "root_dir": str(tmpdir),
                                "name": "test_method",
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

    def test_tools_call_missing_root_dir(self):
        """Test calling tool without root_dir."""
        server = MCPServer("localhost", 15006)
        server.start()
        time.sleep(0.5)
        
        try:
            response = requests.post(
                f"http://localhost:15006/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "find_usages",
                        "arguments": {
                            "name": "test",
                        },
                    },
                },
                timeout=2,
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "result" in data
            assert data["result"].get("isError", False)
            
        finally:
            server.stop()

    def test_tools_call_unknown_tool(self):
        """Test calling unknown tool."""
        server = MCPServer("localhost", 15007)
        server.start()
        time.sleep(0.5)
        
        try:
            response = requests.post(
                f"http://localhost:15007/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "unknown_tool",
                        "arguments": {
                            "root_dir": "/tmp",
                        },
                    },
                },
                timeout=2,
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "result" in data
            assert data["result"].get("isError", False)
            
        finally:
            server.stop()

    def test_invalid_json_request(self):
        """Test handling invalid JSON."""
        server = MCPServer("localhost", 15008)
        server.start()
        time.sleep(0.5)
        
        try:
            response = requests.post(
                f"http://localhost:15008/mcp",
                data="invalid json",
                headers={"Content-Type": "application/json"},
                timeout=2,
            )
            
            # Should handle error gracefully
            assert response.status_code in [200, 400, 500]
            
        finally:
            server.stop()

    def test_404_for_non_mcp_path(self):
        """Test 404 for non-MCP paths."""
        server = MCPServer("localhost", 15009)
        server.start()
        time.sleep(0.5)
        
        try:
            response = requests.post(
                f"http://localhost:15009/other",
                json={"test": "data"},
                timeout=2,
            )
            
            assert response.status_code == 404
            
        finally:
            server.stop()
