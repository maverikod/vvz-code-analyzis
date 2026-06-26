"""Patch the CST find-node command base class declaration."""

import pathlib

path = pathlib.Path(
    "/home/vasilyvz/projects/tools/code_analysis/code_analysis/commands/cst_find_node_command.py"
)
src = path.read_text(encoding="utf-8")
old = "class CSTFindNodeCommand:"
new = "class CSTFindNodeCommand(BaseMCPCommand):"
if old in src:
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    print("Done: replaced class declaration")
else:
    print("ERROR: pattern not found")
