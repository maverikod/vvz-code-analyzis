# Analysis of update_indexes Command Algorithm

**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com  
**Date**: 2026-01-09

## Overview

The `update_indexes` command (`UpdateIndexesMCPCommand`) is a long-running MCP command that analyzes Python project files and updates code indexes in the SQLite database. This document provides a detailed analysis of its algorithm and workflow.

## Command Location

- **File**: `code_analysis/commands/code_mapper_mcp_command.py`
- **Class**: `UpdateIndexesMCPCommand`
- **MCP Command Name**: `update_indexes`
- **Execution Mode**: Queue-based (long-running operation)

## High-Level Algorithm Flow

```
1. Validate Input
   └─> Validate root_dir exists and is a directory
   
2. Database Integrity Check
   ├─> Check corruption marker
   │   └─> If exists: Return error (safe mode)
   ├─> Check SQLite integrity
   │   ├─> If corrupted:
   │   │   ├─> Stop workers (file_watcher, vectorization)
   │   │   ├─> Create backup
   │   │   ├─> Write corruption marker
   │   │   └─> Return error (safe mode)
   │   └─> If OK: Continue
   
3. Database Setup
   ├─> Open database connection
   └─> Get or create project_id
   
4. File Discovery
   ├─> Walk directory tree
   ├─> Filter by ignore patterns (.git, __pycache__, node_modules, data, logs)
   ├─> Collect .py files
   └─> Return list of Python files
   
5. File Processing Loop (Sequential)
   └─> For each Python file:
       ├─> _analyze_file()
       │   ├─> Validate file exists
       │   ├─> Read file content
       │   ├─> Get/update file record in database
       │   ├─> Parse AST (with comments)
       │   ├─> Save AST tree to database
       │   ├─> Save CST (source code) to database
       │   ├─> Extract and save entities:
       │   │   ├─> Classes (with methods)
       │   │   ├─> Functions
       │   │   └─> Imports
       │   ├─> Calculate complexity for functions/methods
       │   ├─> Add content to full-text search index
       │   └─> Mark file for chunking
       └─> Update progress tracker
   
6. Return Results
   └─> Aggregate statistics and return SuccessResult
```

## Detailed Algorithm Analysis

### 1. Main Entry Point: `execute()` Method

**Location**: Lines 550-806

**Algorithm Steps**:

1. **Input Validation** (Line 591)
   - Validates `root_dir` exists and is a directory
   - Sets default `max_lines` if not provided

2. **Database Integrity Check** (Lines 602-657)
   - **Check Corruption Marker** (Line 602)
     - Reads corruption marker from filesystem
     - If exists: Returns error immediately (safe mode)
   - **Check SQLite Integrity** (Line 620)
     - Runs `PRAGMA integrity_check`
     - If corrupted:
       - Stops workers (file_watcher, vectorization)
       - Creates backup of database files
       - Writes corruption marker
       - Returns error (safe mode)

3. **Database Connection** (Line 659)
   - Opens database connection
   - Gets or creates project_id

4. **File Discovery** (Lines 667-678)
   - Uses `os.walk()` to traverse directory tree
   - Filters directories by ignore patterns
   - Collects all `.py` files
   - Returns list of `Path` objects

5. **File Processing** (Lines 713-757)
   - **Sequential Processing**: Files are processed one by one
   - **Progress Tracking**: Updates progress tracker every file
   - **Error Handling**: Collects error samples (max 5)
   - **Logging**: Logs every 100 files

6. **Result Aggregation** (Lines 762-798)
   - Counts successful, error, and syntax_error files
   - Aggregates entity counts (classes, functions, methods, imports)
   - Returns `SuccessResult` with statistics

### 2. File Analysis: `_analyze_file()` Method

**Location**: Lines 133-548

**Algorithm Steps**:

1. **File Validation** (Lines 154-199)
   - Resolves absolute paths
   - Checks file exists
   - Gets file modification time
   - Reads file content (UTF-8)

2. **Database Record Management** (Lines 203-270)
   - Gets or creates dataset_id
   - Gets existing file record or creates new one
   - Updates file metadata if:
     - `force=True`, OR
     - `last_modified` differs from `file_mtime` (with epsilon tolerance)
   - Extracts docstring for `has_docstring` flag

3. **AST Parsing** (Lines 272-279)
   - Uses `parse_with_comments()` to preserve comments
   - Handles syntax errors gracefully (returns error result)

