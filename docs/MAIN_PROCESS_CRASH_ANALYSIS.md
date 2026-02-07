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

## What to do next

1. **Reproduce:** Start the server and use it (or wait) until the main process dies again.
2. **Inspect log:** Open `logs/mcp_server.log` and look at the **end** for:
   - `Received signal 15` / `cleanup_workers` / `run_server returned` → graceful shutdown.
   - A **faulthandler** traceback (thread stacks) → crash in native code / C extension.
   - Still nothing → likely SIGKILL (e.g. OOM); try `sudo dmesg | tail -50` after the next crash.
3. **Optional:** Run without daemon to see stderr live:  
   `python -m code_analysis.main --config config.json`  
   (no `--daemon`). If it crashes, the trace appears in the terminal.

## Summary

Cause of the **ungraceful** main process exit is still **unknown**: no Python exception and no SIGTERM in the log. faulthandler is enabled so the next segfault/abort should leave a trace in `mcp_server.log`. If the process is killed by SIGKILL (e.g. OOM), only the kernel (dmesg) or the sender of the signal can explain it.
