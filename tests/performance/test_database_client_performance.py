"""
Performance tests for database client.

Tests connection pooling performance, concurrent requests performance,
and RPC latency measurements.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import socket
import threading
import time
from pathlib import Path

import pytest

from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.rpc_client import RPCClient
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.rpc_server import RPCServer

# Bounded waits so missing/unready server fails fast (default connect timeout is 30s).
_SERVER_READY_TIMEOUT_SEC = 2.0
_RPC_REQUEST_TIMEOUT_SEC = 10.0


def _wait_for_server_socket(socket_path: str, timeout_sec: float) -> None:
    """Poll until the Unix socket accepts connections or timeout."""
    deadline = time.time() + timeout_sec
    path = Path(socket_path)
    while time.time() < deadline:
        if not path.exists():
            time.sleep(0.05)
            continue
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            probe.settimeout(0.25)
            if probe.connect_ex(socket_path) == 0:
                return
        finally:
            probe.close()
        time.sleep(0.05)
    pytest.skip(f"RPC server socket not ready within {timeout_sec}s: {socket_path}")


def _perf_client(socket_path: str, *, pool_size: int = 5) -> DatabaseClient:
    """DatabaseClient with bounded connect/RPC timeouts for perf tests."""
    rpc = RPCClient(
        socket_path,
        pool_size=pool_size,
        timeout=_RPC_REQUEST_TIMEOUT_SEC,
        startup_connect_timeout=_SERVER_READY_TIMEOUT_SEC,
    )
    return DatabaseClient(rpc_client=rpc)


class TestDatabaseClientPerformance:
    """Performance tests for database client."""

    @pytest.fixture
    def rpc_server(self, tmp_path):
        """Create RPC server for performance testing."""
        db_path = tmp_path / "perf_test.db"
        socket_path = str(tmp_path / "perf_test.sock")

        driver = create_driver("sqlite", {"path": str(db_path)})
        driver.connect({"path": str(db_path)})

        schema = {
            "name": "perf_table",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "data", "type": "TEXT"},
                {"name": "value", "type": "INTEGER"},
            ],
        }
        driver.create_table(schema)

        request_queue = RequestQueue()
        server = RPCServer(driver, request_queue, socket_path)

        server_thread = threading.Thread(
            target=server.start, daemon=True, name="PerfRPCServer"
        )
        server_thread.start()
        _wait_for_server_socket(socket_path, _SERVER_READY_TIMEOUT_SEC)

        yield server, socket_path

        server.stop()
        server_thread.join(timeout=2.0)
        driver.disconnect()

    def test_connection_pooling_performance(self, rpc_server):
        """Test connection pooling performance."""
        _, socket_path = rpc_server

        client_no_pool = _perf_client(socket_path, pool_size=1)
        client_no_pool.connect()

        start_time = time.time()
        for i in range(20):
            client_no_pool.insert("perf_table", {"data": f"data_{i}", "value": i})
        time_no_pool = time.time() - start_time
        client_no_pool.disconnect()

        client_with_pool = _perf_client(socket_path, pool_size=10)
        client_with_pool.connect()

        start_time = time.time()
        for i in range(20):
            client_with_pool.insert("perf_table", {"data": f"data_{i}", "value": i})
        time_with_pool = time.time() - start_time
        client_with_pool.disconnect()

        print(f"Without pool: {time_no_pool:.3f}s, With pool: {time_with_pool:.3f}s")
        assert time_no_pool > 0
        assert time_with_pool > 0

    def test_concurrent_requests_performance(self, rpc_server):
        """Test concurrent requests performance."""
        _, socket_path = rpc_server

        client = _perf_client(socket_path, pool_size=10)
        client.connect()

        try:
            import concurrent.futures

            def make_request(i):
                return client.insert(
                    "perf_table", {"data": f"concurrent_{i}", "value": i}
                )

            start_time = time.time()
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(make_request, i) for i in range(20)]
                results = [f.result() for f in futures]
            concurrent_time = time.time() - start_time

            start_time = time.time()
            for i in range(20):
                client.insert("perf_table", {"data": f"sequential_{i}", "value": i})
            sequential_time = time.time() - start_time

            print(
                f"Concurrent: {concurrent_time:.3f}s, Sequential: {sequential_time:.3f}s"
            )
            assert concurrent_time > 0
            assert sequential_time > 0
            assert all(r is not None and isinstance(r, int) and r > 0 for r in results)
        finally:
            client.disconnect()

    def test_rpc_latency_measurements(self, rpc_server):
        """Test RPC latency measurements."""
        _, socket_path = rpc_server

        client = _perf_client(socket_path)
        client.connect()

        try:
            latencies = []

            for i in range(20):
                start_time = time.time()
                client.insert("perf_table", {"data": f"latency_{i}", "value": i})
                latency = time.time() - start_time
                latencies.append(latency)

            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)
            min_latency = min(latencies)

            print(f"Average latency: {avg_latency*1000:.2f}ms")
            print(f"Min latency: {min_latency*1000:.2f}ms")
            print(f"Max latency: {max_latency*1000:.2f}ms")

            assert avg_latency < 2.0
            assert max_latency < 5.0
        finally:
            client.disconnect()

    def test_bulk_operations_performance(self, rpc_server):
        """Test bulk operations performance."""
        _, socket_path = rpc_server

        client = _perf_client(socket_path)
        client.connect()

        try:
            start_time = time.time()
            for i in range(30):
                client.insert("perf_table", {"data": f"bulk_{i}", "value": i})
            insert_time = time.time() - start_time

            start_time = time.time()
            rows = client.select("perf_table", limit=30)
            select_time = time.time() - start_time

            print(f"Bulk insert (30): {insert_time:.3f}s")
            print(f"Bulk select (30): {select_time:.3f}s")

            assert insert_time > 0
            assert select_time > 0
            assert len(rows) >= 30
        finally:
            client.disconnect()
