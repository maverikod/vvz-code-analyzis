files = [
    '/home/vasilyvz/projects/tools/code_analysis/code_analysis/core/indexing_worker_pkg/processing.py',
    '/home/vasilyvz/projects/tools/code_analysis/code_analysis/core/worker_project_activity.py',
    '/home/vasilyvz/projects/tools/code_analysis/code_analysis/commands/run_project_script_command.py',
]
for fpath in files:
    print(f'\n===== {fpath} =====')
    with open(fpath) as f:
        src = f.read()
    print(src)
