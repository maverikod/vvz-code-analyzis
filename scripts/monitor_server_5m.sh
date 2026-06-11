#!/usr/bin/env bash
# Monitor local casmgr server every 5 minutes (stdout + logs/server_monitor.log).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOG="$ROOT/logs/server_monitor.log"
INTERVAL="${MONITOR_INTERVAL_SEC:-300}"
VENV="$ROOT/.venv/bin/python"

mkdir -p "$ROOT/logs"

log_line() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"
}

snapshot() {
  log_line "=== monitor tick ==="
  if command -v casmgr >/dev/null 2>&1; then
    casmgr --config config.json status 2>&1 | sed 's/^/  /' | tee -a "$LOG" || true
  fi
  "$VENV" - <<'PY' 2>&1 | sed 's/^/  /' | tee -a "$LOG" || true
import json
import subprocess
from pathlib import Path

root = Path("/home/vasilyvz/projects/tools/code_analysis")
log = root / "logs" / "file_watcher.log"

def tail_grep(pattern: str, n: int = 5) -> list[str]:
    if not log.is_file():
        return []
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    hits = [ln for ln in lines if pattern in ln]
    return hits[-n:]

print("file_watcher.log tail SCAN:")
for ln in tail_grep("SCAN"):
    print(ln)

# DB files count via psql if available
try:
    import os
    from dotenv import dotenv_values
    env = dotenv_values(root / ".env")
    pw = env.get("CHANGE_ME_APP") or env.get("POSTGRES_PASSWORD") or ""
    if pw:
        r = subprocess.run(
            [
                "psql",
                "postgresql://code_analysis_app:" + pw + "@127.0.0.1:5432/code_analysis",
                "-tAc",
                "SELECT count(*) FROM files WHERE deleted IS NOT TRUE;",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode == 0:
            print(f"postgres files.active={r.stdout.strip()}")
        else:
            print(f"postgres query failed: {r.stderr.strip()[:200]}")
except Exception as e:
    print(f"postgres skip: {e}")

# Worker CPU from ps
try:
    r = subprocess.run(
        ["pgrep", "-af", "code_analysis.main"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if r.stdout.strip():
        print("processes:")
        for ln in r.stdout.strip().splitlines()[:6]:
            print(ln)
except Exception as e:
    print(f"pgrep skip: {e}")
PY
  log_line "--- end tick ---"
}

log_line "monitor started interval=${INTERVAL}s pid=$$"
while true; do
  snapshot
  sleep "$INTERVAL"
done
