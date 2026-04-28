import subprocess
# Commands modified this session that have metadata() methods
files = [
    # FTS fix - not commands, internal modules
    'code_analysis/core/database_client/client_api_files.py',
    'code_analysis/core/database/entities.py',
    'code_analysis/core/database/files/crud.py',
    'code_analysis/commands/compose_cst_db.py',
    # include_code feature
    'code_analysis/core/cst_tree/tree_finder.py',
    'code_analysis/commands/cst_find_node_command.py',
]
for f in files:
    r = subprocess.run(
        ['grep', '-n', 'def metadata\|def get_schema\|class.*Command',
         f'/home/vasilyvz/projects/tools/code_analysis/{f}'],
        capture_output=True, text=True
    )
    hits = r.stdout.strip()
    print(f'\n=== {f} ===')
    print(hits or '(no metadata/schema/Command)')
