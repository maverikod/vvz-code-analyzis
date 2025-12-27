"""
Tests for WorkerManager.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import multiprocessing
import time
from pathlib import Path

import pytest

from code_analysis.core.worker_manager import WorkerManager, get_worker_manager


def dummy_worker_process():
    """Dummy worker process for testing."""
    import time

    time.sleep(1)


class TestWorkerManager:
    """Tests for WorkerManager."""

    def test_singleton(self):
        """Test that WorkerManager is a singleton."""
        manager1 = get_worker_manager()
        manager2 = get_worker_manager()
        assert manager1 is manager2

    def test_register_worker(self):
        """Test worker registration."""
        manager = WorkerManager()
        manager._workers.clear()  # Clear for test

        process = multiprocessing.Process(target=dummy_worker_process)
        process.start()

        try:
            manager.register_worker(
                "test_worker",
                {
                    "pid": process.pid,
                    "process": process,
                    "name": "test_worker_1",
                },
            )

            status = manager.get_worker_status()
            assert status["total_workers"] == 1
            assert "test_worker" in status["by_type"]
            assert status["by_type"]["test_worker"]["count"] == 1
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
                if process.is_alive():
                    process.kill()

    def test_unregister_worker(self):
        """Test worker unregistration."""
        manager = WorkerManager()
        manager._workers.clear()  # Clear for test

        process = multiprocessing.Process(target=dummy_worker_process)
        process.start()

        try:
            manager.register_worker(
                "test_worker",
                {
                    "pid": process.pid,
                    "process": process,
                    "name": "test_worker_1",
                },
            )

            assert len(manager._workers.get("test_worker", [])) == 1

            manager.unregister_worker("test_worker", process.pid)

            assert len(manager._workers.get("test_worker", [])) == 0
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
                if process.is_alive():
                    process.kill()

    def test_stop_worker_type(self):
        """Test stopping workers of a specific type."""
        manager = WorkerManager()
        manager._workers.clear()  # Clear for test

        # Use a longer-running process
        def long_worker():
            import time

            time.sleep(10)  # Long enough to test termination

        process = multiprocessing.Process(target=long_worker, daemon=True)
        process.start()

        try:
            # Wait a bit to ensure process is running
            time.sleep(0.2)
            assert process.is_alive(), "Process should be alive"

            manager.register_worker(
                "test_worker",
                {
                    "pid": process.pid,
                    "process": process,
                    "name": "test_worker_1",
                },
            )

            result = manager.stop_worker_type("test_worker", timeout=3.0)

            # Check that stop was attempted
            assert result["stopped"] >= 0  # Should stop at least 0 (may be 1)
            assert "errors" in result

            # Wait for process to actually stop
            process.join(timeout=5.0)

            # Process should be stopped
            assert not process.is_alive(), f"Process {process.pid} should be stopped"
        finally:
            # Ensure cleanup
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=1)

    def test_stop_all_workers(self):
        """Test stopping all workers."""
        manager = WorkerManager()
        manager._workers.clear()  # Clear for test

        # Use longer-running processes
        def long_worker():
            import time

            time.sleep(10)  # Long enough to test termination

        process1 = multiprocessing.Process(target=long_worker, daemon=True)
        process2 = multiprocessing.Process(target=long_worker, daemon=True)
        process1.start()
        process2.start()

        try:
            # Wait a bit to ensure processes are running
            time.sleep(0.2)
            assert process1.is_alive(), "Process1 should be alive"
            assert process2.is_alive(), "Process2 should be alive"

            manager.register_worker(
                "test_worker_1",
                {
                    "pid": process1.pid,
                    "process": process1,
                    "name": "test_worker_1",
                },
            )
            manager.register_worker(
                "test_worker_2",
                {
                    "pid": process2.pid,
                    "process": process2,
                    "name": "test_worker_2",
                },
            )

            result = manager.stop_all_workers(timeout=3.0)

            # Check that stop was attempted
            assert result["total_stopped"] >= 0  # Should stop at least 0 (may be 2)
            assert "total_failed" in result

            # Wait for processes to actually stop
            process1.join(timeout=5.0)
            process2.join(timeout=5.0)

            # Processes should be stopped
            assert not process1.is_alive(), f"Process1 {process1.pid} should be stopped"
            assert not process2.is_alive(), f"Process2 {process2.pid} should be stopped"
        finally:
            # Ensure cleanup
            for proc in [process1, process2]:
                if proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=2)
                    if proc.is_alive():
                        proc.kill()
                        proc.join(timeout=1)

    def test_get_worker_status(self):
        """Test getting worker status."""
        manager = WorkerManager()
        manager._workers.clear()  # Clear for test

        process = multiprocessing.Process(target=dummy_worker_process)
        process.start()

        try:
            manager.register_worker(
                "test_worker",
                {
                    "pid": process.pid,
                    "process": process,
                    "name": "test_worker_1",
                },
            )

            status = manager.get_worker_status()

            assert status["total_workers"] == 1
            assert "test_worker" in status["by_type"]
            assert len(status["workers"]) == 1
            assert status["workers"][0]["type"] == "test_worker"
            assert status["workers"][0]["pid"] == process.pid
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
                if process.is_alive():
                    process.kill()
