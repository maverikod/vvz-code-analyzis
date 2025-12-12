"""
Production wrapper for test data detection.

This module provides a production stub for test data detection.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# Production wrapper for is_test_data

def is_test_data(obj):
    """
    Production stub: всегда возвращает False.
    В тестах monkeypatch-ить на реальную функцию из tests.api_standard_test_utils.
    """
    return False
