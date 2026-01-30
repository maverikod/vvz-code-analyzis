# Why Workers May Not Start

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Causes and fixes

### 1. PID file blocks start

**Symptom:** `get_worker_status` shows 0 processes; server log says "Vectorization worker already running" or start is skipped.

**Cause:** PID file (e.g. `logs/vectorization_worker.pid`) exists and contains a PID that is still running (e.g. from a previous server run). The current process does not register that PID, so status shows 0.

**Fixes:**

- Workers now remove their PID file on exit (`finally` in runner). Restart the server so that when workers exit they clear the PID file; then on next start they can start again.
- PID file path is now absolute when `worker_logs_dir` is passed (from `worker_log_path`’s parent). This avoids different working directories creating different PID file locations.
- Manually remove stale PID files: `rm -f logs/vectorization_worker.pid logs/file_watcher_worker.pid` (or the absolute path under your config logs dir), then restart.

### 2. Missing or empty `code_analysis` config

**Symptom:** Log message "No code_analysis config found, skipping vectorization worker".

**Cause:** At startup, `get_config()` from the adapter may not yet expose the full config (e.g. when startup runs in a background thread), so `code_analysis` is missing.

**Fix:** Startup now falls back to loading config from the same `config_path` file used to create the app. Ensure `config.json` (or your config file) contains a `code_analysis` section with at least `chunker` and optionally `worker` (e.g. `enabled: true`, `log_path`, etc.).

### 3. No chunker config

**Symptom:** "No chunker config found, skipping vectorization worker".

**Cause:** `code_analysis.chunker` is missing or empty.

**Fix:** In config, set `code_analysis.chunker` with at least `enabled: true` and connection settings (url/port, protocol, certs if mTLS).

### 4. Worker disabled in config

**Symptom:** "Vectorization worker is disabled in config, skipping".

**Cause:** `code_analysis.worker.enabled` is `false`.

**Fix:** Set `code_analysis.worker.enabled` to `true` (or omit it; default is true).

### 5. Worker process starts then exits

**Symptom:** Worker starts (log shows "Starting universal vectorization worker...") but `get_worker_status` later shows 0 processes.

**Cause:** The worker process crashes (e.g. SVO client init fails, database unavailable, import error). Check the worker’s own log file.

**Fix:**

- Ensure the database driver is running before workers start (startup order: database driver → vectorization → file_watcher).
- Check `logs/vectorization_worker.log` (or the path in `code_analysis.worker.log_path`) for exceptions.
- Ensure SVO/chunker and embedding services are reachable if configured.

## Separate worker logs

Worker logs are written to dedicated files:

- **Vectorization:** `code_analysis.worker.log_path` (default `logs/vectorization_worker.log`), with rotation.
- **File watcher:** `code_analysis.file_watcher.log_path` (default `logs/file_watcher.log`), with rotation.

Each worker process configures its root logger to write to its log file (and optionally stderr). The main server log is separate (e.g. `server.log_dir` / `mcp_server.log`).
