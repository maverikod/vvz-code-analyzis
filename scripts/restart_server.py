"""Restart the code analysis server through its Python module entrypoint."""

import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "code_analysis.server", "restart"],
    capture_output=True,
    text=True,
    timeout=10,
)
print(result.stdout)
print(result.stderr)
