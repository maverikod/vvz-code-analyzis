"""
Helper methods for database client.

Provides utility methods for processing RPC responses and error handling.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

from .protocol import RPCResponse
from .exceptions import RPCResponseError


class _ClientHelpersMixin:
    """Mixin class with helper methods for processing RPC responses."""

    def _extract_success(self, response: RPCResponse) -> bool:
        """Extract success value from response.

        Args:
            response: RPC response

        Returns:
            Success value

        Raises:
            RPCResponseError: If response contains error
        """
        if response.is_error():
            raise self._create_response_error(response)

        result_data = response.result
        if result_data and isinstance(result_data, dict):
            return result_data.get("success", False)
        return False

    def _extract_result_data(self, response: RPCResponse) -> Any:
        """Extract result data from response.

        Args:
            response: RPC response

        Returns:
            Result data (dict, list, or other type depending on result type)

        Raises:
            RPCResponseError: If response contains error
        """
        if response.is_error():
            raise self._create_response_error(response)

        result_data = response.result
        if result_data and isinstance(result_data, dict):
            # Handle both SuccessResult and DataResult formats
            # Both formats have "data" key, so always extract it
            # SuccessResult format: {"success": True, "data": {"row_id": 1}}
            # DataResult format: {"success": True, "data": [...]}
            # For execute() method, we need to preserve the full structure
            # Return the full dict - execute() will handle extraction
            return result_data
        # If result_data is not a dict (e.g., list for DataResult), return as-is
        return result_data if result_data is not None else {}

    def _create_response_error(self, response: RPCResponse) -> RPCResponseError:
        """Create RPCResponseError from RPC response.

        Args:
            response: RPC response with error

        Returns:
            RPCResponseError instance
        """
        if response.error:
            return RPCResponseError(
                message=response.error.message,
                error_code=response.error.code.value,
                error_data=response.error.data,
            )
        return RPCResponseError(message="Unknown error")
