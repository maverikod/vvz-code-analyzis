"""
Metadata for universal_file_edit command (AI/docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type


def get_universal_file_edit_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return command metadata dict for universal_file_edit.

    Args:
        cls: The command class (UniversalFileEditCommand).

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
            "Apply a batch of mutation operations to an open edit session draft.\n\n"
            "universal_file_edit is step 3 in the universal file edit workflow:\n"
            "  1. universal_file_open  — open a file (or create it), get session_id\n"
            "  2. universal_file_preview — obtain node_ref values from the current draft\n"
            "  3. universal_file_edit  — apply one or more operations to the in-memory draft\n"
            "  4. universal_file_write — first call: preview diff; second call: commit to disk\n"
            "  5. universal_file_close — release the session\n\n"
            "Operation shape uses integer short_id from universal_file_preview (all formats):\n\n"
            "Python (.py, .pyi, .pyw):\n"
            "  Preview returns integer short_id in node_ref. Pass the same integer in node_id,\n"
            "  target_node_id, or parent_node_id; the server maps short_id to CST stable_id via MAP.\n"
            "  Legacy MAP UUID4 strings are still accepted on input.\n"
            "  Fields: type, node_id, code_lines (recommended) or code.\n"
            "  type is mapped to action automatically: replace | insert | delete | move.\n"
            "  For insert (container): parent_node_id (__root__ for module level), position first|last.\n"
            "  For insert (sibling-relative): target_node_id, position before|after "
            "(parent_node_id omitted or __root__).\n"
            '  Shorthand: parent_node_id + position {"after": N} (0-based sibling index).\n'
            "  stable_id (preview short_id) is preserved across sibling/unrelated ops in one batch;\n"
            "  re-preview only after failure, full parent replace, or when targets are unknown.\n"
            "  Nested functions and class methods are normal sibling targets.\n"
            "  Parent and child in the same batch are rejected (NESTED_BATCH_FORBIDDEN).\n\n"
            "JSON/YAML (.json, .yaml, .yml):\n"
            "  Preview returns integer short_id in node_ref. Pass the same integer in node_ref or\n"
            "  json_pointer; the server maps short_id to RFC 6901 JSON Pointer via MAP.\n"
            "  Legacy JSON Pointer or opaque UUID strings are still accepted on input.\n"
            "  For replace: value (any JSON type — string, number, boolean, null, array, object).\n"
            "  For insert: key (object) or index (array);\n"
            "  omit index (or use position: 'last') to append at end of array.\n"
            "  RFC 6901 sentinel: parent_json_pointer ending in '/-' (e.g. '/concepts/-')\n"
            "  resolves to the array itself and always appends — no index needed.\n"
            "  sibling-relative (preferred): position 'before:<addr>' | 'after:<addr>' —\n"
            "  <addr> is JSON Pointer (/items/0), stable UUID, or object key name.\n"
            "  Legacy: before_key|after_key, before_node_id|after_node_id, before_json_pointer|after_json_pointer.\n"
            "  parent_json_pointer='' targets the document root object.\n\n"
            "text (.txt, .md, .rst, .adoc, others):\n"
            "  Preview returns integer short_id (paragraph/line or section tree). Pass the same\n"
            "  integer in node_ref or target_node_id; the server resolves source line bounds.\n"
            "  Legacy markdown slug or line-index strings are still accepted on input.\n"
            "  Fields: type, start_line, end_line, content — or type, node_ref, content.\n"
            "  When both node_ref and start_line are present, node_ref wins.\n"
            "  For .md insert: position before|after (default after), or before:<node_ref>|after:<node_ref>.\n"
            "  before inserts at the section heading line; after inserts after the section.\n"
            "  For .md replace by node_ref: the range includes the heading line (breaking change).\n"
            "  Optional safety: anchor_head + anchor_tail (five non-whitespace chars from the\n"
            "  first/last line of the target range). When supplied, the server rejects the\n"
            "  operation if the draft lines no longer match — use after locating content via\n"
            "  fulltext_search or an earlier preview.\n"
            "  Use position: 'last' (without start_line) to append content at end of file.\n"
            "  **Never reuse line numbers from fulltext_search or an earlier preview after a\n"
            "  prior universal_file_edit call.** Each edit shifts line numbers. Before every\n"
            "  line-targeted operation, re-run universal_file_preview with the same session_id\n"
            "  (reads the draft) or pass anchor_head/anchor_tail from the intended target lines.\n"
            "  Multiple line-targeted operations in one batch are sorted bottom-up automatically.\n\n"
            "Format routing: edit operations are routed by session.format_group from open "
            "(sidecar, tree-temp, or text). In sidecar/tree-temp without is_invalid fallback, "
            "only node-based operations apply — line ranges are rejected. After parse-error "
            "fallback (is_invalid=True), format_group becomes text and line-based edits are used "
            "until a successful commit restores structural editing.\n\n"
            "The original file on disk is never touched by this command. "
            "Changes reach disk only after universal_file_write (commit phase)."
        ),
        "parameters": {
            "project_id": {
                "description": (
                    "Project UUID. Required by schema for MCP consistency; execute resolves "
                    "the session by session_id only and does not re-validate project_id."
                ),
                "type": "string",
                "required": True,
                "examples": ["8772a086-688d-4198-a0c4-f03817cc0e6c"],
            },
            "session_id": {
                "description": (
                    "Active session UUID returned by universal_file_open. "
                    "Sessions are invalidated on server restart."
                ),
                "type": "string",
                "required": True,
                "examples": ["4b4255c7-6a0c-4396-94c6-6f2bcf297912"],
            },
            "operations": {
                "description": (
                    "Batch of edit operations. Shape must match universal_file_preview:\n"
                    "  Python : {type, node_id, code_lines}\n"
                    "  JSON/YAML: {type, json_pointer, value} or {type, node_id, value}\n"
                    "  text   : {type, node_ref, content} or {type, start_line, end_line, content}\n"
                    "Supported type values: replace, insert, delete."
                ),
                "type": "array",
                "required": True,
                "items": {"type": "object"},
                "examples": [
                    [
                        {
                            "type": "replace",
                            "node_id": "<uuid>",
                            "code_lines": ["def f() -> str:", "    return 'ok'"],
                        }
                    ],
                    [{"type": "replace", "json_pointer": "/timeout", "value": 60}],
                    [
                        {
                            "type": "replace",
                            "start_line": 2,
                            "end_line": 2,
                            "content": "Updated line.",
                        }
                    ],
                ],
            },
        },
        "return_value": {
            "success": {
                "description": "Operations applied to the in-memory draft without errors.",
                "data": {
                    "success": "Always True on success.",
                    "updated": "True when the draft was modified (sidecar and tree-temp).",
                    "line_count": "Number of lines after edit (text format only).",
                },
                "example": {"success": True, "updated": True},
            },
            "error": {
                "description": "One or more operations were rejected; no partial writes occur.",
                "code": "Stable error code (see error_cases).",
                "message": "Human-readable description of what failed.",
                "details": "Optional dict with operation payload or path context.",
            },
        },
        "usage_examples": [
            {
                "description": "Replace a Python function (sidecar)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<from universal_file_open>",
                    "operations": [
                        {
                            "type": "replace",
                            "node_id": 4,
                            "code_lines": [
                                "def hello() -> str:",
                                '    """Say hello."""',
                                '    return "hello"',
                            ],
                        }
                    ],
                },
                "explanation": (
                    "Open .py with universal_file_open, run universal_file_preview to get "
                    "integer short_id of the target node, pass it as node_id. "
                    "Use code_lines (list of strings) for multi-line code."
                ),
            },
            {
                "description": "Batch insert and replace sibling Python methods (sidecar)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<from universal_file_open>",
                    "operations": [
                        {
                            "type": "insert",
                            "target_node_id": 3,
                            "position": "after",
                            "code_lines": [
                                "",
                                "def gamma(self) -> bool:",
                                "    return True",
                            ],
                        },
                        {
                            "type": "replace",
                            "node_id": 5,
                            "code_lines": ["def beta(self) -> int:", "    return 42"],
                        },
                    ],
                },
                "explanation": (
                    "Sibling methods in one batch: stable_id from preview stays valid "
                    "for both ops. Do not combine parent class and child method in one batch."
                ),
            },
            {
                "description": "Update a JSON scalar field value (tree-temp)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<from universal_file_open>",
                    "operations": [{"type": "replace", "node_ref": 3, "value": 60}],
                },
                "explanation": (
                    "Preview returns integer short_id in node_ref. Pass the same integer in "
                    "node_ref or json_pointer (legacy '/timeout' also accepted)."
                ),
            },
            {
                "description": "Replace a YAML array field with a new list (tree-temp)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<from universal_file_open>",
                    "operations": [
                        {
                            "type": "replace",
                            "json_pointer": "/atomic_steps",
                            "value": ["A-001", "A-002"],
                        }
                    ],
                },
                "explanation": (
                    "value accepts any JSON type: string, number, boolean, null, array, or object. "
                    "Pass a Python list to replace a sequence node. "
                    "Pass [] to replace with an empty array."
                ),
            },
            {
                "description": "Replace a YAML scalar field (tree-temp)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<from universal_file_open>",
                    "operations": [
                        {
                            "type": "replace",
                            "json_pointer": "/status",
                            "value": "ready_for_review",
                        }
                    ],
                },
                "explanation": (
                    "Pass a string (or any scalar) directly as value. "
                    "The node type in the document is replaced with the new value type."
                ),
            },
            {
                "description": "Append to a JSON array using RFC 6901 sentinel (tree-temp)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<from universal_file_open>",
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "/concepts/-",
                            "value": "C-010",
                        }
                    ],
                },
                "explanation": (
                    "parent_json_pointer ending in '/-' resolves the array at /concepts "
                    "and appends without requiring an explicit index. "
                    "Equivalent to passing parent_json_pointer='/concepts' with position='last'."
                ),
            },
            {
                "description": "Append a line to end of text file (text)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<from universal_file_open>",
                    "operations": [
                        {
                            "type": "insert",
                            "position": "last",
                            "content": "new line at end of file",
                        }
                    ],
                },
                "explanation": (
                    "position='last' appends content at the end of the file "
                    "without needing to know the current line count."
                ),
            },
            {
                "description": "Replace a line in a text file (text)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<from universal_file_open>",
                    "operations": [
                        {
                            "type": "replace",
                            "node_ref": 2,
                            "content": "Updated.",
                        }
                    ],
                },
                "explanation": (
                    "Pass integer short_id from preview as node_ref; the server resolves line bounds. "
                    "start_line/end_line (1-based) remain available when node_ref is omitted."
                ),
            },
        ],
        "error_cases": {
            "SESSION_NOT_FOUND": {
                "description": "The session_id is not registered on the server.",
                "message": "Unknown session: {session_id}",
                "solution": "Open a new session with universal_file_open. Sessions are lost on server restart.",
            },
            "NESTED_BATCH_FORBIDDEN": {
                "description": (
                    "Sidecar only: batch targets both a parent node and its descendant "
                    "(e.g. replace outer and replace inner_a). Sibling batches are allowed."
                ),
                "message": "Ancestor-descendant pair in batch",
                "solution": (
                    "Split into separate universal_file_edit calls, or edit only the "
                    "outermost node in one batch."
                ),
            },
            "INVALID_OPERATION": {
                "description": (
                    "Operation rejected: unknown type value, unknown node_id/json_pointer, "
                    "invalid sidecar insert shape, or tree-temp path not found."
                ),
                "message": "No operations built from edit payload",
                "solution": (
                    "Verify node_id/json_pointer with universal_file_preview. "
                    "Use type: replace | insert | delete. "
                    "For text: check start_line/end_line are within draft bounds."
                ),
            },
            "STALE_NODE_ID": {
                "description": (
                    "Sidecar only: stable_id from preview was not found in metadata "
                    "(unexpected after normal sibling edits)."
                ),
                "message": "Stale or unknown node_id",
                "solution": (
                    "Re-run universal_file_preview with session_id. If persistent, "
                    "the node may have been removed by a full parent replace."
                ),
            },
            "UNKNOWN_NODE_REF": {
                "description": "Text/marked-tree: preview short_id or legacy alias not found in the current draft.",
                "message": "Unknown node_ref",
                "solution": "Re-run universal_file_preview with session_id to refresh integer short_id values.",
            },
            "LINE_OUT_OF_RANGE": {
                "description": "Text only: start_line/end_line are outside the current draft bounds.",
                "message": "line range {start_line}-{end_line} is out of range (draft has {line_count} lines)",
                "solution": (
                    "Re-run universal_file_preview with session_id to read the current draft. "
                    "Do not reuse line numbers from fulltext_search or a preview taken before "
                    "a prior universal_file_edit call."
                ),
            },
            "ANCHOR_MISMATCH": {
                "description": "Text only: anchor_head/anchor_tail do not match the draft lines at start_line/end_line.",
                "message": "anchor_head mismatch at lines {start_line}-{end_line}",
                "solution": (
                    "The draft shifted since line numbers were collected. Re-run "
                    "universal_file_preview with session_id and retry with fresh line numbers "
                    "or updated anchors."
                ),
            },
            "INVALID_SESSION": {
                "description": "Session has no registered tree_id (tree-temp path).",
                "message": "Session has no registered tree id for tree-temp format.",
                "solution": "Close and re-open the session with universal_file_open.",
            },
            "PARSE_ERROR": {
                "description": "File could not be parsed when loading the CST tree (sidecar path).",
                "message": "Parse error on file load.",
                "solution": "Check the file for syntax errors before opening the session.",
            },
            "WRITE_FAILED": {
                "description": "Backup creation failed before applying tree-temp or text edits.",
                "message": "Backup before edit failed: {exc}",
                "solution": "Check disk space and permissions under the project root.",
            },
        },
        "best_practices": [
            "Call universal_file_preview before the first universal_file_edit to obtain integer short_id values.",
            "Preview responses use integer node_ref; pass the same integer in edit ops (node_id, node_ref, json_pointer).",
            "For Python (sidecar): short_id is preserved across sibling ops in one batch.",
            "For Python (sidecar): use code_lines (list of strings) for multi-line code to avoid JSON escaping issues.",
            "For Python sibling insert: target_node_id + position before|after (not parent_node_id + before).",
            "For Python: do not combine parent and child node targets in one batch (NESTED_BATCH_FORBIDDEN).",
            "For JSON/YAML replace: value accepts any JSON type — string, number, boolean, null, array, object.",
            "For JSON/YAML replace array: pass a Python list as value; pass [] for an empty array.",
            "For JSON/YAML array append: omit index, or use position='last', or end parent_json_pointer with '/-'.",
            "For JSON array sibling insert: before_node_id or after_node_id (mutually exclusive with index).",
            "For JSON object sibling insert: before_key or after_key to preserve key order.",
            "For text/markdown: pass integer short_id as node_ref; legacy slug/pointer strings still accepted on input.",
            "For text: never reuse line numbers from fulltext_search or an earlier preview after universal_file_edit — re-run universal_file_preview with session_id before each line-targeted edit.",
            "For text: pass anchor_head and anchor_tail together to verify the target range before replace/delete.",
            "For text append: use position='last' without start_line — no need to know the line count.",
            "Multiple operations in one batch are validated together before any modification is applied.",
            "The original file is never touched until universal_file_write (commit phase).",
            "After server restart all sessions are lost — re-open with universal_file_open.",
        ],
    }
