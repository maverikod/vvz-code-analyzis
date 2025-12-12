"""
Tests for MCP server refactoring commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import requests
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from code_analysis.mcp_server import MCPServer


class TestMCPServerRefactor:
    """Tests for refactoring commands in MCP server."""

    def test_tools_call_split_class(self):
        """Test calling split_class tool."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text(
                '''class SourceClass:
    """Source class docstring."""
    
    def __init__(self):
        self.prop1 = 1
        self.prop2 = 2
    
    def method1(self):
        """Method 1."""
        return 1
    
    def method2(self):
        """Method 2."""
        return 2
'''
            )
            
            server = MCPServer("localhost", 15020)
            server.start()
            time.sleep(0.5)
            
            try:
                response = requests.post(
                    f"http://localhost:15020/mcp",
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
                                    "src_class": "SourceClass",
                                    "dst_classes": {
                                        "DstClass1": {
                                            "props": ["prop1"],
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

    def test_tools_call_extract_superclass(self):
        """Test calling extract_superclass tool."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text(
                '''class Child1:
    def __init__(self):
        self.prop1 = 1
    
    def method(self):
        return 1

class Child2:
    def __init__(self):
        self.prop1 = 1
    
    def method(self):
        return 2
'''
            )
            
            server = MCPServer("localhost", 15021)
            server.start()
            time.sleep(0.5)
            
            try:
                response = requests.post(
                    f"http://localhost:15021/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "extract_superclass",
                            "arguments": {
                                "root_dir": str(tmpdir),
                                "file_path": "test.py",
                                "config": {
                                    "base_class": "Base",
                                    "child_classes": ["Child1", "Child2"],
                                    "abstract_methods": [],
                                    "extract_from": {
                                        "Child1": {
                                            "properties": ["prop1"],
                                            "methods": ["method"]
                                        },
                                        "Child2": {
                                            "properties": ["prop1"],
                                            "methods": ["method"]
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

    def test_tools_call_merge_classes(self):
        """Test calling merge_classes tool."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text(
                '''class Source1:
    def method1(self):
        return 1

class Source2:
    def method2(self):
        return 2
'''
            )
            
            server = MCPServer("localhost", 15022)
            server.start()
            time.sleep(0.5)
            
            try:
                response = requests.post(
                    f"http://localhost:15022/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "merge_classes",
                            "arguments": {
                                "root_dir": str(tmpdir),
                                "file_path": "test.py",
                                "config": {
                                    "base_class": "Merged",
                                    "source_classes": ["Source1", "Source2"]
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

    def test_tools_call_with_exception(self):
        """Test handling exceptions in tool calls."""
        server = MCPServer("localhost", 15023)
        server.start()
        time.sleep(0.5)
        
        try:
            # Call with file that doesn't exist
            response = requests.post(
                f"http://localhost:15023/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "split_class",
                        "arguments": {
                            "root_dir": "/tmp",
                            "file_path": "/nonexistent/file.py",
                            "config": {
                                "src_class": "Test",
                                "dst_classes": {}
                            },
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
