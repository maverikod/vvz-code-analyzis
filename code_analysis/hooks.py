"""
Command registration hooks for code-analysis-server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# Import patch for CommandExecutionJob to support progress tracking
# This must be imported before CommandExecutionJob is used
from .core.command_execution_job_patch import patch_command_execution_job  # noqa: F401

from mcp_proxy_adapter.commands.hooks import register_custom_commands_hook
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.hooks import register_auto_import_module

from .hooks_register_part1 import register_commands_part1
from .hooks_register_part2 import register_commands_part2


def register_code_analysis_commands(reg: registry) -> None:
    """Register all code analysis commands.

    Args:
        reg: MCP command registry instance.

    Returns:
        None
    """
    register_commands_part1(reg)
    register_commands_part2(reg)


# Register hook
register_custom_commands_hook(register_code_analysis_commands)

# Register modules for auto-import in child processes (spawn mode).
# Patch must be imported in the worker so CommandExecutionJob.run is patched and
# context["progress_tracker"] is set; otherwise progress/description never update.
register_auto_import_module("code_analysis.core.command_execution_job_patch")
register_auto_import_module("code_analysis.core.shared_database_spawn_init")
register_auto_import_module("code_analysis.commands.check_vectors_command")
register_auto_import_module("code_analysis.commands.list_cst_blocks_command")
register_auto_import_module("code_analysis.commands.query_cst_command")
register_auto_import_module("code_analysis.commands.cst_load_file_command")
register_auto_import_module("code_analysis.commands.cst_modify_tree_command")
register_auto_import_module("code_analysis.commands.cst_save_tree_command")
register_auto_import_module("code_analysis.commands.cst_reload_tree_command")
register_auto_import_module("code_analysis.commands.cst_find_node_command")
register_auto_import_module("code_analysis.commands.cst_get_node_info_command")
register_auto_import_module("code_analysis.commands.cst_get_node_by_range_command")
register_auto_import_module("code_analysis.commands.cst_create_file_command")
register_auto_import_module("code_analysis.commands.cst_convert_and_save_command")
register_auto_import_module("code_analysis.commands.cst_unload_tree_command")
register_auto_import_module("code_analysis.commands.cst_list_trees_command")
register_auto_import_module("code_analysis.commands.ast_mcp_commands")
register_auto_import_module("code_analysis.commands.fs_grep_command")
register_auto_import_module("code_analysis.commands.fs_copy_move_remove_commands")
register_auto_import_module("code_analysis.commands.project_fs_enumerate")
register_auto_import_module("code_analysis.commands.vector_commands")
register_auto_import_module("code_analysis.commands.semantic_search_mcp")
register_auto_import_module("code_analysis.commands.refactor_mcp_commands")
register_auto_import_module("code_analysis.commands.code_quality_commands")
register_auto_import_module("code_analysis.commands.analyze_complexity_mcp")
register_auto_import_module("code_analysis.commands.find_duplicates_mcp")
register_auto_import_module("code_analysis.commands.comprehensive_analysis_mcp")
register_auto_import_module("code_analysis.commands.search_mcp_commands")
register_auto_import_module("code_analysis.commands.code_mapper_mcp_command")
register_auto_import_module("code_analysis.commands.backup_mcp_commands")
register_auto_import_module("code_analysis.commands.file_management_mcp_commands")
register_auto_import_module("code_analysis.commands.log_viewer_mcp_commands")
register_auto_import_module("code_analysis.commands.worker_status_mcp_commands")
register_auto_import_module("code_analysis.commands.repair_worker_mcp_commands")
register_auto_import_module("code_analysis.commands.worker_management_mcp_commands")
register_auto_import_module("code_analysis.commands.database_integrity_mcp_commands")
register_auto_import_module("code_analysis.commands.database_restore_mcp_commands")
register_auto_import_module("code_analysis.commands.project_management_mcp_commands")
register_auto_import_module("code_analysis.commands.run_project_script_command")
register_auto_import_module("code_analysis.commands.run_project_module_command")
register_auto_import_module("code_analysis.commands.project_pip_commands")
register_auto_import_module("code_analysis.commands.read_project_text_file_command")
register_auto_import_module("code_analysis.commands.universal_file_read_command")
register_auto_import_module(
    "code_analysis.commands.project_file_transfer_by_id_commands"
)
register_auto_import_module(
    "code_analysis.commands.project_file_advisory_lock_batch_command"
)
register_auto_import_module("code_analysis.commands.project_file_lock_status_command")
register_auto_import_module("code_analysis.commands.universal_file_save_command")
register_auto_import_module("code_analysis.commands.universal_file_replace_command")
register_auto_import_module("code_analysis.commands.universal_file_delete_command")
register_auto_import_module("code_analysis.commands.write_project_text_lines_command")
register_auto_import_module("code_analysis.commands.json_load_file_command")
register_auto_import_module("code_analysis.commands.json_modify_tree_command")
register_auto_import_module("code_analysis.commands.json_save_tree_command")
register_auto_import_module("code_analysis.commands.json_reload_tree_command")
register_auto_import_module("code_analysis.commands.json_find_node_command")
register_auto_import_module("code_analysis.commands.json_get_node_info_command")
register_auto_import_module("code_analysis.commands.list_json_blocks_command")
register_auto_import_module("code_analysis.commands.qa_sleep_command")
register_auto_import_module("code_analysis.core.transfer_lock_registry")
