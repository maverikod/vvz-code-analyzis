#!/usr/bin/env python3
"""
Check all MCP commands availability.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mcp_MCP_Proxy_2 import list_servers, call_server

# Expected commands from hooks.py
EXPECTED_COMMANDS = {
    # CST commands
    "compose_cst_module",
    "list_cst_blocks",
    "query_cst",
    # AST commands
    "get_ast",
    "search_ast_nodes",
    "ast_statistics",
    "list_project_files",
    "get_code_entity_info",
    "list_code_entities",
    "get_imports",
    "find_dependencies",
    "get_class_hierarchy",
    "find_usages",
    "export_graph",
    # Vector commands
    "rebuild_faiss",
    "revectorize",
    # Search commands
    "semantic_search",
    "fulltext_search",
    "find_classes",
    "list_class_methods",
    # Code quality
    "format_code",
    "lint_code",
    "type_check_code",
    # Refactoring
    "split_class",
    "extract_superclass",
    "split_file_to_package",
    # Database
    "restore_database",
    "update_indexes",
    # Project management
    "change_project_id",
    # Workers
    "start_worker",
    "stop_worker",
    "get_worker_status",
    # File management
    "cleanup_deleted_files",
    "unmark_deleted_file",
    "collapse_versions",
    "repair_database",
    # Backup
    "list_backup_files",
    "list_backup_versions",
    "restore_backup_file",
    "delete_backup",
    "clear_all_backups",
    # Logs
    "view_worker_logs",
    "list_worker_logs",
    "get_database_status",
}


def main():
    """Check all commands."""
    print("=" * 80)
    print("MCP Commands Availability Check")
    print("=" * 80)
    print()

    # Get server info
    servers_result = list_servers(page=1, page_size=10)
    if not servers_result.get("servers"):
        print("❌ No servers found")
        return 1

    code_analysis_server = None
    for server in servers_result["servers"]:
        if server["server_id"] == "code-analysis-server":
            code_analysis_server = server
            break

    if not code_analysis_server:
        print("❌ code-analysis-server not found")
        return 1

    print(f"✅ Found server: {code_analysis_server['server_id']}")
    print(f"   Commands available: {code_analysis_server['command_count']}")
    print()

    # Get available commands
    available_commands = set(code_analysis_server["commands"].keys())

    print("Checking commands...")
    print()

    missing = []
    found = []

    for cmd in sorted(EXPECTED_COMMANDS):
        if cmd in available_commands:
            found.append(cmd)
            print(f"✅ {cmd}")
        else:
            missing.append(cmd)
            print(f"❌ {cmd} - NOT FOUND")

    print()
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"Total expected: {len(EXPECTED_COMMANDS)}")
    print(f"Found: {len(found)}")
    print(f"Missing: {len(missing)}")

    if missing:
        print()
        print("Missing commands:")
        for cmd in missing:
            print(f"  - {cmd}")

    # Check CST commands specifically
    cst_commands = ["compose_cst_module", "list_cst_blocks", "query_cst"]
    cst_missing = [cmd for cmd in cst_commands if cmd not in available_commands]

    if cst_missing:
        print()
        print("⚠️  CST commands missing:", ", ".join(cst_missing))
        return 1
    else:
        print()
        print("✅ All CST commands are available")

    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())

