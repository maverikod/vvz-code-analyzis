"""
Commands package for code_analysis MCP server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# Import commands for automatic registration
from .project_management_mcp_commands import (  # noqa: F401
    ChangeProjectIdMCPCommand,
    ListProjectsMCPCommand,
)


