"""Temporary script: delete models.tree sidecar to force CST rebuild."""

from pathlib import Path

from code_analysis.tree.sibling_convention import sibling_tree_path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_SOURCE = REPO_ROOT / "code_analysis" / "core" / "cst_tree" / "models.py"

p = sibling_tree_path(MODELS_SOURCE)
print("path:", p)
print("exists:", p.exists())
p.unlink(missing_ok=True)
print("deleted:", not p.exists())
