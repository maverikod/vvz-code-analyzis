"""
UniversalFileCloseCommand: ends an editing session with group-specific cleanup.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.universal_file_edit.errors import (
    SESSION_NOT_FOUND,
    error_result_from_make_error,
    make_error,
)
from code_analysis.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TEXT,
    FORMAT_TREE_TEMP,
    delete_lockfile,
    read_lockfile_pid,
)
from code_analysis.commands.universal_file_edit.session import (
    EditSession,
    get_session,
    release_session,
)
from code_analysis.commands.universal_file_edit.close_command_metadata import (
    get_universal_file_close_metadata,
)


class UniversalFileCloseCommand(BaseMCPCommand):
    """MCP command that ends a session with format-group-specific cleanup.

    Sidecar: verify checksum; rebuild on mismatch; never delete sidecar.
    Tree-temp: sha256 compare draft vs original; delete or rebuild draft; free tree.
    Text: delete draft unconditionally.
    Lockfile deleted in all cases.
    """

    name = "universal_file_close"

    version = "1.0.0"

    descr = "End a universal file edit session with format-group-specific cleanup."

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
        return "universal_file_close"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict describing project_id and session_id.
        """
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["project_id", "session_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["UniversalFileCloseCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for universal_file_close.

        Returns:
            Metadata dict with description, parameters, examples, errors.
        """
        return cast(Dict[str, Any], get_universal_file_close_metadata(cls))

    async def execute(  # type: ignore[override]
        self,
        project_id: str,
        session_id: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the close command.

        Args:
            project_id: Required by schema; session record is authoritative for paths.
            session_id: Active session identifier.
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with cleanup details, or ErrorResult on session not found.
        """
        _ = project_id  # required by schema; session record is authoritative for paths
        _ = kwargs
        try:
            session = get_session(session_id)
        except ValueError:
            return error_result_from_make_error(
                make_error(SESSION_NOT_FOUND, f"Unknown session: {session_id}")
            )
        payload: Dict[str, Any] = {"success": True}
        fg = session.format_group
        if fg == FORMAT_SIDECAR:
            payload = self._close_sidecar(session)
        else:
            payload = self._close_tree_temp_or_text(session)
        # Delete lockfile only if it belongs to this session.
        lock = read_lockfile_pid(session.abs_path)
        if lock is None or lock[1] == session.session_id:
            delete_lockfile(session.abs_path)
        release_session(session_id)
        return SuccessResult(data=payload)

    def _close_sidecar(self, session: EditSession) -> Dict[str, Any]:
        """Close a sidecar group session.

        Verifies sidecar checksum. On mismatch rebuilds sidecar from source.
        Sidecar is never deleted.

        Args:
            session: Active sidecar group EditSession.

        Returns:
            Dict with success=True and draft_rebuilt flag.
        """
        from code_analysis.core.cst_tree import tree_builder as cst_builder
        from code_analysis.core.cst_tree.tree_sidecar import (
            read_sidecar_payload,
            verify_sidecar_against_source,
            write_sidecar_atomic,
        )

        tree = cst_builder.load_file_to_tree(str(session.abs_path))
        payload = read_sidecar_payload(session.abs_path)
        if payload is not None and verify_sidecar_against_source(
            tree.module.code, payload
        ):
            return {"success": True, "draft_rebuilt": False}
        write_sidecar_atomic(session.abs_path, tree)
        return {"success": True, "draft_rebuilt": True}

    def _close_tree_temp_or_text(self, session: EditSession) -> Dict[str, Any]:
        """Close a tree-temp or text group session.

        Args:
            session: Active tree-temp or text group EditSession.

        Returns:
            Dict with success=True and draft_rebuilt flag.
        """
        fg = session.format_group
        abs_path = session.abs_path

        if fg == FORMAT_TEXT:
            session.draft_path.unlink(missing_ok=True)
            return {"success": True, "draft_rebuilt": False}

        if fg == FORMAT_TREE_TEMP and session.tree_temp_roots is not None:
            session.draft_path.unlink(missing_ok=True)
            session.tree_temp_roots = None
            draft_rebuilt = False
        else:
            draft_rebuilt = False
            if session.draft_path.exists():
                draft_sha = hashlib.sha256(session.draft_path.read_bytes()).hexdigest()
                orig_sha = hashlib.sha256(abs_path.read_bytes()).hexdigest()
                if draft_sha == orig_sha:
                    session.draft_path.unlink(missing_ok=True)
                else:
                    if session.handler_id == "json":
                        import json

                        from code_analysis.core.json_tree import (
                            tree_builder as json_builder,
                        )

                        loaded_json = json_builder.load_file_to_tree(str(abs_path))
                        draft_text = (
                            json.dumps(
                                loaded_json.root_data,
                                indent=2,
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                        session.draft_path.write_text(draft_text, encoding="utf-8")
                        json_builder.remove_tree(loaded_json.tree_id)
                    else:
                        import yaml

                        from code_analysis.core.yaml_tree import (
                            tree_builder as yaml_builder,
                        )

                        loaded_yaml = yaml_builder.load_file_to_tree(str(abs_path))
                        draft_text = yaml.safe_dump(
                            loaded_yaml.root_data,
                            default_flow_style=False,
                            allow_unicode=True,
                            sort_keys=False,
                        )
                        session.draft_path.write_text(draft_text, encoding="utf-8")
                        yaml_builder.remove_tree(loaded_yaml.tree_id)
                    draft_rebuilt = True

        if session.tree_id:
            if session.handler_id == "json":
                from code_analysis.core.json_tree import tree_builder as json_builder

                json_builder.remove_tree(session.tree_id)
            else:
                from code_analysis.core.yaml_tree import tree_builder as yaml_builder

                yaml_builder.remove_tree(session.tree_id)

        return {"success": True, "draft_rebuilt": draft_rebuilt}
