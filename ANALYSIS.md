# Code Mapper Analysis and Improvement Plan

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

## Current State Analysis

### Purpose
The code_mapper utility is designed for AI model-programmers to understand codebase structure, find methods, classes, and detect code quality issues.

### Current Features
1. **Code Structure Analysis**
   - Classes with methods and inheritance
   - Functions with signatures
   - Imports and dependencies
   - File-level information

2. **Issue Detection**
   - Missing docstrings (files, classes, methods)
   - Methods with only `pass` statements
   - `NotImplementedError` in non-abstract methods
   - Files exceeding line limit
   - `Any` type usage
   - Generic exception handling
   - Invalid imports
   - Imports in the middle of files

3. **Output Format**
   - YAML files: `code_map.yaml`, `code_issues.yaml`, `method_index.yaml`

### Current Limitations

1. **Storage Format (YAML)**
   - Slow for large codebases
   - No indexing for fast searches
   - Difficult to query complex relationships
   - Full file rewrite on each update
   - No incremental updates
   - Large files for big projects

2. **Search Capabilities**
   - No built-in search functionality
   - Requires parsing YAML files manually
   - No filtering or querying

3. **Performance**
   - Full re-analysis on each run
   - No caching of unchanged files
   - Sequential file processing

4. **Data Relationships**
   - Difficult to track dependencies between files
   - No easy way to find all usages of a class/function
   - Limited cross-referencing

## Proposed Improvements

### 1. SQLite Database Storage (Priority: High)
**Benefits:**
- Fast indexed searches
- SQL queries for complex filtering
- Incremental updates (only changed files)
- Single database file instead of multiple YAML files
- Better for AI model queries
- Versioning support possible

**Schema Design:**
- `files` - file metadata
- `classes` - class definitions
- `functions` - function definitions
- `methods` - method definitions (linked to classes)
- `imports` - import statements
- `issues` - detected issues
- `dependencies` - file dependencies

### 2. Incremental Updates (Priority: High)
- Track file modification times
- Only re-analyze changed files
- Mark deleted files
- Update timestamps

### 3. Enhanced Search API (Priority: Medium)
- Search by name (classes, functions, methods)
- Search by file path
- Search by issue type
- Find all usages of a symbol
- Dependency graph queries

### 4. Performance Optimizations (Priority: Medium)
- Parallel file processing
- AST caching for unchanged files
- Batch database inserts

### 5. Additional Features for AI Models (Priority: Low)
- Code embeddings storage (for semantic search)
- Change history tracking
- Code metrics (complexity, test coverage hints)
- Cross-reference links

## Implementation Plan

### Phase 1: SQLite Migration
1. Create database schema
2. Implement database module
3. Migrate reporter to use SQLite
4. Maintain backward compatibility (optional YAML export)

### Phase 2: Incremental Updates
1. Add file timestamp tracking
2. Implement change detection
3. Update only modified files

### Phase 3: Search API
1. Add query methods
2. CLI search commands
3. Export filtered results

## Database Schema

```sql
-- Files table
CREATE TABLE files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    lines INTEGER,
    last_modified REAL,
    has_docstring BOOLEAN,
    created_at REAL DEFAULT (julianday('now')),
    updated_at REAL DEFAULT (julianday('now'))
);

-- Classes table
CREATE TABLE classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    line INTEGER NOT NULL,
    docstring TEXT,
    bases TEXT,  -- JSON array of base classes
    created_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    UNIQUE(file_id, name, line)
);

-- Methods table (methods are functions within classes)
CREATE TABLE methods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    line INTEGER NOT NULL,
    args TEXT,  -- JSON array of argument names
    docstring TEXT,
    is_abstract BOOLEAN DEFAULT 0,
    has_pass BOOLEAN DEFAULT 0,
    has_not_implemented BOOLEAN DEFAULT 0,
    created_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    UNIQUE(class_id, name, line)
);

-- Functions table (standalone functions)
CREATE TABLE functions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    line INTEGER NOT NULL,
    args TEXT,  -- JSON array of argument names
    docstring TEXT,
    created_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    UNIQUE(file_id, name, line)
);

-- Imports table
CREATE TABLE imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    module TEXT,
    import_type TEXT,  -- 'import' or 'import_from'
    line INTEGER NOT NULL,
    created_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

-- Issues table
CREATE TABLE issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER,
    class_id INTEGER,
    function_id INTEGER,
    method_id INTEGER,
    issue_type TEXT NOT NULL,
    line INTEGER,
    description TEXT,
    metadata TEXT,  -- JSON for additional data
    created_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    FOREIGN KEY (function_id) REFERENCES functions(id) ON DELETE CASCADE,
    FOREIGN KEY (method_id) REFERENCES methods(id) ON DELETE CASCADE
);

-- Dependencies table (file-to-file dependencies)
CREATE TABLE dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file_id INTEGER NOT NULL,
    target_file_id INTEGER NOT NULL,
    dependency_type TEXT,  -- 'import', 'import_from', etc.
    created_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (source_file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY (target_file_id) REFERENCES files(id) ON DELETE CASCADE,
    UNIQUE(source_file_id, target_file_id)
);

-- Indexes for performance
CREATE INDEX idx_files_path ON files(path);
CREATE INDEX idx_classes_name ON classes(name);
CREATE INDEX idx_classes_file ON classes(file_id);
CREATE INDEX idx_methods_name ON methods(name);
CREATE INDEX idx_methods_class ON methods(class_id);
CREATE INDEX idx_functions_name ON functions(name);
CREATE INDEX idx_functions_file ON functions(file_id);
CREATE INDEX idx_imports_file ON imports(file_id);
CREATE INDEX idx_imports_name ON imports(name);
CREATE INDEX idx_issues_type ON issues(issue_type);
CREATE INDEX idx_issues_file ON issues(file_id);
```
