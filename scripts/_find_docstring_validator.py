"""Find docstring validator source file."""
import subprocess
result = subprocess.run(
    ['grep', '-r', 'missing type hints for parameters', '/home/vasilyvz/projects/tools/code_analysis/.venv', '--include=*.py', '-l'],
    capture_output=True, text=True
)
print(result.stdout)
print(result.stderr)
