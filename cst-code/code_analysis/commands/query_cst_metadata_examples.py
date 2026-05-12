"""
query_cst metadata: usage_examples (aggregates find + selector modules).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List

from .query_cst_metadata_examples_find import get_find_examples
from .query_cst_metadata_examples_selector import get_selector_examples


def get_usage_examples() -> List[Dict[str, Any]]:
    """Return the usage_examples list for query_cst metadata."""
    return get_find_examples() + get_selector_examples()
