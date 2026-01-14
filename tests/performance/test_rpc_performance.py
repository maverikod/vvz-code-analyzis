"""
Performance tests for RPC server and client.

Tests RPC latency, throughput, and performance with real data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import threading
import time
import statistics

from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.rpc_server import RPCServer


class TestRPCPerformance:
    """Test RPC performance metrics."""

    @pytest.fixture
    def rpc_server(self, tmp_path):
        """Create RPC server for performance testing."""
        db_path = tmp_path / "perf_test.db"
        socket_path = str(tmp_path / "test_perf.sock")

        # Create driver
        driver = create_driver("sqlite", {"path": str(db_path)})

        # Create test table
        schema = {
            "name": "perf_test",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "value", "type": "INTEGER"},
                {"name": "data", "type": "TEXT"},
            ],
        }
        driver.create_table(schema)

        # Start RPC server
        request_queue = RequestQueue()
        server = RPCServer(driver, request_queue, socket_path)

        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.2)  # Wait for server to start

        yield server, socket_path

        # Cleanup
        server.stop()
        driver.disconnect()

    def test_rpc_latency_single_request(self, rpc_server):
        """Test RPC latency for single request."""
        _, socket_path = rpc_server

        client = DatabaseClient(socket_path=socket_path)
        client.connect()

        try:
            # Measure latency for single insert
            start_time = time.perf_counter()
            client.insert("perf_test", {"value": 1, "data": "test"})
            end_time = time.perf_counter()

            latency = (end_time - start_time) * 1000  # Convert to milliseconds
            # Allow up to 200ms for single request (includes RPC overhead)
            assert latency < 200  # Should be less than 200ms
        finally:
            client.disconnect()

    def test_rpc_latency_multiple_requests(self, rpc_server):
        """Test RPC latency for multiple sequential requests."""
        _, socket_path = rpc_server

        client = DatabaseClient(socket_path=socket_path)
        client.connect()

        try:
            latencies = []
            num_requests = 100

            for i in range(num_requests):
                start_time = time.perf_counter()
                client.insert("perf_test", {"value": i, "data": f"test_{i}"})
                end_time = time.perf_counter()

                latency = (end_time - start_time) * 1000  # Convert to milliseconds
                latencies.append(latency)

            # Calculate statistics
            avg_latency = statistics.mean(latencies)
            median_latency = statistics.median(latencies)
            p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

            # Assert reasonable performance
            assert avg_latency < 50  # Average should be less than 50ms
            assert median_latency < 50  # Median should be less than 50ms
            assert p95_latency < 200  # 95th percentile should be less than 200ms
        finally:
            client.disconnect()

    def test_rpc_throughput_concurrent_requests(self, rpc_server):
        """Test RPC throughput with concurrent requests."""
        _, socket_path = rpc_server

        client = DatabaseClient(socket_path=socket_path, pool_size=20)
        client.connect()

        try:
            num_requests = 1000
            num_workers = 20

            def make_request(value):
                return client.insert(
                    "perf_test", {"value": value, "data": f"test_{value}"}
                )

            start_time = time.perf_counter()

            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=num_workers
            ) as executor:
                futures = [
                    executor.submit(make_request, i) for i in range(num_requests)
                ]
                results = [f.result() for f in futures]

            end_time = time.perf_counter()

            total_time = end_time - start_time
            throughput = num_requests / total_time  # Requests per second

            # Verify all requests succeeded
            assert len(results) == num_requests
            assert all(r is not None for r in results)

            # Assert reasonable throughput
            assert throughput > 100  # Should handle at least 100 requests/second
        finally:
            client.disconnect()

    def test_rpc_connection_pool_performance(self, rpc_server):
        """Test RPC connection pool performance."""
        _, socket_path = rpc_server

        # Test with different pool sizes
        pool_sizes = [1, 5, 10, 20]

        for pool_size in pool_sizes:
            client = DatabaseClient(socket_path=socket_path, pool_size=pool_size)
            client.connect()

            try:
                num_requests = 100
                num_workers = pool_size * 2  # More workers than pool size

                def make_request(value):
                    return client.insert(
                        "perf_test", {"value": value, "data": f"test_{value}"}
                    )

                start_time = time.perf_counter()

                import concurrent.futures

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

                # Verify all requests succeeded
                assert len(results) == num_requests
                assert all(r is not None for r in results)

                # Larger pool should generally perform better (but not always due to overhead)
                if pool_size > 1:
                    assert throughput > 50  # Should handle at least 50 requests/second
            finally:
                client.disconnect()

    def test_rpc_bulk_operations_performance(self, rpc_server):
        """Test RPC performance for bulk operations."""
        _, socket_path = rpc_server

        client = DatabaseClient(socket_path=socket_path)
        client.connect()

        try:
            # Test bulk insert performance
            num_rows = 1000
            start_time = time.perf_counter()

            for i in range(num_rows):
                client.insert("perf_test", {"value": i, "data": f"bulk_test_{i}"})

            end_time = time.perf_counter()

            total_time = end_time - start_time
            rows_per_second = num_rows / total_time

            # Verify all rows were inserted
            rows = client.select("perf_test", where={"data": "bulk_test_0"})
            assert len(rows) > 0

            # Assert reasonable performance
            assert rows_per_second > 200  # Should insert at least 200 rows/second
        finally:
            client.disconnect()

    def test_rpc_select_performance(self, rpc_server):
        """Test RPC select query performance."""
        _, socket_path = rpc_server

        client = DatabaseClient(socket_path=socket_path)
        client.connect()

        try:
            # Insert test data
            num_rows = 1000
            for i in range(num_rows):
                client.insert("perf_test", {"value": i, "data": f"select_test_{i}"})

            # Test select performance
            start_time = time.perf_counter()
            rows = client.select("perf_test")
            end_time = time.perf_counter()

            total_time = end_time - start_time
            assert len(rows) >= num_rows

            # Select should be reasonably fast
            assert total_time < 1.0  # Should complete in less than 1 second
        finally:
            client.disconnect()

    def test_rpc_transaction_performance(self, rpc_server):
        """Test RPC transaction performance."""
        _, socket_path = rpc_server

        client = DatabaseClient(socket_path=socket_path)
        client.connect()

        try:
            num_operations = 100

            # Test transaction performance
            start_time = time.perf_counter()

            transaction_id = client.begin_transaction()
            for i in range(num_operations):
                client.insert("perf_test", {"value": i, "data": f"trans_test_{i}"})
            client.commit_transaction(transaction_id)

            end_time = time.perf_counter()

            total_time = end_time - start_time
            ops_per_second = num_operations / total_time

            # Verify all operations were committed
            rows = client.select("perf_test", where={"data": "trans_test_0"})
            assert len(rows) > 0

            # Transactions should be reasonably fast
            assert ops_per_second > 100  # Should handle at least 100 ops/second
        finally:
            client.disconnect()
