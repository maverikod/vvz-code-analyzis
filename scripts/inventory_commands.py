#!/usr/bin/env python3
"""
Command inventory script.

Checks all MCP commands registration and availability.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import importlib
import traceback
from typing import Dict, List, Set

# Expected commands from hooks.py
EXPECTED_CST_COMMANDS = [
    "compose_cst_module",
    "list_cst_blocks",
    "query_cst",
]

# Commands that should be registered
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


def check_command_files() -> Dict[str, bool]:
    """Check if command files exist."""
    results: Dict[str, bool] = {}
    commands_dir = project_root / "code_analysis" / "commands"

    # Check CST commands
    cst_files = {
        "compose_cst_module": commands_dir / "cst_compose_module_command.py",
        "list_cst_blocks": commands_dir / "list_cst_blocks_command.py",
        "query_cst": commands_dir / "query_cst_command.py",
    }

    for cmd_name, file_path in cst_files.items():
        results[cmd_name] = file_path.exists()
        if not results[cmd_name]:
            print(f"❌ Missing file: {file_path}")

    return results


def check_command_imports() -> Dict[str, bool]:
    """Check if commands can be imported."""
    results: Dict[str, bool] = {}

    # Try to import CST commands
    try:
        from code_analysis.commands.cst_compose_module_command import (
            ComposeCSTModuleCommand,
        )

        results["compose_cst_module"] = True
        print("✅ compose_cst_module: import successful")
    except ImportError as e:
        results["compose_cst_module"] = False
        print(f"❌ compose_cst_module: import failed - {e}")

    try:
        from code_analysis.commands.list_cst_blocks_command import (
            ListCSTBlocksCommand,
        )

        results["list_cst_blocks"] = True
        print("✅ list_cst_blocks: import successful")
    except ImportError as e:
        results["list_cst_blocks"] = False
        print(f"❌ list_cst_blocks: import failed - {e}")

    try:
        from code_analysis.commands.query_cst_command import QueryCSTCommand

        results["query_cst"] = True
        print("✅ query_cst: import successful")
    except ImportError as e:
        results["query_cst"] = False
        print(f"❌ query_cst: import failed - {e}")

    return results


def check_hooks_registration() -> Dict[str, bool]:
    """Check if commands are registered in hooks.py."""
    results: Dict[str, bool] = {}
    hooks_file = project_root / "code_analysis" / "hooks.py"

    if not hooks_file.exists():
        print(f"❌ hooks.py not found: {hooks_file}")
        return results

    content = hooks_file.read_text(encoding="utf-8")

    # Check CST commands registration
    cst_checks = {
        "compose_cst_module": "ComposeCSTModuleCommand" in content
        and "reg.register(ComposeCSTModuleCommand" in content,
        "list_cst_blocks": "ListCSTBlocksCommand" in content
        and "reg.register(ListCSTBlocksCommand" in content,
        "query_cst": "QueryCSTCommand" in content
        and "reg.register(QueryCSTCommand" in content,
    }

    for cmd_name, found in cst_checks.items():
        results[cmd_name] = found
        if found:
            print(f"✅ {cmd_name}: registered in hooks.py")
        else:
            print(f"❌ {cmd_name}: NOT registered in hooks.py")

    return results


def main():
    """Run command inventory."""
    print("=" * 80)
    print("Command Inventory Check")
    print("=" * 80)
    print()

    print("1. Checking command files...")
    file_results = check_command_files()
    print()

    print("2. Checking command imports...")
    import_results = check_command_imports()
    print()

    print("3. Checking hooks.py registration...")
    hooks_results = check_hooks_registration()
    print()

    print("=" * 80)
    print("Summary")
    print("=" * 80)

    all_commands = set(file_results.keys()) | set(import_results.keys()) | set(
        hooks_results.keys()
    )

    for cmd in sorted(all_commands):
        file_ok = file_results.get(cmd, False)
        import_ok = import_results.get(cmd, False)
        hooks_ok = hooks_results.get(cmd, False)

        status = "✅" if (file_ok and import_ok and hooks_ok) else "❌"
        print(
            f"{status} {cmd}: file={file_ok}, import={import_ok}, hooks={hooks_ok}"
        )

    # Check if all CST commands are available
    cst_missing = [
        cmd
        for cmd in EXPECTED_CST_COMMANDS
        if not (
            file_results.get(cmd, False)
            and import_results.get(cmd, False)
            and hooks_results.get(cmd, False)
        )
    ]

    if cst_missing:
        print()
        print("⚠️  Missing CST commands:", ", ".join(cst_missing))
        return 1
    else:
        print()
        print("✅ All CST commands are available")
        return 0


if __name__ == "__main__":
    sys.exit(main())

