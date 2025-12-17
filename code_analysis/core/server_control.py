"""
Server control manager in systemd/systemv style.

Provides start, stop, restart, status, and reload commands for MCP server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ServerControl:
    """Systemd-style server control manager."""

    def __init__(
        self,
        config_path: Path,
        pid_file: Optional[Path] = None,
        log_file: Optional[Path] = None,
    ):
        """
        Initialize server control manager.

        Args:
            config_path: Path to server configuration file
            pid_file: Path to PID file (default: /var/run/code_analysis/mcp_server.pid for system, data/mcp_server.pid for local)
            log_file: Path to log file (default: from config or logs/mcp_server.log)
        """
        self.config_path = Path(config_path).resolve()
        
        # Load config to get log path from adapter config
        # Priority: Arguments > Environment variables > Adapter Config > Default
        import os
        
        # Try to load adapter config to get log_dir
        adapter_log_dir = None
        try:
            from mcp_proxy_adapter.core.config.simple_config import SimpleConfig
            simple_config = SimpleConfig(str(self.config_path))
            model = simple_config.load()
            adapter_log_dir = getattr(model.server, "log_dir", None)
        except Exception:
            pass
        
        # Determine log file: Argument > ENV > Adapter Config > Default
        if not log_file:
            env_log = os.getenv("CODE_ANALYSIS_LOG")
            if env_log:
                log_file = env_log
            elif adapter_log_dir:
                # adapter_log_dir is a directory, add filename
                log_dir_path = Path(adapter_log_dir)
                log_file = str(log_dir_path / "mcp_server.log")
            else:
                log_file = None
        
        # Default PID file location
        if pid_file:
            self.pid_file = Path(pid_file).resolve()
        else:
            # Use /var/run for system-wide config, local data/ for local config
            if str(self.config_path).startswith("/etc/"):
                pid_dir = Path("/var/run/code_analysis")
                try:
                    pid_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
                except PermissionError:
                    # Fallback to /tmp if no permission for /var/run
                    pid_dir = Path("/tmp/code_analysis")
                    pid_dir.mkdir(parents=True, exist_ok=True)
                self.pid_file = pid_dir / "mcp_server.pid"
            else:
                data_dir = self.config_path.parent / "data"
                data_dir.mkdir(parents=True, exist_ok=True)
                self.pid_file = data_dir / "mcp_server.pid"
        
        # Default log file location
        if log_file:
            self.log_file = Path(log_file).resolve()
        else:
            # Use /var/log for system-wide config, local logs/ for local config
            if str(self.config_path).startswith("/etc/"):
                log_dir = Path("/var/log/code_analysis")
                try:
                    log_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
                except PermissionError:
                    # Fallback to /tmp if no permission for /var/log
                    log_dir = Path("/tmp/code_analysis/logs")
                    log_dir.mkdir(parents=True, exist_ok=True)
                self.log_file = log_dir / "mcp_server.log"
            else:
                logs_dir = self.config_path.parent / "logs"
                logs_dir.mkdir(parents=True, exist_ok=True)
                self.log_file = logs_dir / "mcp_server.log"

    def _read_pid(self) -> Optional[int]:
        """Read process ID from PID file."""
        if not self.pid_file.exists():
            return None
        try:
            with open(self.pid_file, "r") as f:
                pid = int(f.read().strip())
            return pid
        except (ValueError, IOError) as e:
            logger.warning(f"Failed to read PID file {self.pid_file}: {e}")
            return None

    def _write_pid(self, pid: int) -> None:
        """Write process ID to PID file."""
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.pid_file, "w") as f:
            f.write(str(pid))
        logger.debug(f"Wrote PID {pid} to {self.pid_file}")

    def _remove_pid(self) -> None:
        """Remove PID file."""
        if self.pid_file.exists():
            self.pid_file.unlink()
            logger.debug(f"Removed PID file {self.pid_file}")

    def _is_process_running(self, pid: int) -> bool:
        """Check if process is running."""
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _get_process_info(self, pid: int) -> Optional[Dict[str, Any]]:
        """Get process information."""
        if not self._is_process_running(pid):
            return None
        
        try:
            # Try to get process info from /proc (Linux)
            proc_path = Path(f"/proc/{pid}")
            if proc_path.exists():
                cmdline = proc_path / "cmdline"
                if cmdline.exists():
                    with open(cmdline, "r") as f:
                        cmd = f.read().replace("\x00", " ").strip()
                    return {
                        "pid": pid,
                        "cmd": cmd,
                        "running": True,
                    }
        except Exception:
            pass
        
        return {"pid": pid, "running": True}

    def start(self) -> Dict[str, Any]:
        """
        Start MCP server.

        Returns:
            Dictionary with status information
        """
        # Check if already running
        pid = self._read_pid()
        if pid and self._is_process_running(pid):
            return {
                "success": False,
                "message": f"Server is already running (PID: {pid})",
                "pid": pid,
            }

        # Clean up stale PID file
        if pid:
            self._remove_pid()

        # Build command - use main.py with mcp-proxy-adapter
        cmd = [
            sys.executable,
            "-m",
            "code_analysis.main",
            "--config",
            str(self.config_path),
        ]

        # Start server in background
        try:
            # Open log file for output
            log_dir = self.log_file.parent
            log_dir.mkdir(parents=True, exist_ok=True)
            log_handle = open(self.log_file, "a")
            
            process = subprocess.Popen(
                cmd,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                cwd=self.config_path.parent,
            )

            # Wait a bit to check if process started successfully
            time.sleep(0.5)
            
            if process.poll() is not None:
                # Process exited immediately
                log_handle.close()
                return {
                    "success": False,
                    "message": f"Server failed to start (exit code: {process.returncode})",
                }

            self._write_pid(process.pid)
            
            logger.info(f"Server started with PID: {process.pid}")
            return {
                "success": True,
                "message": "Server started successfully",
                "pid": process.pid,
                "log_file": str(self.log_file),
            }
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            return {
                "success": False,
                "message": f"Failed to start server: {str(e)}",
            }

    def stop(self, timeout: int = 10) -> Dict[str, Any]:
        """
        Stop MCP server.

        Args:
            timeout: Timeout in seconds before force kill

        Returns:
            Dictionary with status information
        """
        pid = self._read_pid()
        if not pid:
            return {
                "success": False,
                "message": "Server is not running (no PID file found)",
            }

        if not self._is_process_running(pid):
            # Stale PID file
            self._remove_pid()
            return {
                "success": False,
                "message": "Server is not running (stale PID file)",
            }

        # Try graceful shutdown
        try:
            os.kill(pid, signal.SIGTERM)
            logger.info(f"Sent SIGTERM to process {pid}")

            # Wait for process to terminate
            for _ in range(timeout):
                if not self._is_process_running(pid):
                    self._remove_pid()
                    return {
                        "success": True,
                        "message": "Server stopped successfully",
                        "pid": pid,
                    }
                time.sleep(1)

            # Force kill if still running
            if self._is_process_running(pid):
                os.kill(pid, signal.SIGKILL)
                logger.warning(f"Force killed process {pid}")
                time.sleep(0.5)
                self._remove_pid()
                return {
                    "success": True,
                    "message": "Server force stopped",
                    "pid": pid,
                }
        except ProcessLookupError:
            # Process already gone
            self._remove_pid()
            return {
                "success": True,
                "message": "Server was not running",
            }
        except Exception as e:
            logger.error(f"Failed to stop server: {e}")
            return {
                "success": False,
                "message": f"Failed to stop server: {str(e)}",
            }

    def restart(self) -> Dict[str, Any]:
        """
        Restart MCP server (stop then start).

        Returns:
            Dictionary with status information
        """
        # Stop first
        stop_result = self.stop()
        if not stop_result["success"] and "stale" not in stop_result["message"].lower():
            # Only fail if it's a real error (not just "not running")
            logger.warning(f"Stop returned: {stop_result['message']}")

        # Wait a bit
        time.sleep(1)

        # Start
        return self.start()

    def status(self) -> Dict[str, Any]:
        """
        Get server status.

        Returns:
            Dictionary with status information
        """
        pid = self._read_pid()
        if not pid:
            return {
                "running": False,
                "message": "Server is not running (no PID file)",
            }

        if not self._is_process_running(pid):
            # Stale PID file
            self._remove_pid()
            return {
                "running": False,
                "message": "Server is not running (stale PID file)",
                "pid": pid,
            }

        # Get process info
        proc_info = self._get_process_info(pid)
        if proc_info:
            return {
                "running": True,
                "message": "Server is running",
                "pid": pid,
                "log_file": str(self.log_file),
                "config_file": str(self.config_path),
            }
        else:
            return {
                "running": False,
                "message": "Server process not found",
                "pid": pid,
            }

    def reload(self) -> Dict[str, Any]:
        """
        Reload server configuration (restart server).

        Note: MCP server doesn't support hot reload, so this restarts the server.

        Returns:
            Dictionary with status information
        """
        return self.restart()

