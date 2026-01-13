"""
Additional tests for request queue to improve coverage.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import time

from code_analysis.core.database_driver_pkg.request_queue import (
    RequestQueue,
    RequestPriority,
    QueuedRequest,
)


class TestRequestQueueCoverage:
    """Test request queue for coverage."""

    def test_dequeue_expired_requests(self):
        """Test dequeuing expired requests."""
        queue = RequestQueue(default_timeout=0.1)
        queue.enqueue("req1", {"data": 1})
        queue.enqueue("req2", {"data": 2})

        # Wait for expiration
        time.sleep(0.2)

        # Dequeue should remove expired requests
        request = queue.dequeue()
        assert request is None  # All expired

    def test_remove_expired_from_all_queues(self):
        """Test removing expired requests from all priority queues."""
        queue = RequestQueue(default_timeout=0.1)
        queue.enqueue("low1", {"data": 1}, RequestPriority.LOW)
        queue.enqueue("normal1", {"data": 2}, RequestPriority.NORMAL)
        queue.enqueue("high1", {"data": 3}, RequestPriority.HIGH)

        time.sleep(0.2)

        # All should be expired
        request = queue.dequeue()
        assert request is None

    def test_remove_request_not_in_queue(self):
        """Test removing request that's not in queue."""
        queue = RequestQueue()
        queue.enqueue("req1", {"data": 1})

        # Try to remove non-existent request
        removed = queue.remove("req2")
        assert removed is False

    def test_get_statistics_snapshot(self):
        """Test getting statistics snapshot."""
        queue = RequestQueue(max_size=100)
        queue.enqueue("req1", {"data": 1})
        queue.enqueue("req2", {"data": 2})

        stats1 = queue.get_statistics()
        assert stats1.current_size == 2

        queue.dequeue()
        stats2 = queue.get_statistics()
        assert stats2.current_size == 1
        assert stats1.current_size == 2  # Snapshot should not change
