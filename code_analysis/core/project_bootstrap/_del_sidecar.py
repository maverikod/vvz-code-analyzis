"""Remove generated CST sidecar files for local bootstrap cleanup."""

import pathlib

p = pathlib.Path(
    "/home/vasilyvz/projects/tools/code_analysis/code_analysis/commands/.cst"
)
if p.exists():
    for f in p.glob("cst_modify_tree_command*"):
        print("removing", f)
        f.unlink()
print("done")
