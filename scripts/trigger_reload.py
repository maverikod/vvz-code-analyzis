"""Trigger server reload."""

import subprocess
import sys

result = subprocess.run(
    [
        sys.executable,
        "-c",
        'import importlib; import code_analysis.core.cst_tree.tree_builder; importlib.reload(code_analysis.core.cst_tree.tree_builder); print("reloaded")',
    ],
    capture_output=True,
    text=True,
)
print(result.stdout)
print(result.stderr)
