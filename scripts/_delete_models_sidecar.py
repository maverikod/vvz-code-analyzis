"""Temporary script: delete models.tree sidecar to force CST rebuild."""
from pathlib import Path

p = Path('/home/vasilyvz/projects/tools/code_analysis/code_analysis/core/cst_tree/.cst/models.tree')
print('exists:', p.exists())
p.unlink(missing_ok=True)
print('deleted:', not p.exists())
