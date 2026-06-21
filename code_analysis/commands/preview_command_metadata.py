"""
Metadata for universal_file_preview command (AI/docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type


def get_universal_file_preview_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return command metadata dict for universal_file_preview.

    Args:
        cls: The command class (UniversalFilePreviewCommand).

    Returns:
        Metadata dict with description, parameters, examples, errors.
    """
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Read-only structured preview of any project file node.\n\n"
            "Works without an edit session. Supports .py, .json, .yaml, .yml, .md, .txt,\n"
            "  .rst, .adoc, .jsonl, .ndjson. Does not modify files, DB, or tree sessions.\n\n"
            "Navigation model:\n"
            "  Omit node_ref — get the file root.\n"
            "  Pass a node_ref from a previous response — drill into that node.\n"
            "  Each block in the response carries its own node_ref for further drill-down.\n\n"
            "Identifier model (all marked-tree formats: .py, .json, .yaml, .md, .txt, …):\n"
            "  API responses — positive integer short_id on focus.node_ref and blocks[].node_ref.\n"
            "  API requests  — integer short_id (canonical) or legacy string alias resolved via\n"
            "                  the ``.tree`` MAP (UUID4, JSON Pointer, markdown slug, decimal\n"
            "                  short_id string). Internal TreeNodeUuid lives in MAP only.\n\n"
            "selector parameter:\n"
            "  String slice (contains ':' or starts with '-'): '0:5', '-3:', '2:8'\n"
            "  list[int]: explicit block indices, e.g. [0, 2, 4]\n"
            "  list[str]: explicit block identifiers (node_ref values)\n"
            "  Omit: return first preview_lines blocks (default 20)\n\n"
            "full_text_max_lines (all formats, including degraded text):\n"
            "  When the file has fewer source lines than this threshold (default 200),\n"
            "  root preview returns annotated full source on focus and every tree node\n"
            "  in blocks. Applies to native .txt/.rst and to parse-error fallback when\n"
            "  JSON/YAML/Python cannot be parsed (is_invalid=True). Set to 0 for drilldown only.\n\n"
            "Parse-error fallback (is_invalid):\n"
            "  Unparseable files are previewed as text format (paragraph/line tree).\n"
            "  Use preview_offset/max_chars for envelope pagination; node_ref/selector\n"
            "  are rejected until the file parses again.\n\n"
            "Edit session integration:\n"
            "  Pass session_id from universal_file_open to preview the current draft\n"
            "  (in-memory CST tree for sidecar, tree_temp_roots for tree-temp, draft file for text).\n"
            "  This session_id is unrelated to client session commands (session_create, …)."
        ),
        "parameters": {
            "project_id": {
                "description": "Project UUID. Use list_projects to discover valid values.",
                "type": "string",
                "required": True,
                "examples": ["8772a086-688d-4198-a0c4-f03817cc0e6c"],
            },
            "file_path": {
                "description": "Project-relative path to one file. Literal path; no globs.",
                "type": "string",
                "required": True,
                "examples": [
                    "code_analysis/commands/my_command.py",
                    "config/settings.yaml",
                ],
            },
            "node_ref": {
                "description": (
                    "Drill-down identifier from a prior preview response. "
                    "All supported formats use marked-tree navigation: responses expose "
                    "positive integer ``short_id`` values; requests should pass the same "
                    "integer (or a legacy string alias resolved via the ``.tree`` MAP "
                    "section — UUID4, JSON Pointer, markdown slug). Omit for file root."
                ),
                "type": "integer | string",
                "required": False,
                "notes": (
                    "Canonical form is integer short_id. UUID4 is internal to MAP only."
                ),
            },
            "selector": {
                "description": (
                    "Subset of the focus node's blocks. "
                    "String slice (e.g. '0:5', '-3:'), list of int indices, or list of node_ref strings. "
                    "Omit to get the first preview_lines blocks."
                ),
                "type": "string | list[int] | list[str]",
                "required": False,
            },
            "preview_lines": {
                "description": "Max blocks returned when selector is omitted. Default 20.",
                "type": "integer",
                "required": False,
                "default": 20,
            },
            "value_preview_len": {
                "description": "Max character length for inline scalar previews. Default 120.",
                "type": "integer",
                "required": False,
                "default": 120,
            },
            "full_text_max_lines": {
                "description": (
                    "Per-format source-line threshold (not bytes). When the file has "
                    "fewer lines than this value, root preview returns annotated full "
                    "source on focus and lists every tree node (all descendants) in "
                    "blocks. Default 200. Set to 0 to disable (drilldown only)."
                ),
                "type": "integer",
                "required": False,
                "default": 200,
            },
            "session_id": {
                "description": (
                    "UUID from universal_file_open. When set, previews the current draft "
                    "(in-memory tree or draft file) rather than the on-disk source."
                ),
                "type": "string",
                "required": False,
            },
            "tree_id": {
                "description": "UUID of an existing in-memory TreeSession (legacy; prefer session_id).",
                "type": "string",
                "required": False,
            },
            "max_chars": {
                "description": (
                    "Invalid-source fallback only: max characters per preview_chunk page when "
                    "the file failed structural parse (is_invalid). Ignored when the file parses."
                ),
                "type": "integer",
                "required": False,
            },
            "preview_offset": {
                "description": (
                    "Invalid-source fallback only: character offset into serialized invalid-source "
                    "preview; use preview_next_offset from the prior page. Must be 0 for parseable "
                    "files (use node_ref / selector instead)."
                ),
                "type": "integer",
                "required": False,
                "default": 0,
            },
        },
        "return_value": {
            "success": {
                "description": "Preview returned without errors.",
                "data": {
                    "focus": "Metadata of the focus node: node_kind, node_ref, type, name, attributes, text.",
                    "blocks": "List of child block summaries, each with node_ref for drill-down.",
                    "total_blocks": "Total child count of the focus node (may exceed len(blocks) when selector limits output).",
                    "selector_applied": "The selector that was applied, or null when omitted.",
                },
                "example": {
                    "focus": {"node_kind": "mapping", "node_ref": 1},
                    "blocks": [{"node_kind": "scalar", "node_ref": 2}],
                    "total_blocks": 3,
                    "selector_applied": None,
                },
            },
            "error": {
                "description": "Preview failed.",
                "code": "Stable error code (see error_cases).",
                "message": "Human-readable description.",
            },
        },
        "usage_examples": [
            {
                "description": "Preview the root of a YAML file",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "file_path": "config/settings.yaml",
                },
                "explanation": (
                    "Returns the top-level keys as blocks. "
                    "Each block has an integer node_ref (short_id) for drill-down."
                ),
            },
            {
                "description": "Drill into a nested YAML key",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "file_path": "config/settings.yaml",
                    "node_ref": 2,
                },
                "explanation": (
                    "Pass integer short_id from a previous preview response. "
                    "Legacy input such as '/database' is also accepted and resolved via MAP."
                ),
            },
            {
                "description": "Preview a Python file (full-text for small files)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "file_path": "code_analysis/commands/my_command.py",
                    "full_text_max_lines": 300,
                },
                "explanation": (
                    "When the file has fewer than 300 source lines, root preview returns "
                    "annotated full source on focus and every tree node in blocks (int short_id). "
                    "Set full_text_max_lines=0 for drilldown-only on large files."
                ),
            },
        ],
        "error_cases": {
            "UNKNOWN_EXTENSION": {
                "description": "File extension not supported by any preview handler.",
                "solution": "Use a supported extension: .py, .json, .yaml, .yml, .md, .txt, .rst, .adoc, .jsonl.",
            },
            "UNKNOWN_NODE_REF": {
                "description": "node_ref (short_id or legacy alias) not found in the current file tree.",
                "solution": "Re-run preview without node_ref to get valid integer short_id values from the current file state.",
            },
            "REQUIRES_LINE_ADDRESSING": {
                "description": (
                    "File has parse errors (is_invalid). node_ref and selector are rejected until "
                    "syntax is fixed."
                ),
                "solution": (
                    "Use preview_offset and max_chars at file root only, or fix the file and "
                    "re-preview for integer short_id navigation."
                ),
            },
            "FILE_STRUCTURE_ERROR": {
                "description": "File could not be parsed (e.g. invalid JSON or YAML syntax).",
                "solution": "Fix the file syntax, or open it with universal_file_open which falls back to text mode.",
            },
            "GLOB_IN_FILE_PATH": {
                "description": "file_path contains glob characters (* ? [).",
                "solution": "Provide a single literal file path.",
            },
            "INVALID_SELECTOR_FORM": {
                "description": "Selector string does not contain ':' and does not start with '-'.",
                "solution": "Use slice syntax (e.g. '0:5', '-3:') or a list of indices/identifiers.",
            },
            "FILE_LOCKED": {
                "description": (
                    "File is locked by another universal_file_open edit session "
                    "(preview without session_id). universal_file_open returns PARSE_ERROR "
                    "for the same lock."
                ),
                "solution": (
                    "Pass the owning session_id from universal_file_open, or call "
                    "universal_file_close on that session."
                ),
            },
            "CONFLICTING_PARAMETERS": {
                "description": "Unknown or invalid session_id when resolving edit draft.",
                "solution": "Re-open the file with universal_file_open and use the new session_id.",
            },
            "HANDLER_ERROR": {
                "description": "Unexpected failure inside a preview handler.",
                "solution": "Retry; if persistent, check server logs and file content.",
            },
        },
        "best_practices": [
            "Call universal_file_preview before universal_file_edit to obtain valid integer short_id values.",
            "Responses always use integer node_ref (short_id); pass the same integer back for drill-down and edit.",
            "Legacy string aliases (JSON Pointer, MAP UUID4, markdown slug) are accepted on input only.",
            "Do not use MAP UUID4 from sidecar files — it is internal; preview never returns it.",
            "When is_invalid=True, use preview_offset/max_chars only; node_ref/selector return REQUIRES_LINE_ADDRESSING.",
            "Use full_text_max_lines=0 for drilldown-only; default 200 returns full annotated tree on small files.",
            "Pass session_id to preview the draft after edits but before commit.",
            "Use selector='0:N' to cap the response size for large files.",
        ],
    }
