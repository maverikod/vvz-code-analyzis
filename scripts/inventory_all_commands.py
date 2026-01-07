#!/usr/bin/env python3
"""
Command inventory script - finds ALL commands in the project using real registry.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import sys
from pathlib import Path
from typing import Dict, List, Set, Any
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def get_all_registered_commands() -> Dict[str, Dict[str, Any]]:
    """Get all registered commands from the real registry."""
    from mcp_proxy_adapter.commands.command_registry import CommandRegistry
    from code_analysis.hooks import register_code_analysis_commands
    
    # Create a fresh registry and register commands
    reg = CommandRegistry()
    register_code_analysis_commands(reg)
    
    # Get all commands from registry
    commands = {}
    for cmd_name, cmd_class in reg._commands.items():
        # Get command metadata
        category = getattr(cmd_class, "category", "uncategorized")
        commands[cmd_name] = {
            "name": cmd_name,
            "category": category,
            "class": cmd_class.__name__,
        }
    
    return commands


def get_standard_adapter_commands() -> Set[str]:
    """Get list of standard adapter commands (from mcp_proxy_adapter)."""
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


def map_category_to_display_name(category: str) -> str:
    """Map internal category to display name."""
    category_map = {
        "ast": "AST Commands",
        "cst": "CST Commands",
        "search": "Search Commands",
        "vector": "Vector Operations",
        "code_quality": "Code Quality",
        "refactoring": "Refactoring",
        "code_analysis": "Code Analysis",
        "database": "Database Management",
        "project_management": "Project Management",
        "file_management": "File Management",
        "backup": "Backup Management",
        "worker": "Worker Management",
        "log": "Log Management",
        "custom": "Custom Commands",
    }
    return category_map.get(category, category.replace("_", " ").title() + " Commands")


def main():
    """Main function."""
    print("🔍 Conducting command inventory using real registry...")
    
    # Get all registered commands from real registry
    all_commands = get_all_registered_commands()
    
    # Get standard adapter commands
    standard_commands = get_standard_adapter_commands()
    
    # Filter out standard commands
    custom_commands = {
        name: info
        for name, info in all_commands.items()
        if name not in standard_commands
    }
    
    # Group commands by category
    commands_by_category = defaultdict(list)
    for cmd_name, cmd_info in custom_commands.items():
        category = cmd_info.get("category", "uncategorized")
        display_category = map_category_to_display_name(category)
        commands_by_category[display_category].append(cmd_name)
    
    # Sort commands within each category
    for category in commands_by_category:
        commands_by_category[category].sort()
    
    # Find command files
    command_files = find_command_files()
    
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
        
        # Write categorized commands (sorted by category name)
        for category in sorted(commands_by_category.keys()):
            f.write(f"### {category}\n\n")
            for cmd_name in commands_by_category[category]:
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
    print(f"   Categories: {len(commands_by_category)}")


if __name__ == "__main__":
    main()