4. **AST Tree Storage** (Lines 281-308)
   - Serializes AST to JSON
   - Calculates SHA256 hash of AST JSON
   - Saves AST tree to database with:
     - `file_id`
     - `project_id`
     - AST JSON
     - AST hash
     - File modification time
     - `overwrite=True`

5. **CST Tree Storage** (Lines 310-333)
   - Calculates SHA256 hash of source code
   - Saves CST (source code) to database with:
     - `file_id`
     - `project_id`
     - Source code content
     - CST hash
     - File modification time
     - `overwrite=True`

6. **Full-Text Search Index** (Lines 342-364)
   - Adds entire file content to FTS index
   - Entity type: "file"
   - Entity name: relative file path
   - Content: full file content
   - Docstring: module docstring

7. **Entity Extraction** (Lines 366-521)
   - **Classes** (Lines 366-402):
     - Extracts class name, line number, docstring
     - Extracts base classes
     - Saves to database
     - Adds class content to FTS index
     - Processes methods within class
   - **Methods** (Lines 404-448):
     - Extracts method name, line number, arguments, docstring
     - Calculates cyclomatic complexity
     - Saves to database
     - Adds method content to FTS index
   - **Functions** (Lines 450-506):
     - Distinguishes functions from methods (checks if inside class)
     - Extracts function name, line number, arguments, docstring
     - Calculates cyclomatic complexity
     - Saves to database
     - Adds function content to FTS index
   - **Imports** (Lines 508-521):
     - Processes `ast.Import` and `ast.ImportFrom` nodes
     - Extracts module name, imported name, import type
     - Saves to database

8. **Chunking Mark** (Line 523)
   - Marks file for chunking (vectorization worker will process)

9. **Return Result** (Lines 525-532)
   - Returns dictionary with:
     - File path
     - Status (success/error/syntax_error)
     - Entity counts (classes, functions, methods, imports)

## Key Design Decisions

### 1. Sequential Processing

**Decision**: Files are processed sequentially, not in parallel.

**Rationale**:
- Database operations are synchronous
- Prevents database locking issues
- Easier error handling and progress tracking
- Simpler implementation

**Trade-offs**:
- Slower for large projects
- Could be optimized with parallel processing (requires careful database connection management)

### 2. Force Update Mechanism

**Decision**: Uses `force` parameter and `last_modified` comparison to determine if file needs update.

**Algorithm** (Lines 221-243):
```python
if force or abs(last_modified - file_mtime) > epsilon:
    # Update file record
```

**Rationale**:
- Avoids unnecessary database writes
- Handles file timestamp precision issues (epsilon tolerance)
- Allows forced updates when needed (e.g., after `clear_file_data`)

### 3. AST and CST Storage

**Decision**: Stores both AST (abstract syntax tree) and CST (concrete syntax tree/source code).

**Rationale**:
- AST: For code analysis and transformation
- CST: For code editing and source code retrieval
- Both needed for different use cases

**Storage**:
- AST: JSON serialization of AST dump
- CST: Raw source code content
- Both include hash for change detection

### 4. Full-Text Search Index

**Decision**: Adds code content to FTS index at multiple levels:
- File level (entire file content)
- Class level (class source code)
- Method level (method source code)
- Function level (function source code)

**Rationale**:
- Enables fast text search across codebase
- Multiple granularity levels for better search results
- Guaranteed baseline (file-level) even if entity extraction fails

### 5. Error Handling Strategy

**Decision**: Continues processing even if individual files fail.

**Algorithm**:
- Syntax errors: Returns `syntax_error` status, continues
- Other errors: Returns `error` status, continues
- Collects error samples (max 5) for reporting
- Aggregates error counts in final result

**Rationale**:
- Robustness: One bad file shouldn't stop entire indexing
- User feedback: Error samples help identify problematic files
- Statistics: Error counts provide overview of issues

### 6. Database Integrity Protection

**Decision**: Checks database integrity before starting, enters safe mode if corrupted.

**Algorithm**:
1. Check corruption marker (fast check)
2. If marker exists: Return error immediately
3. Run SQLite integrity check
4. If corrupted:
   - Stop workers
   - Create backup
   - Write corruption marker
   - Return error

**Rationale**:
- Prevents further corruption
- Provides recovery mechanism (backup + marker)
- Stops workers to prevent concurrent access issues

## Performance Characteristics

### Time Complexity

