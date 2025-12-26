"""
Commands package for code analysis server.

This package contains all MCP command implementations.
Commands are automatically discovered by mcp-proxy-adapter when modules are imported.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# Import new command modules to ensure they are discovered by mcp-proxy-adapter
# Commands are auto-discovered when their modules are imported
# Only import new modules that we know work correctly

# File management commands
from . import file_management_mcp_commands  # noqa: F401

# Log viewer commands
from . import log_viewer_mcp_commands  # noqa: F401

# Worker status commands
from . import worker_status_mcp_commands  # noqa: F401

# Note: Other command modules (backup_mcp_commands, search_mcp_commands, etc.)
# are already working and don't need explicit import here.
# mcp-proxy-adapter will discover them automatically when the server starts.
