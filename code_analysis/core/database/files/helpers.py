"""
File helpers: last_modified normalization.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Optional

# Julian day for 1970-01-01 00:00:00 UTC (normalize last_modified to Unix)
_JD_UNIX_EPOCH = 2440587.5


def _last_modified_to_unix(value: Any) -> Optional[float]:
    """Normalize last_modified from DB to Unix timestamp for comparison with os.stat().st_mtime.

    files.last_modified may be stored as Unix timestamp, datetime (Julian convention),
    or raw float. Converts to Unix seconds for comparison.

    Args:
        value: last_modified from DB: None, datetime, or float (Unix or Julian).

    Returns:
        Unix timestamp (seconds since 1970-01-01 UTC) or None.
    """
    if value is None:
        return None
    if hasattr(value, "timestamp"):
        return value.timestamp()
    try:
        v = float(value)
        if v >= 1e9:
            return v
        return (v - _JD_UNIX_EPOCH) * 86400.0
    except (TypeError, ValueError):
        return None
