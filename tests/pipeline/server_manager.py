"""
Server management utilities for testing.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from tests.pipeline.config import PipelineConfig


class ServerManager:
    """Manages test server process."""

    def __init__(self, config: "PipelineConfig"):  # noqa: F821
        """Initialize server manager.

        Args:
            config: Pipeline configuration
        """
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.pid: Optional[int] = None
        self.config_file: Optional[Path] = None

    def start_server(self, timeout: int = 30) -> bool:
        """Start test server.

        Args:
            timeout: Timeout in seconds to wait for server to start

        Returns:
            True if server started successfully
        """
        if self.process is not None:
            return False

        # Create temporary config file
        self.config_file = (
            Path(tempfile.gettempdir()) / f"test_config_{os.getpid()}.json"
        )
        self.config.create_test_config(self.config_file)

        # Start server process
        python = sys.executable
        args = [
            python,
            "-m",
            "code_analysis.main",
            "--config",
            str(self.config_file),
            "--daemon",
        ]

        try:
            self.process = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            self.pid = self.process.pid

            # Wait for server to start
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self.is_server_running():
                    return True
                time.sleep(0.5)

            return False

        except Exception:
            self.process = None
            self.pid = None
            return False

    def stop_server(self, timeout: int = 10) -> bool:
        """Stop test server.

        Args:
            timeout: Timeout in seconds to wait for server to stop

        Returns:
            True if server stopped successfully
        """
        if self.process is None:
            return True

        try:
            # Try graceful shutdown
            if self.pid:
                try:
                    os.kill(self.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

            # Wait for process to terminate
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Force kill
                if self.pid:
                    try:
                        os.kill(self.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                self.process.wait()

            self.process = None
            self.pid = None

            # Cleanup config file
            if self.config_file and self.config_file.exists():
                try:
                    self.config_file.unlink()
                except Exception:
                    pass
            self.config_file = None

            return True

        except Exception:
            return False

    def is_server_running(self) -> bool:
        """Check if server is running.

        Returns:
            True if server is running
        """
        if self.process is None:
            return False

        # Check if process is still alive
        if self.process.poll() is not None:
            return False

        # Try to connect to server (simple check)
        # For now, just check if process is alive
        return True

    def restart_server(self, timeout: int = 30) -> bool:
        """Restart test server.

        Args:
            timeout: Timeout in seconds

        Returns:
            True if server restarted successfully
        """
        if not self.stop_server():
            return False

        time.sleep(1)  # Brief pause between stop and start

        return self.start_server(timeout=timeout)
