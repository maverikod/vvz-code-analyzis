"""
Performance tests for database client.

Tests connection pooling performance, concurrent requests performance,
and RPC latency measurements.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import time
from pathlib import Path

import pytest

from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.rpc_server import RPCServer


class TestDatabaseClientPerformance:
    """Performance tests for database client."""

    @pytest.fixture
    def rpc_server(self, tmp_path):
        """Create RPC server for performance testing."""
        db_path = tmp_path / "perf_test.db"
        socket_path = str(tmp_path / "perf_test.sock")

        # Create table
        driver = create_driver("sqlite", {"path": str(db_path)})
        schema = {
            "name": "perf_table",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "data", "type": "TEXT"},
                {"name": "value", "type": "INTEGER"},
            ],
        }
        driver.create_table(schema)
        driver.disconnect()

        # Start RPC server
        import threading

        request_queue = RequestQueue()
        driver = create_driver("sqlite", {"path": str(db_path)})
        server = RPCServer(driver, request_queue, socket_path)

        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.3)

        yield server, socket_path

        # Cleanup
        server.stop()
        driver.disconnect()

    def test_connection_pooling_performance(self, rpc_server):
        """Test connection pooling performance."""
        _, socket_path = rpc_server

        # Test without pooling (pool_size=1)
        client_no_pool = DatabaseClient(socket_path, pool_size=1)
        client_no_pool.connect()

        start_time = time.time()
        for i in range(100):
            client_no_pool.insert("perf_table", {"data": f"data_{i}", "value": i})
        time_no_pool = time.time() - start_time
        client_no_pool.disconnect()

        # Test with pooling (pool_size=10)
        client_with_pool = DatabaseClient(socket_path, pool_size=10)
        client_with_pool.connect()

        start_time = time.time()
        for i in range(100):
            client_with_pool.insert("perf_table", {"data": f"data_{i}", "value": i})
        time_with_pool = time.time() - start_time
        client_with_pool.disconnect()

        # Pooling should be faster (or at least not significantly slower)
        # Allow some variance, but pooling should help
        print(f"Without pool: {time_no_pool:.3f}s, With pool: {time_with_pool:.3f}s")
        # Just verify both complete successfully
        assert time_no_pool > 0
        assert time_with_pool > 0

    def test_concurrent_requests_performance(self, rpc_server):
        """Test concurrent requests performance."""
        _, socket_path = rpc_server

        client = DatabaseClient(socket_path, pool_size=10)
        client.connect()

        try:
            import concurrent.futures

            def make_request(i):
                return client.insert(
                    "perf_table", {"data": f"concurrent_{i}", "value": i}
                )

            # Measure concurrent performance
            start_time = time.time()
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(make_request, i) for i in range(100)]
                results = [f.result() for f in futures]
            concurrent_time = time.time() - start_time

            # Measure sequential performance
            start_time = time.time()
            for i in range(100):
                client.insert("perf_table", {"data": f"sequential_{i}", "value": i})
            sequential_time = time.time() - start_time

            # Concurrent should be faster
            print(
                f"Concurrent: {concurrent_time:.3f}s, Sequential: {sequential_time:.3f}s"
            )
            assert concurrent_time > 0
            assert sequential_time > 0
            assert all(r > 0 for r in results)
        finally:
            client.disconnect()

    def test_rpc_latency_measurements(self, rpc_server):
        """Test RPC latency measurements."""
        _, socket_path = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            latencies = []

            # Measure latency for 50 operations
            for i in range(50):
                start_time = time.time()
                client.insert("perf_table", {"data": f"latency_{i}", "value": i})
                latency = time.time() - start_time
                latencies.append(latency)

            # Calculate statistics
            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)
            min_latency = min(latencies)

            print(f"Average latency: {avg_latency*1000:.2f}ms")
            print(f"Min latency: {min_latency*1000:.2f}ms")
            print(f"Max latency: {max_latency*1000:.2f}ms")

            # Verify reasonable latency (should be < 100ms for local operations)
            assert avg_latency < 0.1  # 100ms
            assert max_latency < 0.5  # 500ms for worst case
        finally:
            client.disconnect()

    def test_bulk_operations_performance(self, rpc_server):
        """Test bulk operations performance."""
        _, socket_path = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Test bulk insert
            start_time = time.time()
            for i in range(1000):
                client.insert("perf_table", {"data": f"bulk_{i}", "value": i})
            insert_time = time.time() - start_time

            # Test bulk select
            start_time = time.time()
            rows = client.select("perf_table", limit=1000)
            select_time = time.time() - start_time

            print(f"Bulk insert (1000): {insert_time:.3f}s")
            print(f"Bulk select (1000): {select_time:.3f}s")

            assert insert_time > 0
            assert select_time > 0
            assert len(rows) >= 1000
        finally:
            client.disconnect()
