"""
Metadata for get_comprehensive_analysis_results MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type


def get_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return metadata aligned with METADATA_SCHEMA_STANDARD."""
    from code_analysis.commands.command_metadata_helpers import (
        build_command_metadata,
        parameters_from_schema,
    )

    return build_command_metadata(
        cls,
        detailed_description=(
            "Reads persisted comprehensive_analysis output from the database table "
            "comprehensive_analysis_results. The command does not analyze files and "
            "does not recalculate findings; it loads the latest saved results_json "
            "and summary_json for indexed files in the requested project. Use file_id "
            "or file_path to inspect one file. Use result_key to fetch one result "
            "family, especially result_key='missing_docstrings' for the docstring "
            "report produced by comprehensive_analysis."
        ),
        parameters=parameters_from_schema(cls.get_schema()),
        usage_examples=[
            {
                "description": "List files with missing docstrings from saved analysis",
                "command": {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "result_key": "missing_docstrings",
                    "limit": 100,
                    "offset": 0,
                },
                "explanation": (
                    "Returns only files whose saved missing_docstrings list is non-empty."
                ),
            },
            {
                "description": "Read the latest saved result for one file",
                "command": {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "file_path": "code_analysis/commands/example.py",
                },
                "explanation": "Returns full saved results_json and summary_json.",
            },
        ],
        error_cases={
            "PROJECT_NOT_FOUND": {
                "description": "project_id is not registered.",
                "solution": "Call list_projects and use a valid project UUID.",
            },
            "FILE_NOT_FOUND": {
                "description": "file_path or file_id does not resolve inside project_id.",
                "solution": "Call list_project_files and use a returned file_id or relative_path.",
            },
            "COMPREHENSIVE_ANALYSIS_RESULTS_ERROR": {
                "description": "Database read or result parsing failed.",
                "solution": "Check server logs and verify comprehensive_analysis has completed.",
            },
        },
        return_value={
            "success": {
                "description": "Saved comprehensive analysis results were read.",
                "data": {
                    "items": "Paginated list of file result rows.",
                    "summary": "Aggregate counts for scanned and returned saved rows.",
                    "pagination": "limit, offset, total_matches, and has_more.",
                    "result_key": "Selected result key, or null when full results are returned.",
                },
                "example": {
                    "result_key": "missing_docstrings",
                    "items": [
                        {
                            "file_id": "9c4cf5c0-3dd2-4b04-b14f-000000000000",
                            "path": "/project/pkg/mod.py",
                            "relative_path": "pkg/mod.py",
                            "results": [
                                {
                                    "type": "function",
                                    "name": "load_data",
                                    "line": 12,
                                }
                            ],
                        }
                    ],
                    "summary": {
                        "files_scanned": 100,
                        "files_with_saved_results": 90,
                        "files_returned": 1,
                        "total_findings": 1,
                    },
                },
            },
            "error": {
                "description": "Command failed.",
                "code": "Stable error code.",
                "message": "Human-readable error message.",
            },
        },
        best_practices=[
            "Run comprehensive_analysis first; this command only reads saved results.",
            "Use result_key to keep response size manageable.",
            "Page project-wide requests with limit and offset.",
            "Use list_project_files to resolve file_id for one-file lookups.",
        ],
    )
