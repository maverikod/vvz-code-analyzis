# Comprehensive Analysis Command - Detailed Analysis

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Overview

The `comprehensive_analysis` command is a powerful code quality analysis tool that combines multiple analysis types in a single operation. It performs comprehensive code quality checks including placeholders, stubs, empty methods, imports, long files, duplicates, linting, type checking, and missing docstrings.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Command Structure](#command-structure)
3. [Analysis Types](#analysis-types)
4. [Execution Flow](#execution-flow)
5. [Components Deep Dive](#components-deep-dive)
6. [Queue Integration](#queue-integration)
7. [Progress Tracking](#progress-tracking)
8. [Logging](#logging)
9. [Error Handling](#error-handling)
10. [Performance Considerations](#performance-considerations)
11. [Usage Examples](#usage-examples)

## Architecture Overview

### Components

```
comprehensive_analysis
├── ComprehensiveAnalysisMCPCommand (MCP wrapper)
│   ├── BaseMCPCommand (base functionality)
│   ├── ComprehensiveAnalyzer (core analysis logic)
│   ├── DuplicateDetector (duplicate detection)
│   └── ProgressTracker (progress reporting)
└── Queue System (async execution)
```

### Key Files

- **Command**: `code_analysis/commands/comprehensive_analysis_mcp.py`
- **Core Analyzer**: `code_analysis/core/comprehensive_analyzer.py`
- **Duplicate Detector**: `code_analysis/core/duplicate_detector.py`
- **Base Command**: `code_analysis/commands/base_mcp_command.py`
- **Progress Tracker**: `code_analysis/core/progress_tracker.py`

## Command Structure

### Class Definition

```python
class ComprehensiveAnalysisMCPCommand(BaseMCPCommand):
    name = "comprehensive_analysis"
    version = "1.0.0"
    descr = "Comprehensive code analysis..."
    category = "analysis"
    use_queue = True  # Long-running command
```

### Key Properties

- **`use_queue = True`**: Command is executed asynchronously via queue
- **Inherits from `BaseMCPCommand`**: Provides database access, project resolution, error handling
- **Uses `ComprehensiveAnalyzer`**: Core analysis logic
- **Uses `DuplicateDetector`**: For finding code duplicates

## Analysis Types

The command performs 9 different types of analysis:

### 1. Placeholders (`check_placeholders`)

**Purpose**: Find TODO, FIXME, XXX, HACK, NOTE, BUG, OPTIMIZE, PLACEHOLDER, STUB, NOT IMPLEMENTED comments.

**Implementation**:
- Uses regex pattern matching (case-insensitive)
- Searches in:
  - Comments (via tokenizer)
  - Docstrings (via AST)
  - String literals (via AST)
- Returns: List of placeholder occurrences with line numbers, types, and context

**Example Result**:
```json
{
  "line": 42,
  "type": "comment",
  "pattern": "TODO",
  "text": "# TODO: refactor this",
  "context": "def old_function():"
}
```

### 2. Stubs (`check_stubs`)

**Purpose**: Find functions/methods with stub implementations (pass, ellipsis, NotImplementedError, return None).

**Implementation**:
- Parses AST to find function/method definitions
- Checks body for:
  - `pass` only
  - `...` (ellipsis) only
  - `raise NotImplementedError` only
  - `return None` only (if not abstract)
- Returns: List of stub functions with type and code snippet

**Example Result**:
```json
{
  "function_name": "stub_function",
  "class_name": "MyClass",
  "line": 10,
  "type": "method",
  "stub_type": "pass",
  "code_snippet": "def stub_function(self):\n    pass"
}
```

### 3. Empty Methods (`check_empty_methods`)

**Purpose**: Find methods without body (excluding abstract methods).

**Implementation**:
- Parses AST to find class methods
- Checks if method body is:
  - Empty
  - Only `pass`
  - Only `...` (ellipsis)
  - Only docstring
- Excludes abstract methods (decorated with `@abstractmethod` or in ABC class)
- Returns: List of empty methods with body type

**Example Result**:
```json
{
  "method_name": "empty_method",
  "class_name": "MyClass",
  "line": 15,
  "body_type": "pass",
  "code_snippet": "def empty_method(self):\n    pass",
  "is_abstract": false
}
```

### 4. Imports Not at Top (`check_imports`)

**Purpose**: Find imports that are not at the top of the file.

**Implementation**:
- Parses AST to find first non-import, non-docstring statement
- Checks all imports at module level
- Reports imports that come after first non-import statement
- Returns: List of imports with line numbers and import details

**Example Result**:
```json
{
  "line": 50,
  "import_name": "os",
  "module": null,
  "import_type": "import",
  "code_snippet": "import os"
}
```

### 5. Long Files (`check_long_files`)

**Purpose**: Find files exceeding line limit (default: 400 lines).

**Implementation**:
- Uses file records from database (with line counts)
- Filters files where `lines > max_lines`
- Returns: List of long files sorted by line count (descending)

**Example Result**:
```json
{
  "path": "code_analysis/core/large_file.py",
  "lines": 523,
  "exceeds_by": 123
}
```

### 6. Duplicates (`check_duplicates`)

**Purpose**: Find duplicate code blocks using AST normalization.

**Implementation**:
- Uses `DuplicateDetector` class
- Normalizes AST (variable names, literals)
- Finds functions/methods with same normalized structure
- Groups duplicates by hash
- Returns: List of duplicate groups with occurrences

**Example Result**:
```json
{
  "hash": "function:abc123...",
  "similarity": 1.0,
  "occurrences": [
    {
      "function_name": "func1",
      "class_name": null,
      "type": "function",
      "start_line": 10,
      "end_line": 25,
      "code_snippet": "..."
    },
    {
      "function_name": "func2",
      "class_name": null,
      "type": "function",
      "start_line": 30,
      "end_line": 45,
      "code_snippet": "..."
    }
  ]
}
```

### 7. Flake8 Linting (`check_flake8`)

**Purpose**: Check code with flake8 linter.

**Implementation**:
- Calls `lint_with_flake8()` from `code_quality` module
- Executes flake8 as subprocess
- Parses output for errors
- Returns: Dictionary with success status, errors, and error count

**Example Result**:
```json
{
  "success": false,
  "error_message": "",
  "errors": [
    {
      "line": 42,
      "column": 10,
      "code": "E501",
      "message": "line too long (120 > 79 characters)"
    }
  ],
  "error_count": 1
}
```

### 8. Mypy Type Checking (`check_mypy`)

**Purpose**: Check code with mypy type checker.

**Implementation**:
- Calls `type_check_with_mypy()` from `code_quality` module
- Executes mypy as subprocess
- Supports custom mypy config file
- Parses output for errors
- Returns: Dictionary with success status, errors, and error count

**Example Result**:
```json
{
  "success": false,
  "error_message": "",
  "errors": [
    {
      "line": 15,
      "column": 5,
      "message": "Incompatible return type"
    }
  ],
  "error_count": 1
}
```

### 9. Missing Docstrings (`check_docstrings`)

**Purpose**: Find files, classes, methods, and functions without docstrings.

**Implementation**:
- Parses AST to check docstrings
- Checks:
  - File-level docstring (module docstring)
  - Class docstrings
  - Method docstrings (excluding property getters/setters)
  - Function docstrings (top-level)
- Returns: List of missing docstrings with type and context

**Example Result**:
```json
{
  "type": "method",
  "name": "MyClass.method",
  "class_name": "MyClass",
  "line": 20,
  "context": "Method 'MyClass.method' is missing docstring"
}
```

## Execution Flow

### High-Level Flow

```
1. Command Registration
   └── Registered in hooks.py as MCP command

2. Client Request
   └── MCP client calls comprehensive_analysis

3. Queue Check
   └── use_queue=True → Execute via queue

4. Job Creation
   └── CommandExecutionJob created

5. Command Execution
   ├── Validate root_dir
   ├── Open database
   ├── Resolve project_id
   ├── Setup logging
   ├── Initialize analyzers
   └── Execute analysis
       ├── Single file mode (if file_path provided)
       └── All files mode (if file_path not provided)
           ├── Get all files from database
           ├── Process each file
           │   ├── Run enabled checks
           │   └── Update progress
           └── Aggregate results

6. Create Summary
   └── Calculate statistics

7. Return Results
   └── SuccessResult with all findings
```

### Detailed Execution Steps

#### Step 1: Initialization

```python
# 1.1 Validate root directory
root_path = self._validate_root_dir(root_dir)

# 1.2 Open database
db = self._open_database(root_dir)

# 1.3 Resolve project ID
proj_id = self._get_project_id(db, root_path, project_id)

# 1.4 Setup logging
analysis_logger = logging.getLogger("comprehensive_analysis")
# Creates logs/comprehensive_analysis.log

# 1.5 Initialize analyzers
analyzer = ComprehensiveAnalyzer(max_lines=max_lines)
detector = DuplicateDetector(
    min_lines=duplicate_min_lines,
    min_similarity=duplicate_min_similarity
)
```

#### Step 2: Mode Selection

**Single File Mode** (if `file_path` provided):
- Validates file exists
- Reads source code
- Runs all enabled checks on single file
- Returns results immediately

**Project Files Mode** (if `file_path` not provided and `project_id` is set):
- Gets all files from specific project: `db.get_project_files(project_id)`
- Processes each file sequentially
- Runs all enabled checks for each file
- Aggregates results
- Updates progress after each file

**All Projects Mode** (if `file_path` not provided and `project_id` is None):
- Gets all files from all projects: `SELECT id, path, lines FROM files WHERE deleted = 0`
- Processes each file sequentially
- Runs all enabled checks for each file
- Aggregates results
- Updates progress after each file

#### Step 3: Check Execution

For each file (or single file):

```python
# Placeholders
if check_placeholders:
    placeholders = analyzer.find_placeholders(file_path, source_code)
    results["placeholders"].extend(placeholders)

# Stubs
if check_stubs:
    stubs = analyzer.find_stubs(file_path, source_code)
    results["stubs"].extend(stubs)

# Empty methods
if check_empty_methods:
    empty_methods = analyzer.find_empty_methods(file_path, source_code)
    results["empty_methods"].extend(empty_methods)

# Imports
if check_imports:
    imports_not_at_top = analyzer.find_imports_not_at_top(file_path, source_code)
    results["imports_not_at_top"].extend(imports_not_at_top)

# Duplicates
if check_duplicates:
    duplicates = detector.find_duplicates_in_file(str(file_path))
    results["duplicates"].extend(duplicates)

# Flake8
if check_flake8:
    flake8_result = analyzer.check_flake8(file_path)
    if not flake8_result["success"]:
        results["flake8_errors"].append(flake8_result)

# Mypy
if check_mypy:
    mypy_result = analyzer.check_mypy(file_path, mypy_config)
    if not mypy_result["success"]:
        results["mypy_errors"].append(mypy_result)

# Docstrings
if check_docstrings:
    missing_docstrings = analyzer.find_missing_docstrings(file_path, source_code)
    results["missing_docstrings"].extend(missing_docstrings)
```

#### Step 4: Long Files Check (All Files Mode Only)

```python
if check_long_files:
    results["long_files"] = analyzer.find_long_files(file_records)
```

#### Step 5: Summary Creation

```python
results["summary"] = {
    "total_placeholders": len(results["placeholders"]),
    "total_stubs": len(results["stubs"]),
    "total_empty_methods": len(results["empty_methods"]),
    "total_imports_not_at_top": len(results["imports_not_at_top"]),
    "total_long_files": len(results["long_files"]),
    "total_duplicate_groups": len(results["duplicates"]),
    "total_duplicate_occurrences": sum(len(g["occurrences"]) for g in results["duplicates"]),
    "total_flake8_errors": sum(e.get("error_count", 0) for e in results["flake8_errors"]),
    "files_with_flake8_errors": len(results["flake8_errors"]),
    "total_mypy_errors": sum(e.get("error_count", 0) for e in results["mypy_errors"]),
    "files_with_mypy_errors": len(results["mypy_errors"]),
    "total_missing_docstrings": len(results["missing_docstrings"]),
    "files_without_docstrings": len(set(d["file_path"] for d in results["missing_docstrings"] if d["type"] == "file")),
    "classes_without_docstrings": len([d for d in results["missing_docstrings"] if d["type"] == "class"]),
    "methods_without_docstrings": len([d for d in results["missing_docstrings"] if d["type"] == "method"]),
    "functions_without_docstrings": len([d for d in results["missing_docstrings"] if d["type"] == "function"]),
}
```

## Components Deep Dive

### ComprehensiveAnalyzer

**Location**: `code_analysis/core/comprehensive_analyzer.py`

**Purpose**: Core analysis logic for all checks except duplicates.

**Key Methods**:

1. **`find_placeholders()`**:
   - Uses tokenizer for comments
   - Uses AST for docstrings and string literals
   - Regex pattern matching (case-insensitive)

2. **`find_stubs()`**:
   - AST parsing for function/method definitions
   - Body analysis for stub patterns
   - Distinguishes between functions and methods

3. **`find_empty_methods()`**:
   - AST parsing for class methods
   - Body analysis for empty patterns
   - Abstract method detection

4. **`find_imports_not_at_top()`**:
   - AST parsing for module-level imports
   - Finds first non-import statement
   - Reports imports after first non-import

5. **`find_long_files()`**:
   - Simple line count comparison
   - Uses file records from database

6. **`check_flake8()`**:
   - Delegates to `code_quality.lint_with_flake8()`
   - Subprocess execution
   - Error parsing

7. **`check_mypy()`**:
   - Delegates to `code_quality.type_check_with_mypy()`
   - Subprocess execution with config support
   - Error parsing

8. **`find_missing_docstrings()`**:
   - AST parsing for docstrings
   - Checks file, class, method, function levels
   - Excludes property getters/setters

### DuplicateDetector

**Location**: `code_analysis/core/duplicate_detector.py`

**Purpose**: Find duplicate code blocks using AST normalization.

**Key Features**:

1. **AST Normalization**:
   - Normalizes variable names → `_VAR1_`, `_VAR2_`, etc.
   - Normalizes string literals → `_STR_`
   - Normalizes numeric literals → `_NUM_`
   - Preserves structure (if/for/while/call)

2. **Hash-Based Detection**:
   - Converts normalized AST to hash
   - Groups functions/methods by hash
   - Finds exact structural duplicates

3. **Semantic Similarity** (optional, not used in comprehensive_analysis):
   - Uses embeddings for semantic similarity
   - Requires SVO client manager
   - Not enabled by default in comprehensive_analysis

**Key Methods**:

1. **`normalize_ast()`**: Normalizes AST using `ASTNormalizer`
2. **`ast_to_hash()`**: Converts normalized AST to SHA256 hash
3. **`find_duplicates_in_file()`**: Main entry point for file analysis
4. **`find_duplicates_in_ast()`**: Core duplicate detection logic

### BaseMCPCommand

**Location**: `code_analysis/commands/base_mcp_command.py`

**Purpose**: Base class providing common functionality.

**Key Features**:

1. **Database Management**:
   - Opens/closes database connections
   - Handles database integrity checks
   - Project ID resolution

2. **Validation**:
   - Root directory validation
   - File path validation
   - Project ID validation

3. **Error Handling**:
   - Standardized error responses
   - Error code mapping
   - Exception handling

## Queue Integration

### Queue Execution

The command uses `use_queue = True`, which means:

1. **Command is queued**: Not executed immediately
2. **Job created**: `CommandExecutionJob` is created
3. **Async execution**: Runs in background thread/process
4. **Status tracking**: Job status can be queried
5. **Progress updates**: Progress can be tracked via `ProgressTracker`

### Queue Job Lifecycle

```
PENDING → RUNNING → COMPLETED
              ↓
           FAILED
```

### Getting Job Status

```python
# Execute command (returns job_id)
result = await call_server(
    server_id="code-analysis-server",
    command="comprehensive_analysis",
    params={...},
    use_queue=True
)

# Get job status
status = await call_server(
    server_id="code-analysis-server",
    command="queue_get_job_status",
    params={"job_id": result["job_id"]}
)
```

## Progress Tracking

### Progress Tracker Integration

The command uses `ProgressTracker` to report progress:

```python
from ..core.progress_tracker import get_progress_tracker_from_context

progress_tracker = get_progress_tracker_from_context(
    kwargs.get("context") or {}
)
```

### Progress Updates

**During execution**:

```python
# Initialize
progress_tracker.set_status("running")
progress_tracker.set_description("Initializing comprehensive analysis...")
progress_tracker.set_progress(0)

# During file processing (all files mode)
for idx, file_record in enumerate(files):
    # ... process file ...
    
    # Update progress
    percent = int(((idx + 1) / files_total) * 100)
    progress_tracker.set_progress(percent)
    progress_tracker.set_description(
        f"Analyzing: {idx + 1}/{files_total} ({percent}%)"
    )

# Complete
progress_tracker.set_status("completed")
progress_tracker.set_description("Analysis completed")
progress_tracker.set_progress(100)
```

**Note**: Progress tracking only works in "all files" mode. Single file mode completes too quickly for progress updates.

## Logging

### Dedicated Log File

The command creates a dedicated log file:

**Location**: `logs/comprehensive_analysis.log`

**Configuration**:
- Rotating file handler (10 MB max, 5 backups)
- UTF-8 encoding
- INFO level
- Custom formatter with timestamp

**Setup**:
```python
analysis_logger = logging.getLogger("comprehensive_analysis")
analysis_logger.setLevel(logging.INFO)

log_file = logs_dir / "comprehensive_analysis.log"
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,
    encoding="utf-8",
)
```

### Logged Events

1. **Start**: "Starting analysis of single file: ..." or "Starting comprehensive analysis: N files to analyze"
2. **File processing**: "Analyzing file X/Y: file_path"
3. **Completion**: "Comprehensive analysis completed. Summary: {...}"
4. **Errors**: "Comprehensive analysis failed: ..." (with traceback)

### Cleanup

Log handlers are cleaned up after execution:

```python
# Clean up handler
for handler in analysis_logger.handlers[:]:
    handler.close()
    analysis_logger.removeHandler(handler)
```

## Error Handling

### Error Types

1. **PROJECT_NOT_FOUND**: Project not found in database
2. **FILE_NOT_FOUND**: File not found (single file mode)
3. **COMPREHENSIVE_ANALYSIS_ERROR**: General analysis error

### Error Handling Flow

```python
try:
    # ... analysis logic ...
except Exception as e:
    # Log error to analysis log
    analysis_logger.error(f"Comprehensive analysis failed: {e}", exc_info=True)
    
    # Clean up handler
    for handler in analysis_logger.handlers[:]:
        handler.close()
        analysis_logger.removeHandler(handler)
    
    # Return error result
    return self._handle_error(
        e, "COMPREHENSIVE_ANALYSIS_ERROR", "comprehensive_analysis"
    )
```

### Graceful Degradation

- Syntax errors in files are caught and skipped (files with syntax errors are logged but don't stop analysis)
- Individual check failures don't stop entire analysis
- Database errors are caught and reported

## Performance Considerations

### Performance Characteristics

1. **Single File Mode**: Fast (milliseconds to seconds)
2. **Project Files Mode**: Moderate (seconds to minutes, depending on project size)
3. **All Projects Mode**: Slow (minutes to hours, depending on total files across all projects)

### Bottlenecks

1. **AST Parsing**: Each file is parsed multiple times (once per check)
2. **Flake8/Mypy**: Subprocess execution for each file (slow)
3. **Duplicate Detection**: AST normalization and hashing (moderate)
4. **Database Queries**: Single query for all files (fast)

### Optimization Opportunities

1. **AST Caching**: Parse AST once, reuse for multiple checks
2. **Parallel Processing**: Process files in parallel (not implemented)
3. **Batch Flake8/Mypy**: Run on multiple files at once
4. **Incremental Analysis**: Only analyze changed files

### Memory Usage

- **Low**: Single file mode
- **Moderate**: Project files mode (loads project file records into memory)
- **High**: All projects mode (loads all file records from all projects into memory)

## Usage Examples

### Example 1: Analyze Single File

```python
result = await call_server(
    server_id="code-analysis-server",
    command="comprehensive_analysis",
    params={
        "root_dir": "/home/user/projects/my_project",
        "file_path": "src/main.py",
    },
    use_queue=True
)
```

### Example 2: Analyze All Files in Specific Project

```python
result = await call_server(
    server_id="code-analysis-server",
    command="comprehensive_analysis",
    params={
        "root_dir": "/home/user/projects/my_project",
        "project_id": "123e4567-e89b-12d3-a456-426614174000",
    },
    use_queue=True
)

# Get job status
job_id = result["result"]["job_id"]
status = await call_server(
    server_id="code-analysis-server",
    command="queue_get_job_status",
    params={"job_id": job_id}
)
```

### Example 2b: Analyze All Files in All Projects

```python
result = await call_server(
    server_id="code-analysis-server",
    command="comprehensive_analysis",
    params={
        "root_dir": "/home/user/projects/my_project",
        # project_id not provided - analyzes all projects
    },
    use_queue=True
)

# Get job status
job_id = result["result"]["job_id"]
status = await call_server(
    server_id="code-analysis-server",
    command="queue_get_job_status",
    params={"job_id": job_id}
)
```

### Example 3: Custom Configuration

```python
result = await call_server(
    server_id="code-analysis-server",
    command="comprehensive_analysis",
    params={
        "root_dir": "/home/user/projects/my_project",
        "check_placeholders": True,
        "check_stubs": True,
        "check_duplicates": True,
        "check_flake8": False,  # Skip flake8
        "check_mypy": False,     # Skip mypy
        "duplicate_min_lines": 10,
        "duplicate_min_similarity": 0.9,
        "max_lines": 500,
    },
    use_queue=True
)
```

### Example 4: With Mypy Config

```python
result = await call_server(
    server_id="code-analysis-server",
    command="comprehensive_analysis",
    params={
        "root_dir": "/home/user/projects/my_project",
        "check_mypy": True,
        "mypy_config_file": "mypy.ini",
    },
    use_queue=True
)
```

## Data Persistence

### Results Storage

**Important**: Results of `comprehensive_analysis` are **saved to the database**.

- Results are stored in `comprehensive_analysis_results` table
- Each file's analysis is saved with file modification time (mtime)
- Results are returned in the command response (`SuccessResult.data`)
- Enables incremental analysis - only changed files are analyzed

### Database Schema

**Table**: `comprehensive_analysis_results`

```sql
CREATE TABLE comprehensive_analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    file_mtime REAL NOT NULL,
    results_json TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    created_at REAL DEFAULT (julianday('now')),
    updated_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(file_id, file_mtime)
)
```

### What is Saved

For each analyzed file:
- File ID and project ID
- File modification time (mtime) at analysis
- Complete analysis results (JSON)
- Summary statistics (JSON)
- Timestamp of analysis

### Incremental Analysis

The command implements incremental analysis:

1. **Before analyzing each file**:
   - Gets file modification time (mtime) from disk
   - Checks if analysis results exist in database for this `file_id` and `mtime`
   - If mtime matches (within 0.1s tolerance): **skips analysis**, uses cached results
   - If mtime differs: **performs analysis** and saves new results

2. **Benefits**:
   - Only changed files are analyzed
   - Significantly improves performance for large projects
   - Reduces unnecessary computation

3. **Single File Mode**:
   - If file unchanged: returns cached results from database immediately
   - If file changed: performs analysis and saves new results

### What is Returned

Complete analysis results including:
- All findings (placeholders, stubs, empty methods, imports, duplicates, etc.)
- Summary statistics
- All errors and warnings (flake8, mypy)
- All missing docstrings

All data is returned in the `SuccessResult.data` dictionary.

For single file mode with unchanged file: returns cached results from database.

## Summary

The `comprehensive_analysis` command is a comprehensive code quality analysis tool that:

1. **Combines 9 analysis types** in a single operation
2. **Executes asynchronously** via queue for long-running operations
3. **Tracks progress** during all-files analysis
4. **Logs to dedicated file** for debugging
5. **Handles errors gracefully** without stopping entire analysis
6. **Provides detailed results** with summary statistics
7. **Supports flexible configuration** via boolean flags and parameters
8. **Saves results to database** - enables incremental analysis and caching
9. **Incremental analysis** - only analyzes changed files for better performance

It is designed for:
- Complete code quality audits
- Identifying technical debt
- Monitoring code quality over time
- Finding code quality issues before refactoring
- Generating code quality reports
- Regular automated code quality checks (incremental analysis improves performance)

