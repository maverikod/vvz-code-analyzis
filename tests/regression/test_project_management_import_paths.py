"""
Regression tests for import-path stability in project management MCP modules.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""


def test_project_management_mcp_modules_import_successfully() -> None:
    """Import target modules directly and assert successful import."""
    import code_analysis.commands.project_management_mcp_commands.change_project_id as change_project_id_module
    import code_analysis.commands.project_management_mcp_commands.delete_project as delete_project_module
    import code_analysis.commands.project_management_mcp_commands.delete_unwatched_projects as delete_unwatched_projects_module
    import code_analysis.commands.project_management_mcp_commands.list_projects as list_projects_module
    import code_analysis.commands.project_management_mcp_commands.list_trashed_projects as list_trashed_projects_module
    import code_analysis.commands.project_management_mcp_commands.permanently_delete_from_trash as permanently_delete_from_trash_module
    import code_analysis.commands.project_management_mcp_commands.restore_project_from_trash as restore_project_from_trash_module

    assert list_trashed_projects_module is not None
    assert permanently_delete_from_trash_module is not None
    assert restore_project_from_trash_module is not None
    assert delete_project_module is not None
    assert delete_unwatched_projects_module is not None
    assert change_project_id_module is not None
    assert list_projects_module is not None
