"""
Metadata for query_cst command (detailed description, examples, error cases).

Assembles full metadata from submodules to keep each file under size limit.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from .query_cst_metadata_descr_params import (
    get_detailed_description,
    get_parameters,
)
from .query_cst_metadata_errors_return import (
    get_best_practices,
    get_error_cases,
    get_return_value,
)
from .query_cst_metadata_examples import get_usage_examples


def get_query_cst_metadata(cls: Any) -> Dict[str, Any]:
    """Return full metadata dict for query_cst command."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": get_detailed_description(),
        "parameters": get_parameters(),
        "usage_examples": get_usage_examples(),
        "error_cases": get_error_cases(),
        "return_value": get_return_value(),
        "best_practices": get_best_practices(),
    }