- **File Discovery**: O(n) where n = number of files/directories
- **File Processing**: O(m * k) where:
  - m = number of Python files
  - k = average file size (for AST parsing and entity extraction)
- **Database Operations**: O(m) for file records, O(e) for entities where e = total entities

**Overall**: O(m * k + e) - Linear in number of files and entities

### Space Complexity

- **File Content**: O(m * k) - Stores all file content in memory during processing
- **AST Trees**: O(m * k) - AST JSON for each file
- **CST Trees**: O(m * k) - Source code for each file
- **Database**: O(m + e) - File records and entity records

**Overall**: O(m * k) - Linear in total code size

### Bottlenecks

1. **Sequential Processing**: Main bottleneck for large projects
2. **AST Parsing**: CPU-intensive for large files
3. **Database Writes**: I/O-intensive, especially for many entities
4. **Full-Text Search Index**: Can be slow for large codebases

## Potential Optimizations

### 1. Parallel Processing

**Current**: Sequential file processing  
**Optimization**: Process files in parallel with thread pool

**Challenges**:
- Database connection management (need connection per thread)
- Progress tracking synchronization
- Error collection synchronization

**Expected Improvement**: 2-4x speedup (depending on I/O vs CPU bound)

### 2. Incremental Updates

**Current**: Processes all files every time  
**Optimization**: Only process changed files (based on `last_modified`)

**Implementation**:
- Compare `file_mtime` with `last_modified` in database
- Skip files that haven't changed
- Only process new or modified files

**Expected Improvement**: 10-100x speedup for large projects with few changes

### 3. Batch Database Operations

**Current**: Individual database writes per entity  
**Optimization**: Batch inserts for entities

**Implementation**:
- Collect entities for all files
- Use batch INSERT statements
- Reduces database round-trips

**Expected Improvement**: 2-5x speedup for entity insertion

### 4. Lazy AST/CST Storage

**Current**: Always saves AST/CST  
**Optimization**: Only save if AST/CST hash changed

**Implementation**:
- Compare AST/CST hash with stored hash
- Skip save if unchanged

**Expected Improvement**: 10-50% speedup for unchanged files

## Edge Cases and Error Handling

### 1. File Not Found

**Handling**: Returns error result, continues with next file

### 2. Syntax Errors

**Handling**: Returns `syntax_error` status, continues with next file

### 3. Unicode Decode Errors

**Handling**: Returns error result, continues with next file

### 4. Database Corruption

**Handling**: 
- Detects corruption before processing
- Creates backup
- Enters safe mode
- Returns error immediately

### 5. Large Files

**Handling**: No special handling (processes all files regardless of size)

**Potential Issue**: Memory usage for very large files

### 6. Concurrent Access

**Handling**: No explicit locking (relies on SQLite locking)

**Potential Issue**: Concurrent updates from file watcher

## Integration Points

### 1. File Watcher

**Current**: File watcher marks files for chunking, but doesn't call `update_indexes`

**Integration**: File watcher could call `update_indexes` for changed files

### 2. Vectorization Worker

**Current**: Vectorization worker processes files marked for chunking

**Integration**: Works correctly - files are marked for chunking after indexing

### 3. CST Compose Command

**Current**: `compose_cst_module` edits files but doesn't update indexes

**Integration**: Should call `update_indexes` after file edits (or use `update_file_data_atomic`)

## Recommendations

### 1. Add Incremental Update Support

- Compare `file_mtime` with `last_modified` before processing
- Skip unchanged files
- Significant performance improvement for large projects

### 2. Add Parallel Processing Option

- Make parallel processing optional (via parameter)
- Use thread pool for file processing
- Requires careful database connection management

### 3. Add Progress Persistence

- Save progress to database
- Allow resuming interrupted indexing
- Useful for very large projects

### 4. Optimize Database Operations

- Use batch inserts for entities
- Reduce database round-trips
- Use transactions for better performance

### 5. Add File Size Limits

- Skip or warn about very large files
- Prevent memory issues
- Configurable threshold

## Conclusion

The `update_indexes` command is a well-designed, robust indexing system with good error handling and database integrity protection. The main areas for improvement are:

1. **Performance**: Sequential processing and lack of incremental updates
2. **Integration**: Better integration with file watcher and CST compose command
3. **Optimization**: Batch operations and lazy updates

The algorithm is correct and handles edge cases well, but could benefit from performance optimizations for large codebases.

