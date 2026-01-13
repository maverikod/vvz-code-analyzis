"""
Request queue for database driver process.

Thread-safe queue for managing database operation requests with priorities,
timeouts, and size limits.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, Optional

from .exceptions import RequestQueueError, RequestQueueFullError

logger = logging.getLogger(__name__)


class RequestPriority(IntEnum):
    """Request priority levels."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class QueuedRequest:
    """Request in queue."""

    request_id: str
    request: Any
    priority: RequestPriority
    created_at: float = field(default_factory=time.time)
    timeout: Optional[float] = None

    def is_expired(self) -> bool:
        """Check if request has expired.

        Returns:
            True if request has expired, False otherwise
        """
        if self.timeout is None:
            return False
        return time.time() - self.created_at > self.timeout


@dataclass
class QueueStatistics:
    """Queue statistics."""

    total_requests: int = 0
    pending_requests: int = 0
    processed_requests: int = 0
    expired_requests: int = 0
    rejected_requests: int = 0
    current_size: int = 0
    max_size: int = 0


class RequestQueue:
    """Thread-safe request queue with priorities and timeouts.

    Features:
    - Thread-safe operations
    - Request prioritization
    - Queue size limits
    - Request timeout handling
    - Queue statistics
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_timeout: Optional[float] = 300.0,
    ):
        """Initialize request queue.

        Args:
            max_size: Maximum queue size (default: 1000)
            default_timeout: Default request timeout in seconds (default: 300s, None = no timeout)
        """
        self.max_size = max_size
        self.default_timeout = default_timeout
        self._lock = threading.Lock()
        self._queues: Dict[RequestPriority, deque] = {
            priority: deque() for priority in RequestPriority
        }
        self._request_map: Dict[str, QueuedRequest] = {}
        self._statistics = QueueStatistics(max_size=max_size)

    def enqueue(
        self,
        request_id: str,
        request: Any,
        priority: RequestPriority = RequestPriority.NORMAL,
        timeout: Optional[float] = None,
    ) -> None:
        """Add request to queue.

        Args:
            request_id: Unique request identifier
            request: Request object
            priority: Request priority (default: NORMAL)
            timeout: Request timeout in seconds (default: uses default_timeout)

        Raises:
            RequestQueueFullError: If queue is full
            RequestQueueError: If request_id already exists
        """
        with self._lock:
            if request_id in self._request_map:
                raise RequestQueueError(f"Request {request_id} already exists in queue")

            if self._statistics.current_size >= self.max_size:
                self._statistics.rejected_requests += 1
                raise RequestQueueFullError(f"Queue is full (max_size={self.max_size})")

            timeout_value = timeout if timeout is not None else self.default_timeout
            queued_request = QueuedRequest(
                request_id=request_id,
                request=request,
                priority=priority,
                timeout=timeout_value,
            )

            self._queues[priority].append(queued_request)
            self._request_map[request_id] = queued_request
            self._statistics.total_requests += 1
            self._statistics.current_size += 1
            self._statistics.pending_requests += 1

    def dequeue(self) -> Optional[QueuedRequest]:
        """Get next request from queue (highest priority first).

        Removes expired requests automatically.

        Returns:
            Next request or None if queue is empty
        """
        with self._lock:
            # Remove expired requests first
            self._remove_expired()

            # Get request from highest priority queue
            for priority in reversed(RequestPriority):
                queue = self._queues[priority]
                while queue:
                    request = queue.popleft()
                    if request.is_expired():
                        self._statistics.expired_requests += 1
                        del self._request_map[request.request_id]
                        self._statistics.current_size -= 1
                        self._statistics.pending_requests -= 1
                        continue
                    # Found valid request
                    del self._request_map[request.request_id]
                    self._statistics.current_size -= 1
                    self._statistics.pending_requests -= 1
                    self._statistics.processed_requests += 1
                    return request

            return None

    def get(self, request_id: str) -> Optional[QueuedRequest]:
        """Get request by ID without removing it.

        Args:
            request_id: Request identifier

        Returns:
            Request or None if not found
        """
        with self._lock:
            return self._request_map.get(request_id)

    def remove(self, request_id: str) -> bool:
        """Remove request from queue.

        Args:
            request_id: Request identifier

        Returns:
            True if request was removed, False if not found
        """
        with self._lock:
            if request_id not in self._request_map:
                return False

            request = self._request_map[request_id]
            # Remove from priority queue
            queue = self._queues[request.priority]
            try:
                queue.remove(request)
            except ValueError:
                # Request was already removed from queue (possible race condition)
                # This is safe to ignore - request is being removed anyway
                logger.debug(
                    f"Request {request_id} was already removed from queue "
                    "(possible race condition, safe to ignore)"
                )

            del self._request_map[request_id]
            self._statistics.current_size -= 1
            self._statistics.pending_requests -= 1
            return True

    def _remove_expired(self) -> None:
        """Remove expired requests from all queues."""
        for priority in RequestPriority:
            queue = self._queues[priority]
            # Iterate in reverse to safely remove items
            for i in range(len(queue) - 1, -1, -1):
                request = queue[i]
                if request.is_expired():
                    queue.remove(request)
                    del self._request_map[request.request_id]
                    self._statistics.current_size -= 1
                    self._statistics.pending_requests -= 1
                    self._statistics.expired_requests += 1

    def size(self) -> int:
        """Get current queue size.

        Returns:
            Number of requests in queue
        """
        with self._lock:
            return self._statistics.current_size

    def is_empty(self) -> bool:
        """Check if queue is empty.

        Returns:
            True if queue is empty, False otherwise
        """
        with self._lock:
            return self._statistics.current_size == 0

    def is_full(self) -> bool:
        """Check if queue is full.

        Returns:
            True if queue is full, False otherwise
        """
        with self._lock:
            return self._statistics.current_size >= self.max_size

    def get_statistics(self) -> QueueStatistics:
        """Get queue statistics.

        Returns:
            Queue statistics snapshot
        """
        with self._lock:
            # Create a copy to avoid race conditions
            stats = QueueStatistics(
                total_requests=self._statistics.total_requests,
                pending_requests=self._statistics.pending_requests,
                processed_requests=self._statistics.processed_requests,
                expired_requests=self._statistics.expired_requests,
                rejected_requests=self._statistics.rejected_requests,
                current_size=self._statistics.current_size,
                max_size=self._statistics.max_size,
            )
            return stats

    def clear(self) -> None:
        """Clear all requests from queue."""
        with self._lock:
            for priority in RequestPriority:
                self._queues[priority].clear()
            self._request_map.clear()
            self._statistics.current_size = 0
            self._statistics.pending_requests = 0
