# Main process crash analysis

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## What we know

1. **Process 326382** (and earlier 308198, 300912, 286123): main server process starts, binds to 15000, registers with proxy, then at some point **exits**. Pidfile is left with a dead PID (stale pidfile).

2. **When exit is graceful** we see in `mcp_server.log`:
   - `Received signal 15, stopping all workers then exiting`
   - `cleanup_workers() invoked (shutdown path)`
   - `Hypercorn run_server returned (server loop ended normally)`
   - `main() exiting after server loop`  
   That happens when someone sends **SIGTERM** (e.g. `server_manager_cli restart` or `stop`).

3. **When exit is NOT graceful** (e.g. process 326382): **none** of the above appears for that PID. The log continues with worker activity (indexing, file_watcher) because **workers are separate processes** and keep writing to the same log file. So the main process died **without**:
   - receiving SIGTERM (otherwise we’d see "Received signal 15"),
   - running our Python excepthook (no "Uncaught exception in main thread"),
   - returning from `engine.run_server()` (no "run_server returned" / "main() exiting").

4. **Conclusion:** The main process is either:
   - **Killed by SIGKILL** (e.g. OOM killer, or `kill -9`). Then no handler runs, no log.
   - **Crashing in native code** (segfault, abort). Then the Python excepthook and our `finally` do not run; we’d only see a trace if something (e.g. faulthandler) dumps to stderr.

5. **dmesg:** Checked for OOM/kill messages; none found (or no permission). So OOM is not confirmed but not ruled out.

## What was added

- **faulthandler.enable()** in daemon mode (in `main.py`). On SIGSEGV/SIGABRT the interpreter will dump a traceback to stderr. Since the daemon’s stderr is redirected to `mcp_server.log` by `server_manager_cli`, the next segfault/abort should produce a trace in the log.
- **Main process heartbeat**: a daemon thread logs `Main process heartbeat (pid=...)` every 60 seconds. When the main process dies (crash or kill), the last heartbeat in the log shows the last moment it was alive (within ~60 s).

## What to do next

1. **Reproduce:** Start the server (daemon) and use it or wait until the main process dies again.
2. **Inspect log:** Open `logs/mcp_server.log` and look at the **end** for:
   - `Received signal 15` / `cleanup_workers` / `run_server returned` → graceful shutdown.
   - **Main process heartbeat** → last time the main process was alive (within ~60 s before crash).
   - A **faulthandler** traceback (thread stacks) → crash in native code / C extension.
   - None of the above → likely **SIGKILL** (e.g. OOM). **Right after the crash** run:
     ```bash
     sudo dmesg | tail -100
     ```
     Look for `Out of memory`, `Killed process`, or `oom_reaper`.
     You can run `./scripts/collect_crash_diagnostics.sh` after a crash to capture log tail and (if allowed) dmesg into a timestamped file.
3. **Debug in foreground:** Run the server in the terminal so faulthandler dumps to stderr on crash:
   ```bash
   python -m code_analysis.main --config config.json --foreground
   ```
   (No `--daemon`; same workers + Hypercorn. Stop with Ctrl+C.)

## Reproduction note

A **foreground** run (with `--foreground`) was kept up for **3 minutes** with workers and indexing activity; it did **not** crash. The ungraceful exit therefore is either:
- **Load- or time-dependent** (longer run or heavier load),
- **OOM** (memory growth until the kernel kills the process),
- **Daemon-specific** (e.g. different environment or parent exit).

After the **next** daemon crash: check `logs/mcp_server.log` for the last **Main process heartbeat** and any **faulthandler** output; then run `sudo dmesg | tail -100` to confirm or rule out OOM.

## Summary

Cause of the **ungraceful** main process exit is still **unknown**: no Python exception and no SIGTERM in the log. faulthandler and heartbeat are enabled in daemon mode. On the next crash: if **faulthandler** appears in `mcp_server.log` → native crash; if **heartbeat** is the last main-process line and no faulthandler → run **sudo dmesg** to check for OOM.
