"""
UniversalFileEditCommand: applies a batch of mutations to the draft.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.universal_file_edit.edit_command_metadata import (
    get_universal_file_edit_metadata,
)
from code_analysis.commands.universal_file_edit.errors import (
    SESSION_NOT_FOUND,
    error_result_from_make_error,
    make_error,
)
from code_analysis.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TREE_TEMP,
)
from code_analysis.commands.universal_file_edit.invalid_write_support import (
    invalid_session_warning,
)
from code_analysis.commands.universal_file_edit.session import EditSession, get_session
from code_analysis.commands.universal_file_edit.sidecar_cst_apply import (
    run_sidecar_cst_edit_batch,
    validate_sidecar_nested_batch,
)
from code_analysis.commands.universal_file_edit.text_draft_apply import (
    run_text_draft_apply,
)
from code_analysis.commands.universal_file_edit import tree_temp_edit_batch


class UniversalFileEditCommand(BaseMCPCommand):
    """MCP command that applies a batch of mutation operations to the draft.

    The original file is never touched. For sidecar group, ancestor-descendant
    pairs in the batch are rejected atomically with NESTED_BATCH_FORBIDDEN.
    """

    name = "universal_file_edit"

    version = "1.0.0"

    descr = "Apply a batch of universal file edit operations to the session draft."

    category = "file_management"

    author = "Vasiliy Zdanovskiy"

    email = "vasilyvz@gmail.com"

    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name.

        Returns:
            MCP command name string.
        """
        return "universal_file_edit"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict describing project_id, session_id, operations.
        """
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID. Use list_projects to discover valid values.",
                },
                "session_id": {
                    "type": "string",
                    "description": "Active session UUID returned by universal_file_open.",
                },
                "operations": {
                    "type": "array",
                    "description": (
                        "Batch of edit operations. Shape must match universal_file_preview "
                        "node_ref: Python .py uses {type,node_id,code_lines}; "
                        "JSON/YAML uses {type,json_pointer,value}; "
                        "text/markdown uses {type,node_ref,content} or line ranges only "
                        "when preview or is_invalid fallback requires it."
                    ),
                    "items": {"type": "object"},
                },
            },
            "required": ["project_id", "session_id", "operations"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["UniversalFileEditCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for universal_file_edit.

        Returns:
            Metadata dict with description, parameters, examples, errors.
        """
        return cast(Dict[str, Any], get_universal_file_edit_metadata(cls))

    async def execute(  # type: ignore[override]
        self,
        project_id: str,
        session_id: str,
        operations: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the edit command.

        Args:
            project_id: Project UUID (validated by handler; reserved for future checks).
            session_id: Active session identifier.
            operations: Batch of edit operation dicts.
            **kwargs: Adapter context.

        Returns:
            SuccessResult with payload, or ErrorResult on failure.
        """
        del project_id, kwargs
        try:
            session = get_session(session_id)
        except ValueError:
            return error_result_from_make_error(
                make_error(SESSION_NOT_FOUND, f"Unknown session: {session_id}")
            )

        fg = session.format_group
        if fg == FORMAT_SIDECAR:
            validation = validate_sidecar_nested_batch(operations, session.tree_id)
            if validation is not None:
                return error_result_from_make_error(validation)
            result = await self._apply_sidecar(session, operations)
        elif fg == FORMAT_TREE_TEMP:
            result = await self._apply_tree_temp(session, operations)
        else:
            result = await self._apply_text(session, operations)

        if session.is_invalid and isinstance(result, SuccessResult):
            payload = dict(result.data)
            payload["warning"] = invalid_session_warning(session)
            return SuccessResult(data=payload)
        return result

    async def _apply_sidecar(
        self, session: EditSession, operations: List[Dict[str, Any]]
    ) -> SuccessResult | ErrorResult:
        """Apply sidecar group operations via CST ``modify_tree`` and refresh sidecar.

        Each operation runs in isolation: resolve ``stable_id`` against the current
        tree, ``modify_tree`` with one op (stable_id transfer via ``_build_tree_index``),
        then ``write_sidecar_atomic``. On any failure the batch rolls back to the
        pre-batch tree and sidecar snapshot.

        Args:
            session: Active EditSession.
            operations: List of validated edit operation dicts.

        Returns:
            SuccessResult with success/update flags, or ErrorResult on failure.
        """
        return await asyncio.to_thread(run_sidecar_cst_edit_batch, session, operations)

    async def _apply_tree_temp(
        self, session: EditSession, operations: List[Dict[str, Any]]
    ) -> SuccessResult | ErrorResult:
        """Apply tree-temp group operations to the draft via JSON/YAML pipelines.

        For each operation, updates the registered in-memory tree, then serializes
        the tree to ``session.draft_path``.

        Args:
            session: Active EditSession with tree_id and draft_path.
            operations: Edit operation dicts (``type``/``action``, addresses, values).

        Returns:
            SuccessResult with ``success``/``updated`` flags, or ErrorResult on failure.
        """
        return await asyncio.to_thread(
            tree_temp_edit_batch.apply_tree_temp_mutations,
            session,
            operations,
        )

    async def _apply_text(
        self, session: EditSession, operations: List[Dict[str, Any]]
    ) -> SuccessResult | ErrorResult:
        """Apply text edits to ``session.draft_path`` sorted bottom-up."""

        return await asyncio.to_thread(run_text_draft_apply, session, operations)
