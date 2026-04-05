"""
Shared LibCST parse gate for get_file_lines / replace_file_lines.

When a Python file parses successfully, line-based commands normally return
USE_CST_COMMANDS unless config allows healthy line ops or an internal
router (e.g. read_project_text_file → get_file_lines) sets allow_healthy_line_ops.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import libcst as cst

# Error message when file is healthy and line commands are disallowed
LINE_CMD_DISALLOWED_MSG = (
    "This file parses successfully. Use CST commands instead: "
    "cst_load_file (load tree), cst_modify_tree (edit by node), compose_cst_module (patch by selector). "
    "Set code_analysis.allow_line_commands_on_healthy_files=true to allow get_file_lines/replace_file_lines on healthy files."
)


def healthy_parse_blocks_line_ops(
    source_text: str,
    *,
    allow_healthy_line_ops: bool,
    allow_line_commands_on_healthy_files: bool,
) -> bool:
    """
    Return True if line-based read/write should refuse with USE_CST_COMMANDS.

    When False, the caller should proceed with line-range I/O (unhealthy parse
    or healthy parse explicitly allowed).
    """
    if allow_healthy_line_ops or allow_line_commands_on_healthy_files:
        return False
    try:
        cst.parse_module(source_text)
    except cst.ParserSyntaxError:
        return False
    return True
