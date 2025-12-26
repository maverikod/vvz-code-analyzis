"""
Circuit breaker for service availability tracking.

Tracks service availability and implements exponential backoff when services
are unavailable to reduce CPU load and unnecessary retry attempts.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Service is available
    OPEN = "open"  # Service is unavailable, requests are blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker for tracking service availability.

    Implements exponential backoff when service is unavailable to reduce
    CPU load from constant retry attempts.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2,
        initial_backoff: float = 5.0,
        max_backoff: float = 300.0,  # 5 minutes max
        backoff_multiplier: float = 2.0,
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of consecutive failures before opening circuit
            recovery_timeout: Time in seconds before attempting recovery (half-open)
            success_threshold: Number of successes needed to close circuit from half-open
            initial_backoff: Initial backoff delay in seconds
            max_backoff: Maximum backoff delay in seconds
            backoff_multiplier: Multiplier for exponential backoff
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_multiplier = backoff_multiplier

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.current_backoff = initial_backoff
        self.service_name = "service"

    def set_service_name(self, name: str) -> None:
        """Set service name for logging."""
        self.service_name = name

    def record_success(self) -> None:
        """Record successful service call."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                logger.info(
                    f"Circuit breaker for {self.service_name}: "
                    f"Service recovered, closing circuit"
                )
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.current_backoff = self.initial_backoff
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0
            self.current_backoff = self.initial_backoff

    def record_failure(self) -> None:
        """Record failed service call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            # Failure during half-open, open circuit again
            logger.warning(
                f"Circuit breaker for {self.service_name}: "
                f"Service still unavailable, opening circuit"
            )
            self.state = CircuitState.OPEN
            self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"Circuit breaker for {self.service_name}: "
                    f"Too many failures ({self.failure_count}), opening circuit"
                )
                self.state = CircuitState.OPEN
                self.current_backoff = self.initial_backoff

    def should_attempt(self) -> bool:
        """
        Check if service call should be attempted.

        Returns:
            True if call should be attempted, False if circuit is open
        """
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self.last_failure_time is None:
                return True

            time_since_failure = time.time() - self.last_failure_time
            if time_since_failure >= self.recovery_timeout:
                logger.info(
                    f"Circuit breaker for {self.service_name}: "
                    f"Recovery timeout passed, entering half-open state"
                )
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                return True

            return False

        # HALF_OPEN state - allow attempts
        return True

    def get_backoff_delay(self) -> float:
        """
        Get current backoff delay.

        Returns:
            Backoff delay in seconds
        """
        if self.state == CircuitState.OPEN:
            # Increase backoff exponentially
            delay = min(self.current_backoff, self.max_backoff)
            self.current_backoff = min(
                self.current_backoff * self.backoff_multiplier, self.max_backoff
            )
            return delay

        return 0.0

    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        return self.state

    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.current_backoff = self.initial_backoff
        logger.info(f"Circuit breaker for {self.service_name}: Reset to closed state")

