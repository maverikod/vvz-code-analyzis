"""
Tests for request queue.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import time
import threading

from code_analysis.core.database_driver_pkg.request_queue import (
    RequestQueue,
    RequestPriority,
    QueuedRequest,
    QueueStatistics,
)


class TestRequestQueue:
    """Test RequestQueue class."""

    def test_create_queue(self):
        """Test creating request queue."""
        queue = RequestQueue(max_size=100, default_timeout=60.0)
        assert queue.max_size == 100
        assert queue.default_timeout == 60.0
        assert queue.size() == 0
        assert queue.is_empty()

    def test_enqueue_dequeue(self):
        """Test basic enqueue and dequeue operations."""
        queue = RequestQueue()
        queue.enqueue("req1", {"data": "test"}, RequestPriority.NORMAL)
        assert queue.size() == 1
        assert not queue.is_empty()

        request = queue.dequeue()
        assert request is not None
        assert request.request_id == "req1"
        assert request.request == {"data": "test"}
        assert queue.size() == 0
        assert queue.is_empty()

    def test_priority_ordering(self):
        """Test that higher priority requests are dequeued first."""
        queue = RequestQueue()
        queue.enqueue("low", {"priority": "low"}, RequestPriority.LOW)
        queue.enqueue("high", {"priority": "high"}, RequestPriority.HIGH)
        queue.enqueue("normal", {"priority": "normal"}, RequestPriority.NORMAL)

        # Should get HIGH first
        request = queue.dequeue()
        assert request.request_id == "high"

        # Then NORMAL
        request = queue.dequeue()
        assert request.request_id == "normal"

        # Then LOW
        request = queue.dequeue()
        assert request.request_id == "low"

    def test_queue_full(self):
        """Test queue full error."""
        queue = RequestQueue(max_size=2)
        queue.enqueue("req1", {"data": 1})
        queue.enqueue("req2", {"data": 2})

        with pytest.raises(Exception):  # RequestQueueFullError
            queue.enqueue("req3", {"data": 3})

    def test_duplicate_request_id(self):
        """Test that duplicate request IDs are rejected."""
        queue = RequestQueue()
        queue.enqueue("req1", {"data": 1})

        with pytest.raises(Exception):  # RequestQueueError
            queue.enqueue("req1", {"data": 2})

    def test_request_timeout(self):
        """Test request timeout handling."""
        queue = RequestQueue(default_timeout=0.1)  # 100ms timeout
        queue.enqueue("req1", {"data": 1})

        # Wait for timeout
        time.sleep(0.2)

        # Request should be expired
        request = queue.dequeue()
        assert request is None  # Expired requests are removed

    def test_custom_timeout(self):
        """Test custom timeout per request."""
        queue = RequestQueue(default_timeout=300.0)
        queue.enqueue("req1", {"data": 1}, timeout=0.1)

        time.sleep(0.2)
        request = queue.dequeue()
        assert request is None

    def test_get_request(self):
        """Test getting request by ID without removing."""
        queue = RequestQueue()
        queue.enqueue("req1", {"data": 1})

        request = queue.get("req1")
        assert request is not None
        assert request.request_id == "req1"

        # Request should still be in queue
        assert queue.size() == 1

    def test_remove_request(self):
        """Test removing request from queue."""
        queue = RequestQueue()
        queue.enqueue("req1", {"data": 1})
        queue.enqueue("req2", {"data": 2})

        removed = queue.remove("req1")
        assert removed is True
        assert queue.size() == 1

        # Try to remove non-existent request
        removed = queue.remove("req3")
        assert removed is False

    def test_statistics(self):
        """Test queue statistics."""
        queue = RequestQueue(max_size=100)
        queue.enqueue("req1", {"data": 1})
        queue.enqueue("req2", {"data": 2})

        stats = queue.get_statistics()
        assert stats.total_requests == 2
        assert stats.pending_requests == 2
        assert stats.current_size == 2
        assert stats.max_size == 100

        queue.dequeue()
        stats = queue.get_statistics()
        assert stats.processed_requests == 1
        assert stats.pending_requests == 1
        assert stats.current_size == 1

    def test_clear_queue(self):
        """Test clearing queue."""
        queue = RequestQueue()
        queue.enqueue("req1", {"data": 1})
        queue.enqueue("req2", {"data": 2})

        queue.clear()
        assert queue.size() == 0
        assert queue.is_empty()

    def test_thread_safety(self):
        """Test thread-safe operations."""
        queue = RequestQueue(max_size=1000)
        results = []
        results_lock = threading.Lock()

        def enqueue_worker(worker_id):
            for i in range(100):
                queue.enqueue(f"req_{worker_id}_{i}", {"data": i})

        def dequeue_worker():
            for _ in range(100):
                request = queue.dequeue()
                if request:
                    with results_lock:
                        results.append(request.request_id)

        threads = []
        for worker_id in range(5):
            t = threading.Thread(target=enqueue_worker, args=(worker_id,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        dequeue_threads = []
        for _ in range(5):
            t = threading.Thread(target=dequeue_worker)
            dequeue_threads.append(t)
            t.start()

        for t in dequeue_threads:
            t.join()

        # All requests should be processed
        assert len(results) == 500
        assert queue.size() == 0


class TestQueuedRequest:
    """Test QueuedRequest class."""

    def test_create_request(self):
        """Test creating queued request."""
        request = QueuedRequest(
            request_id="req1",
            request={"data": 1},
            priority=RequestPriority.HIGH,
            timeout=60.0,
        )
        assert request.request_id == "req1"
        assert request.priority == RequestPriority.HIGH
        assert request.timeout == 60.0

    def test_is_expired(self):
        """Test expiration check."""
        request = QueuedRequest(
            request_id="req1",
            request={"data": 1},
            priority=RequestPriority.NORMAL,
            timeout=0.1,
        )
        assert not request.is_expired()

        time.sleep(0.2)
        assert request.is_expired()

    def test_no_timeout(self):
        """Test request without timeout."""
        request = QueuedRequest(
            request_id="req1",
            request={"data": 1},
            priority=RequestPriority.NORMAL,
            timeout=None,
        )
        assert not request.is_expired()
        time.sleep(0.1)
        assert not request.is_expired()  # No timeout means never expires
