"""
MCP command: list_watch_dirs.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from ._shared import (
    Any,
    BaseMCPCommand,
    Dict,
    ErrorResult,
    Optional,
    SuccessResult,
    logger,
)


class ListWatchDirsMCPCommand(BaseMCPCommand):
    """
    List all watch directories with their IDs and paths.

    Allows models without project source code to discover watch_dir_id
    for create_project (e.g. call help('list_watch_dirs'), then call_server,
    then use returned id in create_project).
    """

    name = "list_watch_dirs"
    version = "1.0.0"
    descr = "List watch directories (id and path) for use with create_project"
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(
        cls: type["ListWatchDirsMCPCommand"],
    ) -> Dict[str, Any]:
        return {
            "type": "object",
            "description": (
                "List all watch directories. Returns id (use as watch_dir_id in create_project) "
                "and absolute_path. Database path is resolved from server config."
            ),
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: type["ListWatchDirsMCPCommand"]) -> Dict[str, Any]:
        from ..zero_arg_commands_metadata import list_watch_dirs_metadata

        return list_watch_dirs_metadata(cls)

    async def execute(
        self: "ListWatchDirsMCPCommand",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        try:
            database = self._open_database_from_config(auto_analyze=False)
            try:
                items = database.list_watch_dirs_with_paths()
                return SuccessResult(
                    data={"watch_dirs": items, "count": len(items)},
                    message=f"Found {len(items)} watch directory(ies)",
                )
            finally:
                database.disconnect()
        except Exception as e:
            return self._handle_error(e, "LIST_WATCH_DIRS_ERROR", "list_watch_dirs")
