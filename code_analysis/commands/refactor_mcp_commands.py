"""
MCP commands for code refactoring operations.

Re-exports split_class, extract_superclass, and split_file_to_package commands
from dedicated modules to keep file size under limit.

Rule: All refactor commands that take project_id and use_queue=True MUST override
validate_params() to call BaseMCPCommand._validate_project_id_exists(params["project_id"])
so that invalid project_id is rejected immediately (before queuing), not during job run.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .refactor_extract_superclass import ExtractSuperclassMCPCommand
from .refactor_split_class import SplitClassMCPCommand
from .refactor_split_file_to_package import SplitFileToPackageMCPCommand

__all__ = [
    "ExtractSuperclassMCPCommand",
    "SplitClassMCPCommand",
    "SplitFileToPackageMCPCommand",
]
