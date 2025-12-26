"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Failure detection facade.

This module provides a unified interface for failure detection functionality.
"""

from .failure_detection.failure_detection_facade import FailureDetector

__all__ = ["FailureDetector"]
