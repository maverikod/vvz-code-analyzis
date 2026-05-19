"""
Post-write re-parse for sessions opened on syntactically invalid files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from code_analysis.commands.universal_file_edit.session import EditSession

from code_analysis.commands.universal_file_edit.format_group import FORMAT_SIDECAR


def try_clear_invalid_after_write(session: "EditSession") -> None:
    """If the file now parses, clear ``session.is_invalid``."""
    if not session.is_invalid:
        return
    path = session.abs_path
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    orig = session.original_format_group or session.format_group
    try:
        if orig == FORMAT_SIDECAR or path.suffix.lower() in (".py", ".pyi", ".pyw"):
            from code_analysis.core.cst_tree.tree_builder import load_file_to_tree

            tree = load_file_to_tree(str(path))
            from code_analysis.core.cst_tree.tree_builder import remove_tree

            remove_tree(tree.tree_id)
        elif path.suffix.lower() == ".json":
            json.loads(text)
        elif path.suffix.lower() in (".yaml", ".yml"):
            import yaml

            yaml.safe_load(text)
        else:
            return
    except Exception:
        return
    session.is_invalid = False
