#!/usr/bin/env python3
"""
Script to register code analysis MCP server with MCP Proxy.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import requests
import json
import sys

# MCP Proxy configuration
PROXY_URL = "http://localhost:3002/mcp"
AUTH_TOKEN = "R5aaTkehjkwjgx4UEexkBpFPDNNHfFHtWqQbwkG-OIY"

# Server configuration
SERVER_ID = "code-analysis-server"
SERVER_URL = "http://localhost:15000/mcp"
SERVER_NAME = "Code Analysis Server"
DESCRIPTION = "Code analysis tool providing project analysis, usage search, full-text search, and refactoring capabilities"


def register_server():
    """Register MCP server with proxy."""
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json",
    }

    # First, try to call register_server tool through MCP Proxy
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "register_server",
            "arguments": {
                "server_id": SERVER_ID,
                "server_url": SERVER_URL,
                "server_name": SERVER_NAME,
                "description": DESCRIPTION,
            },
        },
    }
    
    # Alternative: direct registration if proxy supports it
    # Try both approaches

    try:
        response = requests.post(PROXY_URL, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        if "error" in result:
            print(f"Error registering server: {result['error']}")
            return False
        
        print(f"✅ Server registered successfully!")
        print(f"   Server ID: {SERVER_ID}")
        print(f"   Server URL: {SERVER_URL}")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error connecting to MCP Proxy: {e}")
        print(f"   Make sure MCP Proxy is running on {PROXY_URL}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


if __name__ == "__main__":
    success = register_server()
    sys.exit(0 if success else 1)
