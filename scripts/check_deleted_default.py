"""Check deleted column DEFAULT in files table schema."""
import pathlib

f = pathlib.Path(
    "/home/vasilyvz/projects/tools/code_analysis"
    "/code_analysis/core/database/schema_definition_tables_core.py"
)
lines = f.read_text().splitlines()
in_files = False
for i, line in enumerate(lines, 1):
    if "'files'" in line or '"files"' in line:
        in_files = True
    if in_files and ('deleted' in line.lower() or 'DEFAULT' in line):
        print(f"{i}: {line}")
    if in_files and i > 80:
        break
