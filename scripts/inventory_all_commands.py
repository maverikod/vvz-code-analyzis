#!/usr/bin/env python3
"""
Command inventory script - finds ALL commands in the project.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import sys
import ast
import importlib.util
from pathlib import Path
from typing import Dict, List, Set, Any
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def parse_hooks_file() -> Dict[str, List[str]]:
    """Parse hooks.py to extract registered commands."""
    hooks_file = project_root / "code_analysis" / "hooks.py"
    commands_by_group = defaultdict(list)
    
    with open(hooks_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Parse the file
    tree = ast.parse(content)
    
    # Find all reg.register() calls
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if (isinstance(node.func, ast.Attribute) and 
                isinstance(node.func.value, ast.Name) and
                node.func.value.id == "reg" and
                node.func.attr == "register"):
                if len(node.args) >= 1:
                    if isinstance(node.args[0], ast.Name):
                        command_class = node.args[0].id
                        # Try to infer command name from class name
                        # Remove "MCPCommand" or "Command" suffix
                        if command_class.endswith("MCPCommand"):
                            cmd_name = command_class[:-11].lower()
                            # Convert CamelCase to snake_case
                            cmd_name = "".join(
                                "_" + c.lower() if c.isupper() else c
                                for c in cmd_name
                            ).lstrip("_")
                        elif command_class.endswith("Command"):
                            cmd_name = command_class[:-7].lower()
                            cmd_name = "".join(
                                "_" + c.lower() if c.isupper() else c
                                for c in cmd_name
                            ).lstrip("_")
                        else:
                            cmd_name = command_class.lower()
                        
                        # Group by file location (infer from import)
                        commands_by_group["registered"].append({
                            "class": command_class,
                            "name": cmd_name,
                        })
    
    return commands_by_group


def find_command_files() -> Dict[str, List[Path]]:
    """Find all command files in the project."""
    commands_dir = project_root / "code_analysis" / "commands"
    command_files = defaultdict(list)
    
    # Find all Python files in commands directory
    for py_file in commands_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        
        # Skip test files
        if "test" in py_file.name.lower():
            continue
        
        # Determine group by directory structure
        rel_path = py_file.relative_to(commands_dir)
        if len(rel_path.parts) == 1:
            # Top-level command file
            group = "top_level"
        else:
            # Subdirectory
            group = rel_path.parts[0]
        
        command_files[group].append(py_file)
    
    return command_files


def extract_commands_from_file(file_path: Path) -> List[Dict[str, Any]]:
    """Extract command classes from a Python file."""
    commands = []
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check if it's a command class
                bases = [base.id for base in node.bases if isinstance(base, ast.Name)]
                
                # Check for Command base class
                is_command = any(
                    "Command" in base or base == "Command" 
                    for base in bases
                )
                
                if is_command:
                    # Try to find command name attribute
                    cmd_name = None
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            for target in item.targets:
                                if isinstance(target, ast.Name) and target.id == "name":
                                    if isinstance(item.value, ast.Constant):
                                        cmd_name = item.value.value
                    
                    # If no name attribute, infer from class name
                    if not cmd_name:
                        class_name = node.name
                        if class_name.endswith("MCPCommand"):
                            cmd_name = class_name[:-11]
                            # Convert CamelCase to snake_case
                            cmd_name = "".join(
                                "_" + c.lower() if c.isupper() else c
                                for c in cmd_name
                            ).lstrip("_")
                        elif class_name.endswith("Command"):
                            cmd_name = class_name[:-7]
                            cmd_name = "".join(
                                "_" + c.lower() if c.isupper() else c
                                for c in cmd_name
                            ).lstrip("_")
                        else:
                            cmd_name = class_name.lower()
                    
                    commands.append({
                        "class": node.name,
                        "name": cmd_name,
                        "file": str(file_path.relative_to(project_root)),
                    })
    except Exception as e:
        print(f"Error parsing {file_path}: {e}", file=sys.stderr)
    
    return commands


def get_standard_adapter_commands() -> Set[str]:
    """Get list of standard adapter commands (from mcp_proxy_adapter)."""
    # These are standard commands provided by the adapter
    return {
        "echo",
        "long_task",
        "job_status",
        "help",
        "health",
        "config",
        "reload",
        "settings",
        "load",
        "unload",
        "plugins",
        "transport_management",
        "proxy_registration",
        "roletest",
        "queue_add_job",
        "queue_start_job",
        "queue_stop_job",
        "queue_delete_job",
        "queue_get_job_status",
        "queue_get_job_logs",
        "queue_list_jobs",
        "queue_health",
    }


def main():
    """Main function."""
    print("🔍 Conducting command inventory...")
    
    # Get registered commands from hooks.py
    registered_commands = parse_hooks_file()
    
    # Find all command files
    command_files = find_command_files()
    
    # Extract commands from files
    all_commands = defaultdict(list)
    
    for group, files in command_files.items():
        for file_path in files:
            commands = extract_commands_from_file(file_path)
            for cmd in commands:
                cmd["group"] = group
                all_commands[group].append(cmd)
    
    # Get standard adapter commands
    standard_commands = get_standard_adapter_commands()
    
    # Organize commands by category
    categories = {
        "CST Commands": ["compose_cst_module", "list_cst_blocks", "query_cst"],
        "AST Commands": [
            "get_ast", "search_ast_nodes", "ast_statistics", "list_project_files",
            "get_code_entity_info", "list_code_entities", "get_imports",
            "find_dependencies", "get_class_hierarchy", "find_usages", "export_graph"
        ],
        "Search Commands": [
            "semantic_search", "fulltext_search", "find_classes", "list_class_methods"
        ],
        "Vector Operations": ["rebuild_faiss", "revectorize"],
        "Code Quality": ["format_code", "lint_code", "type_check_code"],
        "Refactoring": [
            "split_class", "extract_superclass", "split_file_to_package"
        ],
        "Code Analysis": [
            "update_indexes", "analyze_complexity", "find_duplicates", "comprehensive_analysis"
        ],
        "Database Management": [
            "restore_database", "get_database_status", "repair_database",
            "get_database_corruption_status", "backup_database", "repair_sqlite_database"
        ],
        "Project Management": ["change_project_id"],
        "File Management": [
            "cleanup_deleted_files", "unmark_deleted_file", "collapse_versions"
        ],
        "Backup Management": [
            "list_backup_files", "list_backup_versions", "restore_backup_file",
            "delete_backup", "clear_all_backups"
        ],
        "Worker Management": [
            "start_worker", "stop_worker", "get_worker_status",
            "start_repair_worker", "stop_repair_worker", "repair_worker_status"
        ],
        "Log Management": [
            "view_worker_logs", "list_worker_logs"
        ],
    }
    
    # Collect all custom commands
    custom_commands = set()
    for group_commands in all_commands.values():
        for cmd in group_commands:
            if cmd["name"] not in standard_commands:
                custom_commands.add(cmd["name"])
    
    # Add registered commands
    for cmd_info in registered_commands.get("registered", []):
        if cmd_info["name"] not in standard_commands:
            custom_commands.add(cmd_info["name"])
    
    # Write inventory to file
    output_file = project_root / "docs" / "COMMAND_INVENTORY.md"
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Command Inventory\n\n")
        f.write("Author: Vasiliy Zdanovskiy\n")
        f.write("email: vasilyvz@gmail.com\n\n")
        f.write("## Overview\n\n")
        f.write("This document lists all custom commands available in the code-analysis-server.\n")
        f.write("Standard adapter commands (echo, health, queue_*, etc.) are excluded.\n\n")
        
        f.write(f"**Total custom commands**: {len(custom_commands)}\n\n")
        
        f.write("## Commands by Category\n\n")
        
        # Group commands by category
        commands_by_category = defaultdict(list)
        uncategorized = []
        
        for cmd_name in sorted(custom_commands):
            categorized = False
            for category, cmd_list in categories.items():
                if cmd_name in cmd_list:
                    commands_by_category[category].append(cmd_name)
                    categorized = True
                    break
            if not categorized:
                uncategorized.append(cmd_name)
        
        # Write categorized commands
        for category in sorted(commands_by_category.keys()):
            f.write(f"### {category}\n\n")
            for cmd_name in sorted(commands_by_category[category]):
                f.write(f"- `{cmd_name}`\n")
            f.write("\n")
        
        # Write uncategorized commands
        if uncategorized:
            f.write("### Uncategorized Commands\n\n")
            for cmd_name in sorted(uncategorized):
                f.write(f"- `{cmd_name}`\n")
            f.write("\n")
        
        # Write command files by group
        f.write("## Command Files by Group\n\n")
        for group in sorted(command_files.keys()):
            f.write(f"### {group}\n\n")
            for file_path in sorted(command_files[group]):
                rel_path = file_path.relative_to(project_root)
                f.write(f"- `{rel_path}`\n")
            f.write("\n")
    
    print(f"✅ Inventory written to: {output_file}")
    print(f"   Total custom commands found: {len(custom_commands)}")
    print(f"   Standard adapter commands excluded: {len(standard_commands)}")


if __name__ == "__main__":
    main()

