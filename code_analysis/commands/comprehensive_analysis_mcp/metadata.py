"""
Command metadata for comprehensive_analysis MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Type


def get_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return full metadata dict for ComprehensiveAnalysisMCPCommand using cls attributes."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "The comprehensive_analysis command performs comprehensive code quality analysis "
            "combining multiple analysis types in a single operation. This is a long-running "
            "command executed via queue and provides detailed code quality metrics.\n\n"
            "Operation flow:\n"
            "1. Validates root_dir exists and is a directory\n"
            "2. Opens database connection\n"
            "3. Resolves project_id:\n"
            "   - If project_id parameter provided, validates it exists\n"
            "   - If not provided, tries to infer from root_dir\n"
            "   - If cannot infer, project_id remains None (analyze all projects)\n"
            "4. Sets up dedicated log file (logs/comprehensive_analysis.log)\n"
            "5. Initializes ComprehensiveAnalyzer and DuplicateDetector\n"
            "6. If file_path provided:\n"
            "   - Analyzes single file with all enabled checks\n"
            "7. If file_path not provided:\n"
            "   - If project_id is set: Analyzes all files in that project\n"
            "   - If project_id is None: Analyzes ALL files in ALL projects\n"
            "   - Processes files with progress tracking\n"
            "   - Runs all enabled checks for each file\n"
            "8. Aggregates results and creates summary statistics\n"
            "9. Saves results to database (comprehensive_analysis_results table)\n"
            "10. Returns comprehensive analysis results\n\n"
            "Incremental Analysis (mtime gate):\n"
            "- Analyzes only if file on disk is newer than latest DB analysis (or no prior record).\n"
            "- Skips when disk mtime is equal to DB mtime within tolerance (0.1s).\n"
            "- Skips when disk mtime is older than DB mtime (no re-analysis of older files).\n"
            "- Single file mode: returns cached results when file is skipped.\n\n"
            "Analysis Types:\n"
            "- Placeholders: Finds TODO, FIXME, XXX, HACK, NOTE comments\n"
            "- Stubs: Finds functions/methods with pass, ellipsis, NotImplementedError\n"
            "- Empty methods: Finds methods without body (excluding abstract methods)\n"
            "- Imports not at top: Finds imports after non-import statements\n"
            "- Long files: Finds files exceeding max_lines threshold\n"
            "- Duplicates: Finds code duplicates (structural and semantic)\n"
            "- Flake8: Runs flake8 linter and reports errors\n"
            "- Mypy: Runs mypy type checker and reports errors\n"
            "- Missing docstrings: Finds files/classes/methods/functions without docstrings\n\n"
            "Use cases:\n"
            "- Complete code quality audit\n"
            "- Identify code quality issues before refactoring\n"
            "- Monitor code quality metrics\n"
            "- Find technical debt indicators\n"
            "- Generate code quality reports\n\n"
            "Important notes:\n"
            "- This is a long-running command (use_queue=True)\n"
            "- When file_path not provided:\n"
            "  * If project_id is set: analyzes all files in that project\n"
            "  * If project_id is None: analyzes ALL files in ALL projects\n"
            "- Progress is tracked and logged to logs/comprehensive_analysis.log\n"
            "- Each check can be enabled/disabled via boolean parameters\n"
            "- Results include summary statistics for all analysis types\n"
            "- Results are saved to database (comprehensive_analysis_results table)\n"
            "- Incremental analysis: only analyzes files whose disk mtime is newer than latest DB (with tolerance)\n"
            "- Older-than-DB files are skipped; equal-within-tolerance files are skipped\n"
            "- Single file mode: returns cached results when file is skipped"
        ),
        "parameters": {
            "root_dir": {
                "description": (
                    "Project root directory path. Can be absolute or relative. "
                    "Must contain data/code_analysis.db file."
                ),
                "type": "string",
                "required": True,
            },
            "file_path": {
                "description": (
                    "Optional path to specific file to analyze. If provided, only analyzes this file. "
                    "If omitted, analyzes files based on project_id parameter (see project_id description)."
                ),
                "type": "string",
                "required": False,
            },
            "max_lines": {
                "description": (
                    "Maximum lines threshold for long files check. Default is 400. "
                    "Files exceeding this threshold are reported as long files."
                ),
                "type": "integer",
                "required": False,
                "default": 400,
            },
            "check_placeholders": {
                "description": (
                    "Check for placeholders (TODO, FIXME, XXX, HACK, NOTE). Default is True."
                ),
                "type": "boolean",
                "required": False,
                "default": True,
            },
            "check_stubs": {
                "description": (
                    "Check for stub functions/methods (pass, ellipsis, NotImplementedError). "
                    "Default is True."
                ),
                "type": "boolean",
                "required": False,
                "default": True,
            },
            "check_empty_methods": {
                "description": (
                    "Check for empty methods (excluding abstract methods). Default is True."
                ),
                "type": "boolean",
                "required": False,
                "default": True,
            },
            "check_imports": {
                "description": (
                    "Check for imports not at top of file. Default is True."
                ),
                "type": "boolean",
                "required": False,
                "default": True,
            },
            "check_long_files": {
                "description": (
                    "Check for long files (exceeding max_lines). Default is True."
                ),
                "type": "boolean",
                "required": False,
                "default": True,
            },
            "check_duplicates": {
                "description": ("Check for code duplicates. Default is True."),
                "type": "boolean",
                "required": False,
                "default": True,
            },
            "check_flake8": {
                "description": ("Check code with flake8 linter. Default is True."),
                "type": "boolean",
                "required": False,
                "default": True,
            },
            "check_mypy": {
                "description": ("Check code with mypy type checker. Default is True."),
                "type": "boolean",
                "required": False,
                "default": True,
            },
            "check_docstrings": {
                "description": (
                    "Check for missing docstrings (files, classes, methods, functions). "
                    "Default is True."
                ),
                "type": "boolean",
                "required": False,
                "default": True,
            },
            "duplicate_min_lines": {
                "description": ("Minimum lines for duplicate detection. Default is 5."),
                "type": "integer",
                "required": False,
                "default": 5,
            },
            "duplicate_min_similarity": {
                "description": (
                    "Minimum similarity for duplicates (0.0-1.0). Default is 0.8."
                ),
                "type": "number",
                "required": False,
                "default": 0.8,
            },
            "mypy_config_file": {
                "description": (
                    "Optional path to mypy config file. If provided, uses this config for mypy checks."
                ),
                "type": "string",
                "required": False,
            },
            "project_id": {
                "description": (
                    "Optional project UUID. "
                    "If provided: analyzes all files in that project (when file_path not provided). "
                    "If omitted: tries to infer from root_dir. "
                    "If cannot infer: analyzes all files in all projects (when file_path not provided)."
                ),
                "type": "string",
                "required": False,
            },
            "limit": {
                "description": (
                    "Max number of files to analyze per run (e.g. 10–15). "
                    "Omit for all files. Use with offset for paging."
                ),
                "type": "integer",
                "required": False,
            },
            "offset": {
                "description": "Number of files to skip (for paging with limit). Default 0.",
                "type": "integer",
                "required": False,
                "default": 0,
            },
        },
        "usage_examples": [
            {
                "description": "Run full comprehensive analysis on all files in all projects",
                "command": {
                    "root_dir": "/home/user/projects/my_project",
                    # project_id not provided - analyzes all projects
                },
                "explanation": (
                    "Runs all checks on all files in all projects. This is a long-running operation. "
                    "Use queue_get_job_status to check progress."
                ),
            },
            {
                "description": "Analyze all files in specific project",
                "command": {
                    "root_dir": "/home/user/projects/my_project",
                    "project_id": "123e4567-e89b-12d3-a456-426614174000",
                },
                "explanation": (
                    "Runs all checks on all files in the specified project only. "
                    "Faster than analyzing all projects."
                ),
            },
            {
                "description": "Analyze specific file with all checks",
                "command": {
                    "root_dir": "/home/user/projects/my_project",
                    "file_path": "src/main.py",
                },
                "explanation": (
                    "Runs all checks on src/main.py file only. Faster than project-wide analysis."
                ),
            },
            {
                "description": "Analyze in batches of 15 files (paging)",
                "command": {
                    "root_dir": "/home/user/projects/my_project",
                    "project_id": "123e4567-e89b-12d3-a456-426614174000",
                    "limit": 15,
                    "offset": 0,
                },
                "explanation": (
                    "Runs analysis on first 15 files. Next run use offset=15, then offset=30, etc."
                ),
            },
            {
                "description": "Run only specific checks",
                "command": {
                    "root_dir": "/home/user/projects/my_project",
                    "check_placeholders": True,
                    "check_stubs": True,
                    "check_duplicates": False,
                    "check_flake8": False,
                    "check_mypy": False,
                },
                "explanation": (
                    "Runs only placeholder and stub checks, skipping duplicates and linting."
                ),
            },
            {
                "description": "Check with custom duplicate settings",
                "command": {
                    "root_dir": "/home/user/projects/my_project",
                    "duplicate_min_lines": 10,
                    "duplicate_min_similarity": 0.9,
                },
                "explanation": (
                    "Finds duplicates with minimum 10 lines and 90% similarity."
                ),
            },
        ],
        "error_cases": {
            "PROJECT_NOT_FOUND": {
                "description": "Project not found in database",
                "example": "root_dir='/path' but project not registered",
                "solution": "Ensure project is registered. Run update_indexes first.",
            },
            "FILE_NOT_FOUND": {
                "description": "File not found",
                "example": "file_path='src/main.py' but file doesn't exist",
                "solution": "Verify file path is correct and file exists.",
            },
            "COMPREHENSIVE_ANALYSIS_ERROR": {
                "description": "General error during comprehensive analysis",
                "example": "Database error, analysis failure, or tool execution error",
                "solution": (
                    "Check database integrity, verify file paths, ensure analysis tools "
                    "(flake8, mypy) are installed. Check logs/comprehensive_analysis.log for details."
                ),
            },
        },
        "return_value": {
            "success": {
                "description": "Command executed successfully",
                "data": {
                    "placeholders": "List of placeholder comments (TODO, FIXME, etc.)",
                    "stubs": "List of stub functions/methods",
                    "empty_methods": "List of empty methods",
                    "imports_not_at_top": "List of imports not at top of file",
                    "long_files": "List of files exceeding max_lines",
                    "duplicates": "List of duplicate code groups",
                    "flake8_errors": "List of flake8 linting errors",
                    "mypy_errors": "List of mypy type checking errors",
                    "missing_docstrings": "List of missing docstrings (files, classes, methods, functions)",
                    "summary": (
                        "Summary statistics dictionary with:\n"
                        "- total_placeholders, total_stubs, total_empty_methods\n"
                        "- total_imports_not_at_top, total_long_files\n"
                        "- total_duplicate_groups, total_duplicate_occurrences\n"
                        "- total_flake8_errors, files_with_flake8_errors\n"
                        "- total_mypy_errors, files_with_mypy_errors\n"
                        "- total_missing_docstrings, files_without_docstrings\n"
                        "- classes_without_docstrings, methods_without_docstrings\n"
                        "- functions_without_docstrings"
                    ),
                },
                "example": {
                    "placeholders": [
                        {
                            "file_path": "src/main.py",
                            "line": 42,
                            "type": "TODO",
                            "text": "TODO: refactor",
                        },
                    ],
                    "stubs": [
                        {
                            "file_path": "src/utils.py",
                            "line": 10,
                            "name": "stub_function",
                            "type": "function",
                        },
                    ],
                    "summary": {
                        "total_placeholders": 1,
                        "total_stubs": 1,
                        "total_empty_methods": 0,
                        "total_long_files": 0,
                        "total_duplicate_groups": 0,
                        "total_flake8_errors": 0,
                        "total_mypy_errors": 0,
                    },
                },
            },
            "error": {
                "description": "Command failed",
                "code": "Error code (e.g., PROJECT_NOT_FOUND, FILE_NOT_FOUND, COMPREHENSIVE_ANALYSIS_ERROR)",
                "message": "Human-readable error message",
            },
        },
        "best_practices": [
            "Use file_path parameter for faster analysis of specific files",
            "Use project_id parameter to analyze specific project instead of all projects",
            "Disable checks you don't need to improve performance",
            "Use queue_get_job_status to monitor progress for project-wide analysis",
            "Check logs/comprehensive_analysis.log for detailed analysis logs",
            "Review summary statistics first, then drill down into specific issues",
            "Run this command regularly to track code quality over time",
            "Use custom duplicate settings to focus on significant duplicates",
            "Results are automatically saved to database - incremental analysis improves performance",
            "Only changed files are analyzed - unchanged files are skipped automatically",
        ],
        "data_persistence": {
            "results_saved_to_database": True,
            "description": (
                "Results of comprehensive_analysis are saved to the database in the "
                "comprehensive_analysis_results table. Each file's analysis results are stored "
                "with the file's modification time (mtime) to enable incremental analysis."
            ),
            "what_is_saved": (
                "For each analyzed file:\n"
                "- File ID and project ID\n"
                "- File modification time (mtime) at analysis\n"
                "- Complete analysis results (JSON)\n"
                "- Summary statistics (JSON)\n"
                "- Timestamp of analysis\n"
                "Results are stored in comprehensive_analysis_results table with UNIQUE(file_id, file_mtime) constraint."
            ),
            "incremental_analysis": (
                "Mtime gate: analyze only if file is newer than latest DB analysis (or no record).\n"
                "1. Gets file mtime from disk; fetches latest analysis mtime from DB for file_id.\n"
                "2. No DB record -> analyze.\n"
                "3. disk_mtime > db_mtime + tolerance (0.1s) -> analyze.\n"
                "4. abs(disk_mtime - db_mtime) <= tolerance -> skip (use cached).\n"
                "5. disk_mtime older than db_mtime (beyond tolerance) -> skip (older-than-DB files not re-analyzed)."
            ),
            "what_is_returned": (
                "Complete analysis results including:\n"
                "- All findings (placeholders, stubs, empty methods, etc.)\n"
                "- Summary statistics\n"
                "- All errors and warnings\n"
                "All data is returned in the SuccessResult.data dictionary.\n"
                "For single file mode with unchanged file: returns cached results from database."
            ),
        },
    }
