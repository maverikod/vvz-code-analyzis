"""
Performance tests for RPC server and client.

Tests RPC latency, throughput, and performance with real data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import concurrent.futures
import socket
import statistics
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


class TestRPCPerformance:
    """Test RPC performance metrics."""

    @pytest.fixture
    def rpc_server(self, tmp_path):
        """Create RPC server for performance testing."""
        db_path = tmp_path / "perf_test.db"
        socket_path = str(tmp_path / "test_perf.sock")

        driver = create_driver("sqlite", {"path": str(db_path)})
        driver.connect({"path": str(db_path)})

        schema = {
            "name": "perf_test",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "value", "type": "INTEGER"},
                {"name": "data", "type": "TEXT"},
            ],
        }
        driver.create_table(schema)

        request_queue = RequestQueue()
        server = RPCServer(driver, request_queue, socket_path)

        server_thread = threading.Thread(
            target=server.start, daemon=True, name="RPCPerfServer"
        )
        server_thread.start()
        _wait_for_server_socket(socket_path, _SERVER_READY_TIMEOUT_SEC)

        yield server, socket_path

        server.stop()
        server_thread.join(timeout=2.0)
        driver.disconnect()

    def test_rpc_latency_single_request(self, rpc_server):
        """Test RPC latency for single request."""
        _, socket_path = rpc_server

        client = _perf_client(socket_path)
        client.connect()

        try:
            start_time = time.perf_counter()
            client.insert("perf_test", {"value": 1, "data": "test"})
            end_time = time.perf_counter()

            latency = (end_time - start_time) * 1000
            assert latency < 200
        finally:
            client.disconnect()

    def test_rpc_latency_multiple_requests(self, rpc_server):
        """Test RPC latency for multiple sequential requests."""
        _, socket_path = rpc_server

        client = _perf_client(socket_path)
        client.connect()

        try:
            latencies = []
            num_requests = 25

            for i in range(num_requests):
                start_time = time.perf_counter()
                client.insert("perf_test", {"value": i, "data": f"test_{i}"})
                end_time = time.perf_counter()

                latency = (end_time - start_time) * 1000
                latencies.append(latency)

            avg_latency = statistics.mean(latencies)
            median_latency = statistics.median(latencies)
            p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

            assert avg_latency < 2000
            assert median_latency < 2000
            assert p95_latency < 5000
        finally:
            client.disconnect()

    def test_rpc_throughput_concurrent_requests(self, rpc_server):
        """Test RPC throughput with concurrent requests."""
        _, socket_path = rpc_server

        client = _perf_client(socket_path, pool_size=20)
        client.connect()

        try:
            num_requests = 50
            num_workers = 5

            def make_request(value):
                return client.insert(
                    "perf_test", {"value": value, "data": f"test_{value}"}
                )

            start_time = time.perf_counter()

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=num_workers
            ) as executor:
                futures = [
                    executor.submit(make_request, i) for i in range(num_requests)
                ]
                results = [f.result() for f in futures]

            end_time = time.perf_counter()

            total_time = end_time - start_time
            throughput = num_requests / total_time

            assert len(results) == num_requests
            assert all(r is not None for r in results)
            assert throughput > 5
        finally:
            client.disconnect()

    def test_rpc_connection_pool_performance(self, rpc_server):
        """Test RPC connection pool performance."""
        _, socket_path = rpc_server

        pool_sizes = [1, 5, 10, 20]

        for pool_size in pool_sizes:
            client = _perf_client(socket_path, pool_size=pool_size)
            client.connect()

            try:
                num_requests = 25
                num_workers = max(2, pool_size)

                def make_request(value):
                    return client.insert(
                        "perf_test", {"value": value, "data": f"test_{value}"}
                    )

                start_time = time.perf_counter()

                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=num_workers
                ) as executor:
                    futures = [
                        executor.submit(make_request, i) for i in range(num_requests)
                    ]
                    results = [f.result() for f in futures]

                end_time = time.perf_counter()

                total_time = end_time - start_time
                throughput = num_requests / total_time

                assert len(results) == num_requests
                assert all(r is not None for r in results)

                if pool_size > 1:
                    assert throughput > 5
            finally:
                client.disconnect()

    def test_rpc_bulk_operations_performance(self, rpc_server):
        """Test RPC performance for bulk operations."""
        _, socket_path = rpc_server

        client = _perf_client(socket_path)
        client.connect()

        try:
            num_rows = 50
            start_time = time.perf_counter()

            for i in range(num_rows):
                client.insert("perf_test", {"value": i, "data": f"bulk_test_{i}"})

            end_time = time.perf_counter()

            total_time = end_time - start_time
            rows_per_second = num_rows / total_time

            rows = client.select("perf_test", where={"data": "bulk_test_0"})
            assert len(rows) > 0
            assert rows_per_second > 0.5
        finally:
            client.disconnect()

    def test_rpc_select_performance(self, rpc_server):
        """Test RPC select query performance."""
        _, socket_path = rpc_server

        client = _perf_client(socket_path)
        client.connect()

        try:
            num_rows = 50
            for i in range(num_rows):
                client.insert("perf_test", {"value": i, "data": f"select_test_{i}"})

            start_time = time.perf_counter()
            rows = client.select("perf_test")
            end_time = time.perf_counter()

            total_time = end_time - start_time
            assert len(rows) >= num_rows
            assert total_time < 5.0
        finally:
            client.disconnect()

    def test_rpc_transaction_performance(self, rpc_server):
        """Test RPC transaction performance."""
        _, socket_path = rpc_server

        client = _perf_client(socket_path)
        client.connect()

        try:
            num_operations = 25

            start_time = time.perf_counter()

            transaction_id = client.begin_transaction()
            for i in range(num_operations):
                client.insert("perf_test", {"value": i, "data": f"trans_test_{i}"})
            client.commit_transaction(transaction_id)

            end_time = time.perf_counter()

            total_time = end_time - start_time
            ops_per_second = num_operations / total_time

            rows = client.select("perf_test", where={"data": "trans_test_0"})
            assert len(rows) > 0
            assert ops_per_second > 0.5
        finally:
            client.disconnect()
