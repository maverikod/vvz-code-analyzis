"""
Implementation plan for code analysis features, CST storage, and metrics.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# Implementation Plan for Code Analysis Features

## Overview

This document provides a detailed step-by-step implementation plan for:
1. Code analysis features (complexity, duplicates, unused code)
2. CST storage in database
3. Metrics and analytics

---

## 1. Code Analysis Features

### 1.1 Analyze Complexity (Cyclomatic Complexity)

#### Step 1: Create AST-based complexity analyzer
- **File**: `code_analysis/core/complexity_analyzer.py`
- **Purpose**: Calculate cyclomatic complexity for functions, methods, and classes
- **Implementation**:
  1. Parse AST for each function/method
  2. Count decision points:
     - `if`, `elif`, `else`
     - `for`, `while`
     - `try`, `except`, `finally`
     - `and`, `or` in conditions
     - `case` statements (if applicable)
  3. Complexity = 1 + number of decision points
  4. Store complexity in database (add `complexity` column to `functions` and `methods` tables)

#### Step 2: Create MCP command
- **File**: `code_analysis/commands/analyze_complexity_mcp.py`
- **Command**: `analyze_complexity`
- **Parameters**:
  - `root_dir`: Project root directory
  - `file_path` (optional): Specific file to analyze
  - `project_id` (optional): Project ID
  - `min_complexity` (optional): Minimum complexity threshold for filtering
- **Output**: List of functions/methods with complexity scores
- **Schema**:
  ```python
  {
    "file_path": str,
    "function_name": str,
    "complexity": int,
    "line": int,
    "type": "function" | "method"
  }
  ```

#### Step 3: Database schema updates
- **File**: `code_analysis/core/database/functions.py`
- **Changes**:
  1. Add `complexity` column to `functions` table (INTEGER, nullable)
  2. Add `complexity` column to `methods` table (INTEGER, nullable)
  3. Create migration script: `migrations/add_complexity_columns.sql`
  4. Update `add_function()` and `add_method()` to accept complexity parameter

#### Step 4: Integration with code_mapper
- **File**: `code_analysis/commands/code_mapper_mcp_command.py`
- **Changes**:
  1. Call complexity analyzer during `update_indexes`
  2. Store complexity scores in database
  3. Update indexes with complexity information

#### Step 5: Testing
- Create test file: `tests/test_complexity_analyzer.py`
- Test cases:
  - Simple function (complexity = 1)
  - Function with if/else (complexity = 2)
  - Function with nested loops (complexity = 3+)
  - Class methods complexity
  - Edge cases (empty functions, single-line functions)

---

### 1.2 Find Duplicates (Code Duplication)

#### Step 1: Create duplicate detection algorithm
- **File**: `code_analysis/core/duplicate_detector.py`
- **Purpose**: Find duplicate code blocks using AST normalization
- **Implementation**:
  1. **AST Normalization**:
     - Normalize variable names (replace with placeholders)
     - Normalize string literals (replace with placeholders)
     - Normalize numeric literals (replace with placeholders)
     - Remove comments and docstrings
     - Normalize whitespace
  2. **Hash-based detection**:
     - Generate hash for normalized AST nodes
     - Group nodes by hash
     - Filter groups with size > 1 (duplicates)
  3. **Similarity scoring**:
     - Calculate similarity percentage
     - Use edit distance for similar but not identical code
  4. **Configuration**:
     - `min_lines`: Minimum lines for duplicate block (default: 5)
     - `min_similarity`: Minimum similarity threshold (default: 0.8)
     - `ignore_whitespace`: Ignore whitespace differences (default: True)

#### Step 2: Create MCP command
- **File**: `code_analysis/commands/find_duplicates_mcp.py`
- **Command**: `find_duplicates`
- **Parameters**:
  - `root_dir`: Project root directory
  - `project_id` (optional): Project ID
  - `min_lines` (optional): Minimum lines for duplicate (default: 5)
  - `min_similarity` (optional): Minimum similarity (default: 0.8)
  - `file_path` (optional): Specific file to analyze
- **Output**: List of duplicate code blocks with locations
- **Schema**:
  ```python
  {
    "duplicate_groups": [
      {
        "hash": str,
        "similarity": float,
        "occurrences": [
          {
            "file_path": str,
            "start_line": int,
            "end_line": int,
            "code_snippet": str
          }
        ]
      }
    ]
  }
  ```

#### Step 3: Database schema updates
- **File**: `code_analysis/core/database/duplicates.py` (new)
- **Tables**:
  1. `code_duplicates`:
     - `id`: INTEGER PRIMARY KEY
     - `project_id`: TEXT
     - `duplicate_hash`: TEXT (hash of normalized code)
     - `similarity`: REAL
     - `created_at`: TIMESTAMP
  2. `duplicate_occurrences`:
     - `id`: INTEGER PRIMARY KEY
     - `duplicate_id`: INTEGER (FK to code_duplicates)
     - `file_id`: INTEGER (FK to files)
     - `start_line`: INTEGER
     - `end_line`: INTEGER
     - `ast_node_id`: INTEGER (optional, FK to ast_nodes)
     - `code_snippet`: TEXT

#### Step 4: Integration with code_mapper
- **File**: `code_analysis/commands/code_mapper_mcp_command.py`
- **Changes**:
  1. Add optional `find_duplicates` parameter to `update_indexes`
  2. Run duplicate detection after AST analysis
  3. Store duplicates in database
  4. Update indexes with duplicate information

#### Step 5: Performance optimization
- **Strategies**:
  1. Use incremental detection (only analyze changed files)
  2. Cache normalized AST hashes
  3. Use parallel processing for large projects
  4. Limit analysis to specific file types (Python only initially)

#### Step 6: Testing
- Create test file: `tests/test_duplicate_detector.py`
- Test cases:
  - Identical code blocks
  - Similar code with different variable names
  - Similar code with different string literals
  - Nested duplicates
  - Edge cases (very short blocks, comments only)

---

### 1.3 Find Unused Code (Unused Code Detection)

#### Step 1: Create unused code detector
- **File**: `code_analysis/core/unused_code_detector.py`
- **Purpose**: Find unused functions, classes, methods, and imports
- **Implementation**:
  1. **Build call graph**:
     - Parse all files in project
     - Extract function/method/class definitions
     - Extract function/method/class calls
     - Build directed graph of dependencies
  2. **Find unused definitions**:
     - Functions/methods never called
     - Classes never instantiated or inherited
     - Imports never used
  3. **Configuration**:
     - `check_imports`: Check unused imports (default: True)
     - `check_private`: Check private functions (default: False)
     - `check_tests`: Include test files (default: False)
     - `ignore_patterns`: Patterns to ignore (e.g., `__init__.py`, `__main__.py`)

#### Step 2: Create MCP command
- **File**: `code_analysis/commands/find_unused_code_mcp.py`
- **Command**: `find_unused_code`
- **Parameters**:
  - `root_dir`: Project root directory
  - `project_id` (optional): Project ID
  - `check_imports` (optional): Check unused imports (default: True)
  - `check_private` (optional): Check private functions (default: False)
  - `file_path` (optional): Specific file to analyze
- **Output**: List of unused code elements
- **Schema**:
  ```python
  {
    "unused_functions": [
      {
        "file_path": str,
        "function_name": str,
        "line": int,
        "type": "function" | "method"
      }
    ],
    "unused_classes": [
      {
        "file_path": str,
        "class_name": str,
        "line": int
      }
    ],
    "unused_imports": [
      {
        "file_path": str,
        "import_name": str,
        "line": int,
        "import_type": "import" | "from_import"
      }
    ]
  }
  ```

#### Step 3: Database schema updates
- **File**: `code_analysis/core/database/unused_code.py` (new)
- **Tables**:
  1. `unused_code`:
     - `id`: INTEGER PRIMARY KEY
     - `project_id`: TEXT
     - `file_id`: INTEGER (FK to files)
     - `entity_type`: TEXT ("function", "method", "class", "import")
     - `entity_name`: TEXT
     - `line`: INTEGER
     - `detected_at`: TIMESTAMP
     - `is_false_positive`: BOOLEAN (default: False)

#### Step 4: Integration with code_mapper
- **File**: `code_analysis/commands/code_mapper_mcp_command.py`
- **Changes**:
  1. Add optional `find_unused_code` parameter to `update_indexes`
  2. Build call graph from existing database data
  3. Run unused code detection
  4. Store results in database
  5. Update indexes with unused code information

#### Step 5: Handle edge cases
- **Strategies**:
  1. **False positives**:
     - Functions called via `getattr()` or `eval()`
     - Functions registered as decorators
     - Functions exported in `__all__`
     - Functions used in type hints
  2. **Dynamic imports**:
     - Track `importlib.import_module()` calls
     - Track `__import__()` calls
  3. **Entry points**:
     - Check `setup.py` entry points
     - Check `__main__` blocks
     - Check decorators (e.g., `@app.route()`)

#### Step 6: Testing
- Create test file: `tests/test_unused_code_detector.py`
- Test cases:
  - Unused function
  - Unused class
  - Unused import
  - Function called via string (false positive handling)
  - Function used in type hint
  - Function exported in `__all__`

---

## 2. CST Storage in Database

### 2.1 Database Schema for CST Trees

#### Step 1: Create CST trees table
- **File**: `code_analysis/core/database/cst_trees.py` (new)
- **Table**: `cst_trees`
- **Schema**:
  ```sql
  CREATE TABLE cst_trees (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      file_id INTEGER NOT NULL,
      project_id TEXT NOT NULL,
      cst_data TEXT NOT NULL,  -- JSON serialized CST tree
      cst_hash TEXT NOT NULL,  -- Hash of CST for change detection
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
      UNIQUE(file_id)
  );
  
  CREATE INDEX idx_cst_trees_file_id ON cst_trees(file_id);
  CREATE INDEX idx_cst_trees_project_id ON cst_trees(project_id);
  CREATE INDEX idx_cst_trees_hash ON cst_trees(cst_hash);
  ```

#### Step 2: Create CST storage manager
- **File**: `code_analysis/core/cst_storage.py` (new)
- **Purpose**: Manage CST tree storage and retrieval
- **Implementation**:
  1. **Serialize CST to JSON**:
     - Use LibCST's `code_for_node()` for serialization
     - Store full CST tree structure
     - Compress large trees (optional)
  2. **Deserialize CST from JSON**:
     - Parse JSON back to CST tree
     - Validate CST structure
  3. **Hash calculation**:
     - Calculate hash of CST tree for change detection
     - Use SHA256 hash of normalized CST
  4. **Methods**:
     - `save_cst(file_id, cst_tree) -> bool`
     - `load_cst(file_id) -> Optional[CSTNode]`
     - `get_cst_hash(file_id) -> Optional[str]`
     - `has_cst_changed(file_id, current_cst) -> bool`

#### Step 3: Database methods
- **File**: `code_analysis/core/database/cst_trees.py`
- **Methods**:
  ```python
  def save_cst_tree(
      self,
      file_id: int,
      project_id: str,
      cst_data: str,
      cst_hash: str
  ) -> int:
      """Save CST tree to database."""
      
  def get_cst_tree(self, file_id: int) -> Optional[Dict[str, Any]]:
      """Get CST tree from database."""
      
  def delete_cst_tree(self, file_id: int) -> None:
      """Delete CST tree from database."""
      
  def get_cst_hash(self, file_id: int) -> Optional[str]:
      """Get CST hash for change detection."""
      
  def get_cst_trees_for_project(
      self,
      project_id: str
  ) -> List[Dict[str, Any]]:
      """Get all CST trees for a project."""
  ```

---

### 2.2 Integration with update_indexes

#### Step 1: Modify code_mapper command
- **File**: `code_analysis/commands/code_mapper_mcp_command.py`
- **Changes**:
  1. Import CST storage manager
  2. After AST analysis, parse file with LibCST
  3. Save CST tree to database
  4. Update `updated_at` timestamp

#### Step 2: CST parsing logic
- **File**: `code_analysis/core/cst_parser.py` (new or extend existing)
- **Implementation**:
  1. Parse file with LibCST
  2. Validate CST structure
  3. Calculate hash
  4. Serialize to JSON
  5. Store in database

#### Step 3: Incremental updates
- **Strategy**:
  1. Check if CST hash changed
  2. Only update if hash differs
  3. Skip unchanged files

#### Step 4: Error handling
- **Cases**:
  1. Invalid CST (syntax errors)
  2. Large files (compression or chunking)
  3. Database errors
  4. Memory issues

---

### 2.3 Integration with repair_database

#### Step 1: Add CST restoration to repair command
- **File**: `code_analysis/commands/database_integrity_mcp_commands.py`
- **Method**: `repair_database` (extend existing)
- **Changes**:
  1. Add `restore_from_cst` parameter (default: False)
  2. If enabled, restore files from CST trees
  3. Validate restored files
  4. Update database with restored content

#### Step 2: CST restoration logic
- **File**: `code_analysis/core/cst_restore.py` (new)
- **Purpose**: Restore files from CST trees
- **Implementation**:
  1. **Load CST from database**:
     - Get CST tree for file
     - Deserialize JSON to CST node
  2. **Generate code from CST**:
     - Use LibCST's `code_for_node()`
     - Generate formatted code
  3. **Validate restored code**:
     - Parse with AST to check syntax
     - Compare with original (if available)
  4. **Update database**:
     - Update `code_content` table
     - Update `files` table
     - Re-run AST analysis

#### Step 3: Batch restoration
- **Strategy**:
  1. Restore files in batches
  2. Validate each batch
  3. Rollback on errors
  4. Log restoration progress

#### Step 4: Testing
- Create test file: `tests/test_cst_restore.py`
- Test cases:
  - Restore single file
  - Restore multiple files
  - Restore with syntax errors (should fail)
  - Restore missing CST (should skip)
  - Validate restored code matches original

---

## 3. Metrics and Analytics

### 3.1 Get Metrics Command

#### Step 1: Create metrics collector
- **File**: `code_analysis/core/metrics_collector.py` (new)
- **Purpose**: Collect various code metrics
- **Metrics**:
  1. **Code metrics**:
     - Total lines of code (LOC)
     - Total files
     - Total functions/classes/methods
     - Average complexity
     - Total complexity
  2. **Quality metrics**:
     - Code duplication percentage
     - Unused code percentage
     - Test coverage (if available)
     - Documentation coverage (docstring percentage)
  3. **Project metrics**:
     - Files by type (Python, config, etc.)
     - Files by size
     - Files by complexity
     - Growth trends (if historical data available)

#### Step 2: Create MCP command
- **File**: `code_analysis/commands/get_metrics_mcp.py`
- **Command**: `get_metrics`
- **Parameters**:
  - `root_dir`: Project root directory
  - `project_id` (optional): Project ID
  - `metrics` (optional): List of specific metrics to return (default: all)
- **Output**: Dictionary with various metrics
- **Schema**:
  ```python
  {
    "code_metrics": {
      "total_lines": int,
      "total_files": int,
      "total_functions": int,
      "total_classes": int,
      "total_methods": int,
      "average_complexity": float,
      "total_complexity": int
    },
    "quality_metrics": {
      "duplication_percentage": float,
      "unused_code_percentage": float,
      "documentation_coverage": float
    },
    "project_metrics": {
      "files_by_type": Dict[str, int],
      "files_by_size": Dict[str, int],
      "files_by_complexity": Dict[str, int]
    }
  }
  ```

#### Step 3: Database queries
- **File**: `code_analysis/core/database/metrics.py` (new)
- **Methods**:
  ```python
  def get_code_metrics(self, project_id: str) -> Dict[str, Any]:
      """Get code metrics for project."""
      
  def get_quality_metrics(self, project_id: str) -> Dict[str, Any]:
      """Get quality metrics for project."""
      
  def get_project_metrics(self, project_id: str) -> Dict[str, Any]:
      """Get project-level metrics."""
  ```

#### Step 4: Caching
- **Strategy**:
  1. Cache metrics in database
  2. Update cache on `update_indexes`
  3. Invalidate cache on file changes
  4. TTL for cache (optional)

---

### 3.2 Analyze Changes (Git Diff Analysis)

#### Step 1: Create git diff analyzer
- **File**: `code_analysis/core/git_diff_analyzer.py` (new)
- **Purpose**: Analyze git diff to understand code changes
- **Implementation**:
  1. **Parse git diff**:
     - Use `git diff` command or library
     - Parse added/removed/modified lines
     - Identify changed functions/classes
  2. **Change analysis**:
     - Function additions/deletions
     - Function modifications
     - Class additions/deletions
     - Import changes
     - Complexity changes
  3. **Impact analysis**:
     - Affected functions
     - Affected tests
     - Breaking changes detection

#### Step 2: Create MCP command
- **File**: `code_analysis/commands/analyze_changes_mcp.py`
- **Command**: `analyze_changes`
- **Parameters**:
  - `root_dir`: Project root directory
  - `commit_range` (optional): Git commit range (e.g., "HEAD~1..HEAD")
  - `file_path` (optional): Specific file to analyze
  - `include_stats` (optional): Include statistics (default: True)
- **Output**: Analysis of code changes
- **Schema**:
  ```python
  {
    "commit_range": str,
    "files_changed": int,
    "lines_added": int,
    "lines_removed": int,
    "functions_added": List[str],
    "functions_removed": List[str],
    "functions_modified": List[str],
    "classes_added": List[str],
    "classes_removed": List[str],
    "complexity_changes": Dict[str, int],
    "breaking_changes": List[str]
  }
  ```

#### Step 3: Integration with git
- **Dependencies**:
  - `gitpython` library (optional)
  - Or use `subprocess` to call `git` command
- **Error handling**:
  - Not a git repository
  - Invalid commit range
  - Missing commits

#### Step 4: Testing
- Create test file: `tests/test_git_diff_analyzer.py`
- Test cases:
  - Analyze single commit
  - Analyze commit range
  - Analyze specific file
  - Handle non-git repository
  - Handle invalid commit range

---

### 3.3 Analyze Dependencies (Circular Dependencies)

#### Step 1: Create dependency analyzer
- **File**: `code_analysis/core/dependency_analyzer.py` (new)
- **Purpose**: Detect circular dependencies
- **Implementation**:
  1. **Build dependency graph**:
     - Parse all imports in project
     - Build directed graph (module -> imported modules)
     - Store in database (extend existing `dependencies` table)
  2. **Detect cycles**:
     - Use DFS (Depth-First Search) to find cycles
     - Identify all cycles in graph
     - Calculate cycle length
  3. **Cycle analysis**:
     - Find shortest cycle
     - Find longest cycle
     - Find all modules in cycles
     - Suggest breaking points

#### Step 2: Create MCP command
- **File**: `code_analysis/commands/analyze_dependencies_mcp.py`
- **Command**: `analyze_dependencies`
- **Parameters**:
  - `root_dir`: Project root directory
  - `project_id` (optional): Project ID
  - `find_circular` (optional): Find circular dependencies (default: True)
  - `find_unused` (optional): Find unused dependencies (default: False)
- **Output**: Dependency analysis results
- **Schema**:
  ```python
  {
    "total_dependencies": int,
    "circular_dependencies": [
      {
        "cycle": List[str],  # Module names in cycle
        "length": int,
        "modules": List[str]
      }
    ],
    "unused_dependencies": List[str],
    "dependency_graph": Dict[str, List[str]]  # module -> dependencies
  }
  ```

#### Step 3: Database schema updates
- **File**: `code_analysis/core/database/dependencies.py` (extend existing)
- **Changes**:
  1. Add `is_circular` column to `dependencies` table
  2. Add `cycle_id` column to track cycles
  3. Create `circular_dependencies` table:
     ```sql
     CREATE TABLE circular_dependencies (
         id INTEGER PRIMARY KEY,
         project_id TEXT NOT NULL,
         cycle_id TEXT NOT NULL,  -- Unique ID for cycle
         modules TEXT NOT NULL,  -- JSON array of module names
         length INTEGER NOT NULL,
         detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
     );
     ```

#### Step 4: Cycle detection algorithm
- **Algorithm**:
  1. Build adjacency list from dependencies
  2. For each node, run DFS to find cycles
  3. Track visited nodes and recursion stack
  4. When back edge found, extract cycle
  5. Store cycles in database

#### Step 5: Visualization (optional)
- **File**: `code_analysis/core/dependency_visualizer.py` (new)
- **Purpose**: Generate dependency graph visualization
- **Output**: Graphviz DOT format or Mermaid diagram
- **Integration**: Add to `analyze_dependencies` command output

#### Step 6: Testing
- Create test file: `tests/test_dependency_analyzer.py`
- Test cases:
  - Simple circular dependency (A -> B -> A)
  - Complex circular dependency (A -> B -> C -> A)
  - Multiple cycles
  - No cycles
  - Self-referential imports

---

## Implementation Order

### Phase 1: Foundation (Week 1-2)
1. CST storage in database
   - Database schema
   - CST storage manager
   - Integration with `update_indexes`
   - Testing

### Phase 2: Code Analysis (Week 3-4)
2. Complexity analysis
   - Complexity analyzer
   - MCP command
   - Database integration
   - Testing
3. Duplicate detection
   - Duplicate detector
   - MCP command
   - Database integration
   - Testing

### Phase 3: Advanced Analysis (Week 5-6)
4. Unused code detection
   - Unused code detector
   - MCP command
   - Database integration
   - Testing
5. Dependency analysis
   - Dependency analyzer
   - Circular dependency detection
   - MCP command
   - Testing

### Phase 4: Metrics and Analytics (Week 7-8)
6. Metrics collection
   - Metrics collector
   - MCP command
   - Database integration
   - Testing
7. Git diff analysis
   - Git diff analyzer
   - MCP command
   - Testing
8. CST restoration
   - CST restore logic
   - Integration with `repair_database`
   - Testing

---

## Testing Strategy

### Unit Tests
- Each component tested independently
- Mock dependencies where needed
- Test edge cases and error handling

### Integration Tests
- Test full workflows
- Test database operations
- Test MCP command execution

### Performance Tests
- Test with large codebases
- Measure execution time
- Optimize slow operations

---

## Documentation

### Code Documentation
- Docstrings for all functions/classes
- Type hints for all parameters
- Examples in docstrings

### User Documentation
- Update `docs/SERVER_CAPABILITIES_ANALYSIS.md`
- Create usage examples
- Document command parameters

---

## Notes

1. **Incremental Implementation**: Implement features incrementally, testing each step
2. **Backward Compatibility**: Ensure new features don't break existing functionality
3. **Performance**: Consider performance impact, especially for large codebases
4. **Error Handling**: Robust error handling for all edge cases
5. **Logging**: Comprehensive logging for debugging and monitoring

