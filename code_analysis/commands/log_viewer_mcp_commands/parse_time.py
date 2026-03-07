"""
Time parsing helper for log viewer commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from datetime import datetime
from typing import Optional


def parse_time_optional(time_str: Optional[str]) -> Optional[datetime]:
    """Parse time string to datetime. ISO or YYYY-MM-DD HH:MM:SS or YYYY-MM-DD."""
    if not time_str:
        return None
    try:
        return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    try:
        return datetime.strptime(time_str, "%Y-%m-%d")
    except ValueError:
        return None
