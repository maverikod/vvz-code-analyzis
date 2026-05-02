"""Check deleted column DEFAULT in files table schema."""
import pathlib

f = pathlib.Path(
    "/home/vasilyvz/projects/tools/code_analysis"
    "/code_analysis/core/database/schema_definition_tables_core.py"
)
lines = f.read_text().splitlines()
for i, line in enumerate(lines, 1):
    if 'deleted' in line.lower():
        print(f"{i}: {line}")
