"""Generate embedded project bootstrap template data from a zip archive."""

import zipfile
import sys
import os

ZIP_PATH = "/home/vasilyvz/projects/tools/code_analysis/rules_template_agents_protocols_updated.zip"
OUT_PATH = "/home/vasilyvz/projects/tools/code_analysis/code_analysis/core/project_bootstrap/template_data.py"
# @node-id: 648715fb-82f1-4570-aa77-c60cd01c3de7


def main() -> None:
    """Run the command-line entry point."""
    files: dict[str, str] = {}
    with zipfile.ZipFile(ZIP_PATH) as z:
        for name in z.namelist():
            if name.endswith("/"):
                continue
            parts = name.split("/", 1)
            rel = parts[1] if len(parts) == 2 else name
            if not rel:
                continue
            content = z.read(name).decode("utf-8", errors="replace")
            files[rel] = content

    lines = [
        '"""',
        "Embedded template data for project_bootstrap.",
        "",
        "Auto-generated from rules_template_agents_protocols_updated.zip.",
        "Author: Vasiliy Zdanovskiy",
        "email: vasilyvz@gmail.com",
        '"""',
        "from __future__ import annotations",
        "",
        "# Embedded zip bytes (empty = use TEMPLATE_FILES dict)",
        'TEMPLATE_ZIP_BYTES: bytes = b""',
        "",
        "# Mapping of relative path -> file content",
        "TEMPLATE_FILES: dict[str, str] = {",
    ]
    for key, val in sorted(files.items()):
        lines.append(f"    {repr(key)}: {repr(val)},")
    lines.append("}")
    lines.append("")

    code = "\n".join(lines)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"Written {len(code)} bytes to {OUT_PATH}")


main()
