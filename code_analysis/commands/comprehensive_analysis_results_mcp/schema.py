"""
JSON schema for get_comprehensive_analysis_results command parameters.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict


RESULT_KEYS = [
    "placeholders",
    "stubs",
    "empty_methods",
    "imports_not_at_top",
    "long_files",
    "duplicates",
    "flake8_errors",
    "mypy_errors",
    "black_findings",
    "isort_findings",
    "bandit_findings",
    "missing_docstrings",
]


def get_schema(cls: Any) -> Dict[str, Any]:
    """Build JSON schema for saved comprehensive analysis result lookup."""
    base_props = cls._get_base_schema_properties()
    return {
        "type": "object",
        "description": (
            "Read saved rows from comprehensive_analysis_results without running a new "
            "analysis. Use result_key='missing_docstrings' to retrieve the docstring "
            "findings from the last comprehensive_analysis run."
        ),
        "properties": {
            **base_props,
            "file_id": {
                "type": "string",
                "description": (
                    "Optional files.id UUID. When provided, returns the latest saved "
                    "analysis for that file only."
                ),
            },
            "file_path": {
                "type": "string",
                "description": (
                    "Optional project-relative or absolute path. Resolved to files.id "
                    "inside project_id; mutually usable instead of file_id."
                ),
            },
            "result_key": {
                "type": "string",
                "description": (
                    "Optional key inside results_json to return. Omit to return the "
                    "whole results_json object for each file."
                ),
                "enum": RESULT_KEYS,
            },
            "include_summary": {
                "type": "boolean",
                "description": "Include per-file summary_json in each returned item.",
                "default": True,
            },
            "include_empty": {
                "type": "boolean",
                "description": (
                    "When result_key is set, include files whose selected result list "
                    "is empty. Default false."
                ),
                "default": False,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of file result items to return.",
                "default": 100,
                "minimum": 1,
                "maximum": 1000,
            },
            "offset": {
                "type": "integer",
                "description": "Number of matching file result items to skip.",
                "default": 0,
                "minimum": 0,
            },
        },
        "required": ["project_id"],
        "additionalProperties": False,
    }
