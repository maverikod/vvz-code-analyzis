import pathlib, json

base = pathlib.Path('/home/vasilyvz/projects/tools/code_analysis/docs/plans/2026-04-27-universal-file-commands-refactor')
result = {}
for f in sorted(base.rglob('*.md')):
    try:
        result[str(f.relative_to(base))] = f.read_text(encoding='utf-8')
    except Exception as e:
        result[str(f.relative_to(base))] = f'ERROR: {e}'
print(json.dumps(result))
