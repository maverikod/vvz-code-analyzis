# Database Driver RPC Refactoring - Technical Specification

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2026-01-13

## 🚨 CRITICAL: New Project Implementation

**⚠️ THIS IS A NEW PROJECT - NO MIGRATION, NO BACKWARD COMPATIBILITY, NO FALLBACKS ⚠️**

- ❌ **NO migration** from old code
- ❌ **NO backward compatibility** with old architecture
- ❌ **NO fallback mechanisms** to old code
- ✅ **NEW implementation** from scratch
- ✅ **Complete removal** of old code (`CodeDatabase`, `SQLiteDriverProxy`, `DBWorkerManager`)
- ✅ **Clean break** - old architecture is completely replaced

## Executive Summary

This document describes the implementation of a new database architecture where database drivers run in separate processes managed by WorkerManager, with RPC-based communication between the main process and driver process. The architecture introduces a client library that provides object-oriented API (Project, File, Attributes) while the driver works with low-level database operations (tables, columns, cells).

**Key Principles**:
- ✅ **New implementation from scratch** - No migration from old code
- ✅ **No backward compatibility** - Old code is completely removed
- ✅ **No fallbacks** - New architecture is the only implementation
- ✅ **Clean break** - Old `CodeDatabase`, `SQLiteDriverProxy`, `DBWorkerManager` are removed

## Current Architecture (Problems)

### Current Flow

```
Main Process
  ↓
CodeDatabase (in-process)
  ↓
SQLiteDriverProxy (in-process)
  ↓
DBWorkerManager.get_or_start_worker()
  ↓
DB Worker Process (separate process)
  ↓
SQLiteDriver (direct SQLite access)
```

### Problems

1. **Driver runs in main process**: SQLiteDriverProxy runs in the main process, causing issues in daemon mode
2. **Lazy initialization**: DB worker starts only when first database connection is requested
3. **No driver configuration in config**: Driver type is hardcoded as "sqlite_proxy"
4. **Tight coupling**: CodeDatabase directly instantiates drivers
5. **No RPC abstraction**: Direct process communication via Unix sockets without proper RPC layer

## Target Architecture

### New Flow

```
Main Process
  ↓
WorkerManager.start_database_driver()
  ↓
Database Driver Process (separate process, managed by WorkerManager)
  ↓
RPC Server (in driver process)
  ↓
Database Driver Implementation (SQLite, PostgreSQL, MySQL, etc.)
  ↓
Database Client Library (in main process and workers)
  ↓
RPC Client (communicates with driver process)
  ↓
Object-Oriented API (Project, File, Attributes)
  ↓
Workers and Commands (use client library)
```

### Key Components

1. **Database Driver Process**: Separate process running database driver (SQLite, PostgreSQL, etc.)
   - **Works with tables**: All operations are table-level (insert, update, delete, select)
   - **Request queue**: Queue is managed inside driver process
   - **No object models**: Driver doesn't know about Project, File, etc. - only tables
2. **RPC Server**: Handles requests from clients, executes database operations
3. **RPC Client**: Communicates with driver process via RPC
4. **Client Library**: Object-oriented API for database operations
   - **Object-to-table mapping**: Client converts objects to table operations
5. **WorkerManager**: Manages driver process lifecycle (start, stop, restart)

## Configuration Structure

### Config File Schema

```json
{
  "code_analysis": {
    "database": {
      "driver": {
        "type": "sqlite_proxy",
        "config": {
          "path": "data/code_analysis.db",
          "backup_dir": "data/backups",
          "worker_config": {
            "command_timeout": 30.0,
            "poll_interval": 0.1
          }
        }
      }
    }
  }
}
```

### Driver-Specific Configurations

#### SQLite Proxy Driver

```json
{
  "type": "sqlite_proxy",
  "config": {
    "path": "data/code_analysis.db",
    "backup_dir": "data/backups",
    "worker_config": {
      "command_timeout": 30.0,
      "poll_interval": 0.1,
      "worker_log_path": "logs/db_worker.log"
    }
  }
}
```

#### PostgreSQL Driver (Future)

```json
{
  "type": "postgres",
  "config": {
    "host": "localhost",
    "port": 5432,
    "database": "code_analysis",
    "user": "code_analysis",
    "password": "secret",
    "ssl_mode": "require"
  }
}
```

#### MySQL Driver (Future)

```json
{
  "type": "mysql",
  "config": {
    "host": "localhost",
    "port": 3306,
    "database": "code_analysis",
    "user": "code_analysis",
    "password": "secret",
    "charset": "utf8mb4"
  }
}
```

## Process Architecture

### Startup Sequence

```
1. Main Process starts
   ↓
2. Load configuration (config.json)
   ↓
3. WorkerManager.start_database_driver()
   ├─ Read driver config from code_analysis.database.driver
   ├─ Start driver process (multiprocessing.Process)
   ├─ Driver process initializes RPC server
   └─ Driver process connects to database
   ↓
4. Database Client Library connects to RPC server
   ↓
5. Start other workers (vectorization, file_watcher)
   ├─ Workers use Database Client Library
   └─ All database operations go through RPC
   ↓
6. Start server (Hypercorn)
```

### Driver Process Lifecycle

```
WorkerManager.start_database_driver()
  ↓
multiprocessing.Process(
  target=run_database_driver,
  args=(driver_type, driver_config),
  daemon=False
)
  ↓
run_database_driver()
  ├─ Initialize RPC server (Unix socket or TCP)
  ├─ Load driver implementation (SQLite, PostgreSQL, etc.)
  ├─ Connect to database
  └─ Start RPC server loop
```

## RPC Protocol

### Communication Method

- **Transport**: Unix socket (local) or TCP (remote)
- **Protocol**: JSON-RPC 2.0 or custom binary protocol
- **Serialization**: JSON for text, MessagePack for binary

### RPC Methods

#### Low-Level Database Operations (Driver Side)

```python
# Table operations
rpc.create_table(schema: dict) -> bool
rpc.drop_table(table_name: str) -> bool
rpc.alter_table(table_name: str, changes: dict) -> bool

# Data operations
rpc.insert(table_name: str, data: dict) -> int  # Returns row ID
rpc.update(table_name: str, where: dict, data: dict) -> int  # Returns affected rows
rpc.delete(table_name: str, where: dict) -> int  # Returns affected rows
rpc.select(table_name: str, where: dict, columns: list, limit: int, offset: int) -> list[dict]
rpc.execute(sql: str, params: tuple) -> dict  # Generic SQL execution

# Transaction operations
rpc.begin_transaction() -> str  # Returns transaction ID
rpc.commit_transaction(transaction_id: str) -> bool
rpc.rollback_transaction(transaction_id: str) -> bool

# Schema operations
rpc.get_table_info(table_name: str) -> list[dict]
rpc.get_schema_version() -> str
rpc.sync_schema(schema_definition: dict, backup_dir: str) -> dict
```

#### High-Level Object Operations (Client Side)

```python
# Project operations
client.create_project(project: Project) -> Project
client.get_project(project_id: str) -> Project
client.update_project(project: Project) -> Project
client.delete_project(project_id: str) -> bool
client.list_projects() -> list[Project]

# File operations
client.create_file(file: File) -> File
client.get_file(file_id: int) -> File
client.update_file(file: File) -> File
client.delete_file(file_id: int) -> bool
client.get_project_files(project_id: str) -> list[File]

# Attribute operations
client.save_ast(file_id: int, ast_data: dict) -> bool
client.get_ast(file_id: int) -> dict
client.save_cst(file_id: int, cst_code: str) -> bool
client.get_cst(file_id: int) -> str
client.save_vectors(file_id: int, vectors: list[dict]) -> bool
client.get_vectors(file_id: int) -> list[dict]

# AST/CST Tree Operations (SQL-like with XPath filters)
client.query_ast(file_id: int, filter: XPathFilter) -> Result[list[ASTNode]]
client.query_cst(file_id: int, filter: XPathFilter) -> Result[list[CSTNode]]
client.modify_ast(file_id: int, filter: XPathFilter, action: TreeAction, nodes: list[ASTNode]) -> Result[ASTTree]
client.modify_cst(file_id: int, filter: XPathFilter, action: TreeAction, nodes: list[CSTNode]) -> Result[CSTTree]
```

### AST/CST Tree Operations

Operations on AST and CST trees follow SQL-like pattern with XPath-like filters:

1. **Filter**: XPath-like selector (using CSTQuery engine)
2. **Action**: Operation type (replace, delete, insert)
3. **Data**: Node or list of nodes (for adding multiple nodes to one target)
4. **Result**: Operation result object with return code, error description, and data

#### XPath Filter Object

Uses existing CSTQuery engine from `code_analysis/cst_query/`:

```python
@dataclass
class XPathFilter:
    """XPath-like filter for AST/CST tree queries."""
    
    selector: str  # CSTQuery selector string (e.g., "function[name='my_func']")
    # Optional additional filters
    node_type: Optional[str] = None
    name: Optional[str] = None
    qualname: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
```

**CSTQuery Selector Syntax**:
- Steps: `TYPE` or `*`
- Combinators: descendant (space), child (`>`)
- Predicates: `[attr=value]`, `[attr!=value]`, `[attr~=value]`, `[attr^=value]`, `[attr$=value]`
- Pseudos: `:first`, `:last`, `:nth(N)`

**Examples**:
- `class[name="MyClass"]` - Find class by name
- `function[name="my_func"] smallstmt[type="Return"]:first` - Find first return in function
- `method[qualname="MyClass.my_method"]` - Find method by qualified name

#### Tree Action Types

```python
class TreeAction(str, Enum):
    """Tree modification action type."""
    
    REPLACE = "replace"      # Replace matched nodes
    DELETE = "delete"        # Delete matched nodes
    INSERT = "insert"        # Insert nodes (before/after target)
```

#### Result Object

All AST/CST operations return a `Result` object:

```python
@dataclass
class Result:
    """Operation result with return code, description, and data."""
    
    code: int  # Return code: 0 = success, non-zero = error
    description: Optional[str] = None  # Error description (required if code != 0)
    data: Optional[Any] = None  # Result data (optional, depends on operation)
```

**Return Code Rules**:

1. **Code = 0 (Success)**:
   - `description`: Optional (may contain success message)
   - `data`: 
     - **Required** if operation goal is data retrieval (e.g., `query_ast`, `query_cst`)
     - **Optional** if operation goal is modification (e.g., `modify_ast`, `modify_cst`)
     - May contain operation metadata (e.g., number of nodes modified)

2. **Code != 0 (Error)**:
   - `description`: **Required** - must contain error message
   - `data`: **Optional** - may contain additional error information:
     - Error details
     - Stack trace (in debug mode)
     - Partial results (if operation partially succeeded)
     - Validation errors

**Example Results**:

```python
# Success with data (query operation)
Result(
    code=0,
    description=None,
    data=[ASTNode(...), ASTNode(...)]
)

# Success without data (modification operation)
Result(
    code=0,
    description="3 nodes replaced successfully",
    data=None
)

# Success with metadata (modification operation)
Result(
    code=0,
    description="Operation completed",
    data={"nodes_modified": 3, "nodes_deleted": 1}
)

# Error with description
Result(
    code=1,
    description="Node not found: node_id='abc123'",
    data=None
)

# Error with additional data
Result(
    code=2,
    description="Validation failed",
    data={
        "errors": [
            {"field": "node_id", "message": "Invalid node ID format"},
            {"field": "code", "message": "Code cannot be empty"}
        ]
    }
)
```

#### AST/CST Node Objects

```python
@dataclass
class ASTNode:
    """AST node representation."""
    
    node_id: str
    type: str  # AST node type
    name: Optional[str] = None
    qualname: Optional[str] = None
    start_line: int = 1
    start_col: int = 0
    end_line: int = 1
    end_col: int = 0
    ast_json: str  # AST tree as JSON string
    # Additional AST-specific fields...

@dataclass
class CSTNode:
    """CST node representation."""
    
    node_id: str
    type: str  # LibCST node type
    kind: str  # Node kind (function, class, method, etc.)
    name: Optional[str] = None
    qualname: Optional[str] = None
    start_line: int = 1
    start_col: int = 0
    end_line: int = 1
    end_col: int = 0
    code: Optional[str] = None  # Node source code
    # Additional CST-specific fields...
```

#### RPC Methods for AST/CST Operations

```python
# Query operations (return data is required)
rpc.query_ast(file_id: int, filter: XPathFilter) -> Result[list[ASTNode]]
rpc.query_cst(file_id: int, filter: XPathFilter) -> Result[list[CSTNode]]

# Modification operations (return data is optional)
rpc.modify_ast(
    file_id: int,
    filter: XPathFilter,
    action: TreeAction,
    nodes: list[ASTNode]  # Single node or multiple nodes for insert
) -> Result[ASTTree]

rpc.modify_cst(
    file_id: int,
    filter: XPathFilter,
    action: TreeAction,
    nodes: list[CSTNode]  # Single node or multiple nodes for insert
) -> Result[CSTTree]
```

**Operation Flow**:

1. **Query**: Find nodes matching XPath filter
   ```python
   filter = XPathFilter(selector="function[name='my_func']")
   result = client.query_cst(file_id=123, filter=filter)
   if result.code == 0:
       nodes = result.data  # List of matching CST nodes
   ```

2. **Modify**: Apply action to matched nodes
   ```python
   # Replace: replace matched nodes with new nodes
   filter = XPathFilter(selector="function[name='old_func']")
   new_node = CSTNode(code="def new_func():\n    pass")
   result = client.modify_cst(
       file_id=123,
       filter=filter,
       action=TreeAction.REPLACE,
       nodes=[new_node]
   )
   
   # Delete: remove matched nodes
   filter = XPathFilter(selector="class[name='OldClass']")
   result = client.modify_cst(
       file_id=123,
       filter=filter,
       action=TreeAction.DELETE,
       nodes=[]  # Empty for delete
   )
   
   # Insert: add nodes before/after target
   filter = XPathFilter(selector="function[name='my_func']")
   new_nodes = [
       CSTNode(code="def helper():\n    pass"),
       CSTNode(code="def another_helper():\n    pass")
   ]
   result = client.modify_cst(
       file_id=123,
       filter=filter,
       action=TreeAction.INSERT,
       nodes=new_nodes,  # Multiple nodes can be inserted
       position="after"  # Insert after matched node
   )
   ```

**Implementation Notes**:

1. **XPath Filter**: Uses existing `code_analysis/cst_query/` engine
2. **Atomic Operations**: All modifications are atomic (all succeed or all fail)
3. **Validation**: Operations are validated before execution
4. **Error Handling**: Detailed error information in `Result.description` and `Result.data`
5. **Batch Operations**: Multiple nodes can be processed in single operation

## Database Objects

### Core Objects

#### 1. Project

**Database Table**: `projects`

**Attributes**:
- `id` (TEXT, PRIMARY KEY): Project identifier (UUID4 from projectid file)
- `root_path` (TEXT, UNIQUE, NOT NULL): Absolute path to project root
- `name` (TEXT): Project directory name
- `comment` (TEXT): Optional project description
- `watch_dir_id` (TEXT, FOREIGN KEY): Watch directory identifier
- `created_at` (REAL): Creation timestamp
- `updated_at` (REAL): Last update timestamp

**Related Objects**:
- Files (one-to-many)
- Datasets (one-to-many)
- AST trees (one-to-many)
- CST trees (one-to-many)
- Code chunks (one-to-many)
- Vector indices (one-to-many)

#### 2. Dataset

**Database Table**: `datasets`

**Attributes**:
- `id` (TEXT, PRIMARY KEY): Dataset identifier (UUID4)
- `project_id` (TEXT, FOREIGN KEY): Project identifier
- `root_path` (TEXT, NOT NULL): Absolute path to dataset root
- `name` (TEXT): Dataset name
- `created_at` (REAL): Creation timestamp
- `updated_at` (REAL): Last update timestamp

**Purpose**: Supports multi-root indexing within a project (e.g., main code + tests)

**Related Objects**:
- Files (one-to-many)

#### 3. File

**Database Table**: `files`

**Attributes**:
- `id` (INTEGER, PRIMARY KEY): File identifier
- `project_id` (TEXT, FOREIGN KEY): Project identifier
- `dataset_id` (TEXT, FOREIGN KEY): Dataset identifier
- `watch_dir_id` (TEXT, FOREIGN KEY): Watch directory identifier
- `path` (TEXT, NOT NULL): Absolute file path
- `relative_path` (TEXT): Relative path from project root (preferred)
- `lines` (INTEGER): Number of lines in file
- `last_modified` (REAL): Last modification timestamp
- `has_docstring` (BOOLEAN): Whether file has docstring
- `deleted` (BOOLEAN, DEFAULT 0): Whether file is deleted
- `original_path` (TEXT): Original path before moving to version_dir
- `version_dir` (TEXT): Version directory path for deleted files
- `created_at` (REAL): Creation timestamp
- `updated_at` (REAL): Last update timestamp

**Unique Constraint**: `(project_id, dataset_id, path)`

**Related Objects**:
- AST trees (one-to-many)
- CST trees (one-to-many)
- Classes (one-to-many)
- Functions (one-to-many)
- Imports (one-to-many)
- Code chunks (one-to-many)
- Issues (one-to-many)
- Usages (one-to-many)

### Attribute Objects

#### 4. AST Tree

**Database Table**: `ast_trees`

**Attributes**:
- `id` (INTEGER, PRIMARY KEY): AST tree identifier
- `file_id` (INTEGER, FOREIGN KEY): File identifier
- `project_id` (TEXT, FOREIGN KEY): Project identifier
- `ast_json` (TEXT, NOT NULL): AST tree as JSON string
- `ast_hash` (TEXT, NOT NULL): Hash of AST tree content
- `file_mtime` (REAL, NOT NULL): File modification time when AST was created
- `created_at` (REAL): Creation timestamp
- `updated_at` (REAL): Last update timestamp

**Unique Constraint**: `(file_id, ast_hash)`

**Purpose**: Stores parsed Abstract Syntax Tree of Python files for analysis

#### 5. CST Tree

**Database Table**: `cst_trees`

**Attributes**:
- `id` (INTEGER, PRIMARY KEY): CST tree identifier
- `file_id` (INTEGER, FOREIGN KEY): File identifier
- `project_id` (TEXT, FOREIGN KEY): Project identifier
- `cst_code` (TEXT, NOT NULL): CST tree as source code string
- `cst_hash` (TEXT, NOT NULL): Hash of CST tree content
- `file_mtime` (REAL, NOT NULL): File modification time when CST was created
- `created_at` (REAL): Creation timestamp
- `updated_at` (REAL): Last update timestamp

**Unique Constraint**: `(file_id, cst_hash)`

**Purpose**: Stores Concrete Syntax Tree (source code) for editing and refactoring

#### 6. Code Chunks

**Database Table**: `code_chunks`

**Attributes**:
- `id` (INTEGER, PRIMARY KEY): Chunk identifier
- `file_id` (INTEGER, FOREIGN KEY): File identifier
- `project_id` (TEXT, FOREIGN KEY): Project identifier
- `chunk_uuid` (TEXT, NOT NULL, UNIQUE): Unique chunk identifier (UUID4)
- `chunk_type` (TEXT, NOT NULL): Type of chunk (docstring, class, function, etc.)
- `chunk_text` (TEXT, NOT NULL): Chunk text content
- `chunk_ordinal` (INTEGER): Chunk order in file
- `vector_id` (INTEGER): Vector identifier in FAISS index
- `embedding_model` (TEXT): Embedding model used
- `bm25_score` (REAL): BM25 relevance score
- `embedding_vector` (TEXT): Embedding vector as JSON
- `class_id` (INTEGER, FOREIGN KEY): Associated class (if applicable)
- `function_id` (INTEGER, FOREIGN KEY): Associated function (if applicable)
- `method_id` (INTEGER, FOREIGN KEY): Associated method (if applicable)
- `line` (INTEGER): Line number in file
- `ast_node_type` (TEXT): AST node type
- `source_type` (TEXT): Source type (docstring, code, etc.)
- `binding_level` (INTEGER, DEFAULT 0): Binding level for context
- `created_at` (REAL): Creation timestamp
- `updated_at` (REAL): Last update timestamp

**Purpose**: Stores code chunks for vectorization and semantic search

#### 7. Vector Index

**Database Table**: `vector_index`

**Attributes**:
- `id` (INTEGER, PRIMARY KEY): Vector index identifier
- `project_id` (TEXT, FOREIGN KEY): Project identifier
- `entity_type` (TEXT, NOT NULL): Entity type (file, chunk, class, function, method)
- `entity_id` (INTEGER, NOT NULL): Entity identifier
- `vector_id` (INTEGER, NOT NULL): Vector identifier in FAISS index
- `vector_dim` (INTEGER, NOT NULL): Vector dimension
- `embedding_model` (TEXT): Embedding model used
- `created_at` (REAL): Creation timestamp

**Unique Constraint**: `(project_id, entity_type, entity_id)`

**Purpose**: Maps entities to vectors in FAISS index

### Code Structure Objects

#### 8. Class

**Database Table**: `classes`

**Attributes**:
- `id` (INTEGER, PRIMARY KEY): Class identifier
- `file_id` (INTEGER, FOREIGN KEY): File identifier
- `name` (TEXT, NOT NULL): Class name
- `line` (INTEGER, NOT NULL): Line number where class is defined
- `docstring` (TEXT): Class docstring
- `bases` (TEXT): Base classes as JSON string
- `created_at` (REAL): Creation timestamp

**Unique Constraint**: `(file_id, name, line)`

**Related Objects**:
- Methods (one-to-many)
- Code chunks (one-to-many)

#### 9. Method

**Database Table**: `methods`

**Attributes**:
- `id` (INTEGER, PRIMARY KEY): Method identifier
- `class_id` (INTEGER, FOREIGN KEY): Class identifier
- `name` (TEXT, NOT NULL): Method name
- `line` (INTEGER, NOT NULL): Line number where method is defined
- `args` (TEXT): Method arguments as JSON string
- `docstring` (TEXT): Method docstring
- `is_abstract` (BOOLEAN, DEFAULT 0): Whether method is abstract
- `has_pass` (BOOLEAN, DEFAULT 0): Whether method body is just `pass`
- `has_not_implemented` (BOOLEAN, DEFAULT 0): Whether method raises `NotImplementedError`
- `created_at` (REAL): Creation timestamp

**Unique Constraint**: `(class_id, name, line)`

#### 10. Function

**Database Table**: `functions`

**Attributes**:
- `id` (INTEGER, PRIMARY KEY): Function identifier
- `file_id` (INTEGER, FOREIGN KEY): File identifier
- `name` (TEXT, NOT NULL): Function name
- `line` (INTEGER, NOT NULL): Line number where function is defined
- `args` (TEXT): Function arguments as JSON string
- `docstring` (TEXT): Function docstring
- `created_at` (REAL): Creation timestamp

**Unique Constraint**: `(file_id, name, line)`

#### 11. Import

**Database Table**: `imports`

**Attributes**:
- `id` (INTEGER, PRIMARY KEY): Import identifier
- `file_id` (INTEGER, FOREIGN KEY): File identifier
- `name` (TEXT, NOT NULL): Import name
- `module` (TEXT): Module name
- `import_type` (TEXT, NOT NULL): Import type (import, from_import, etc.)
- `line` (INTEGER, NOT NULL): Line number where import is defined
- `created_at` (REAL): Creation timestamp

### Analysis Objects

#### 12. Issue

**Database Table**: `issues`

**Attributes**:
- `id` (INTEGER, PRIMARY KEY): Issue identifier
- `file_id` (INTEGER, FOREIGN KEY): File identifier (optional)
- `project_id` (TEXT, FOREIGN KEY): Project identifier (optional)
- `class_id` (INTEGER, FOREIGN KEY): Class identifier (optional)
- `function_id` (INTEGER, FOREIGN KEY): Function identifier (optional)
- `method_id` (INTEGER, FOREIGN KEY): Method identifier (optional)
- `issue_type` (TEXT, NOT NULL): Issue type (missing_docstring, long_file, etc.)
- `line` (INTEGER): Line number where issue occurs
- `description` (TEXT): Issue description
- `metadata` (TEXT): Additional metadata as JSON string
- `created_at` (REAL): Creation timestamp

**Purpose**: Stores code quality issues detected during analysis

#### 13. Usage

**Database Table**: `usages`

**Attributes**:
- `id` (INTEGER, PRIMARY KEY): Usage identifier
- `file_id` (INTEGER, FOREIGN KEY): File identifier
- `line` (INTEGER, NOT NULL): Line number where usage occurs
- `usage_type` (TEXT, NOT NULL): Usage type (call, attribute, etc.)
- `target_type` (TEXT, NOT NULL): Target type (class, function, method, variable)
- `target_class` (TEXT): Target class name (if applicable)
- `target_name` (TEXT, NOT NULL): Target name
- `context` (TEXT): Usage context as JSON string
- `created_at` (REAL): Creation timestamp

**Purpose**: Tracks usage of classes, functions, methods, and variables

#### 14. Code Content

**Database Table**: `code_content`

**Attributes**:
- `id` (INTEGER, PRIMARY KEY): Content identifier
- `file_id` (INTEGER, FOREIGN KEY): File identifier
- `entity_type` (TEXT, NOT NULL): Entity type (class, function, method)
- `entity_id` (INTEGER): Entity identifier (class_id, function_id, method_id)
- `entity_name` (TEXT): Entity name
- `content` (TEXT, NOT NULL): Code content
- `docstring` (TEXT): Docstring content
- `created_at` (REAL): Creation timestamp

**Purpose**: Stores code content for full-text search (FTS5)

#### 15. Code Duplicates

**Database Table**: `code_duplicates`

**Attributes**:
- `id` (INTEGER, PRIMARY KEY): Duplicate identifier
- `project_id` (TEXT, FOREIGN KEY): Project identifier
- `duplicate_hash` (TEXT, NOT NULL): Hash of duplicate code
- `similarity` (REAL, NOT NULL): Similarity score (0.0-1.0)
- `created_at` (REAL): Creation timestamp

**Unique Constraint**: `(project_id, duplicate_hash)`

**Related Objects**:
- Duplicate occurrences (one-to-many)

#### 16. Duplicate Occurrence

**Database Table**: `duplicate_occurrences`

**Attributes**:
- `id` (INTEGER, PRIMARY KEY): Occurrence identifier
- `duplicate_id` (INTEGER, FOREIGN KEY): Duplicate identifier
- `file_id` (INTEGER, FOREIGN KEY): File identifier
- `start_line` (INTEGER, NOT NULL): Start line number
- `end_line` (INTEGER, NOT NULL): End line number
- `code_snippet` (TEXT): Code snippet
- `ast_node_id` (INTEGER): AST node identifier
- `created_at` (REAL): Creation timestamp

### Infrastructure Objects

#### 17. Watch Directory

**Database Table**: `watch_dirs`

**Attributes**:
- `id` (TEXT, PRIMARY KEY): Watch directory identifier (UUID4)
- `name` (TEXT): Human-readable name (optional)
- `created_at` (REAL): Creation timestamp
- `updated_at` (REAL): Last update timestamp

**Related Objects**:
- Watch directory paths (one-to-one)
- Projects (one-to-many)
- Files (one-to-many)

#### 18. Watch Directory Path

**Database Table**: `watch_dir_paths`

**Attributes**:
- `watch_dir_id` (TEXT, PRIMARY KEY, FOREIGN KEY): Watch directory identifier
- `absolute_path` (TEXT): Absolute normalized path (can be NULL if not found)
- `created_at` (REAL): Creation timestamp
- `updated_at` (REAL): Last update timestamp

**Purpose**: Maps watch directory identifier to absolute path on disk

### Statistics Objects

#### 19. Vectorization Stats

**Database Table**: `vectorization_stats`

**Attributes**:
- `id` (INTEGER, PRIMARY KEY): Stats identifier
- `cycle_id` (TEXT, UNIQUE): Cycle identifier (UUID4)
- `cycle_start_time` (REAL): Cycle start timestamp
- `cycle_end_time` (REAL): Cycle end timestamp (NULL if active)
- `files_total_at_start` (INTEGER): Total files count at cycle start
- `files_vectorized` (INTEGER): Number of vectorized files
- `last_updated` (REAL): Last update timestamp

**Purpose**: Tracks vectorization worker statistics

#### 20. File Watcher Stats

**Database Table**: `file_watcher_stats`

**Attributes**:
- `id` (INTEGER, PRIMARY KEY): Stats identifier
- `cycle_id` (TEXT, UNIQUE): Cycle identifier (UUID4)
- `cycle_start_time` (REAL): Cycle start timestamp
- `cycle_end_time` (REAL): Cycle end timestamp (NULL if active)
- `files_total_at_start` (INTEGER): Total files count at cycle start
- `files_added` (INTEGER): Number of files added
- `files_processed` (INTEGER): Number of files processed
- `files_skipped` (INTEGER): Number of files skipped
- `files_failed` (INTEGER): Number of files failed
- `files_changed` (INTEGER): Number of files changed
- `files_deleted` (INTEGER): Number of files deleted
- `total_processing_time_seconds` (REAL): Total processing time
- `current_project_id` (TEXT): Current project being processed
- `last_updated` (REAL): Last update timestamp

**Purpose**: Tracks file watcher worker statistics

#### 21. Comprehensive Analysis Results

**Database Table**: `comprehensive_analysis_results`

**Attributes**:
- `id` (INTEGER, PRIMARY KEY): Result identifier
- `file_id` (INTEGER, FOREIGN KEY): File identifier
- `project_id` (TEXT, FOREIGN KEY): Project identifier
- `file_mtime` (REAL, NOT NULL): File modification time
- `results_json` (TEXT, NOT NULL): Analysis results as JSON
- `summary_json` (TEXT, NOT NULL): Summary as JSON
- `created_at` (REAL): Creation timestamp
- `updated_at` (REAL): Last update timestamp

**Unique Constraint**: `(file_id, file_mtime)`

**Purpose**: Stores comprehensive code analysis results

## Package Structure

### New Package: `code_analysis.core.database_client`

```
code_analysis/core/database_client/
├── __init__.py
├── client.py              # Main client class
├── rpc_client.py          # RPC client implementation
├── objects/
│   ├── __init__.py
│   ├── project.py         # Project object
│   ├── file.py            # File object
│   ├── dataset.py         # Dataset object
│   ├── attributes.py      # AST, CST, vectors
│   ├── code_structure.py  # Classes, functions, methods
│   └── analysis.py        # Issues, usages, duplicates
└── exceptions.py          # Client-specific exceptions
```

### New Package: `code_analysis.core.database_driver_pkg`

```
code_analysis/core/database_driver_pkg/
├── __init__.py
├── runner.py              # Driver process entry point
├── rpc_server.py          # RPC server implementation
├── drivers/
│   ├── __init__.py
│   ├── base.py            # Base driver interface
│   ├── sqlite.py           # SQLite driver
│   ├── postgres.py         # PostgreSQL driver (future)
│   └── mysql.py            # MySQL driver (future)
└── exceptions.py          # Driver-specific exceptions
```

### Modified Package: `code_analysis.core.worker_manager`

Add method to manage database driver:

```python
class WorkerManager:
    def start_database_driver(
        self,
        driver_type: str,
        driver_config: dict,
        worker_log_path: Optional[str] = None,
    ) -> WorkerStartResult:
        """Start database driver process."""
        ...
```

## Implementation Plan

**⚠️ IMPORTANT**: See `DATABASE_DRIVER_RPC_REFACTORING_PLAN.md` for detailed step-by-step implementation plan with dependencies.

**📁 Detailed Steps**: See `DATABASE_DRIVER_RPC_REFACTORING/` directory for individual step files with checklists.

### Implementation Priorities

1. **🔴 Priority 1**: Query Language Testing and Production Readiness
   - Test and refine CSTQuery language
   - Ensure production readiness before implementing driver

2. **🟠 Priority 2**: Driver Process Implementation
   - Driver works in terms of database tables (not objects)
   - Request queue managed in driver process

3. **🟡 Priority 3**: Client Implementation
   - Object-oriented API on client side
   - Converts objects to table operations

### Phase 1: RPC Infrastructure

1. **Create RPC Server** (`database_driver_pkg/rpc_server.py`)
   - Unix socket or TCP server
   - JSON-RPC 2.0 protocol
   - Request/response handling
   - Error handling and serialization

2. **Create RPC Client** (`database_client/rpc_client.py`)
   - Connect to RPC server
   - Send requests and receive responses
   - Connection pooling
   - Retry logic

3. **Create Driver Runner** (`database_driver_pkg/runner.py`)
   - Process entry point
   - Initialize RPC server
   - Load driver implementation
   - Start server loop

### Phase 2: Driver Process Management

1. **Add to WorkerManager** (`worker_manager.py`)
   - `start_database_driver()` method
   - Process lifecycle management
   - Health checks
   - Restart logic

2. **Update Main Process** (`main.py`)
   - Load driver config from `code_analysis.database.driver`
   - Start driver process before other workers
   - Shutdown driver on exit

### Phase 3: Client Library

1. **Create Object Models** (`database_client/objects/`)
   - Project, File, Dataset classes
   - Attribute classes (AST, CST, Vectors)
   - Code structure classes (Class, Function, Method)
   - Analysis classes (Issue, Usage, Duplicate)

2. **Create Client API** (`database_client/client.py`)
   - Object-oriented methods
   - Convert objects to/from database format
   - Transaction support
   - Batch operations

### Phase 4: Implementation - Commands and Workers

1. **Implement Commands** (`commands/`)
   - Implement all commands using `DatabaseClient`
   - Use new object-oriented API
   - Test all MCP commands

2. **Implement Workers** (`*_worker_pkg/`)
   - Implement workers using `DatabaseClient`
   - Use new object-oriented API
   - Test worker functionality

3. **Remove Old Code** (Cleanup)
   - Remove `CodeDatabase` class completely
   - Remove `SQLiteDriverProxy` completely
   - Remove `DBWorkerManager` completely
   - Remove all old database access code
   - Clean up unused imports and dependencies

### Phase 5: Testing and Documentation

1. **Unit Tests**
   - RPC server/client tests
   - Client library tests
   - Driver tests

2. **Integration Tests**
   - End-to-end workflow tests
   - Worker tests with new client
   - Command tests

3. **Documentation**
   - API documentation
   - Migration guide
   - Configuration guide

## Implementation Strategy

**⚠️ NO MIGRATION - NEW IMPLEMENTATION**

This is a **new project implementation**. Old code is completely removed and replaced with new architecture.

### Implementation Approach

1. **Clean Implementation**: Implement new architecture from scratch
2. **No Old Code**: Remove all old database access code (`CodeDatabase`, `SQLiteDriverProxy`, `DBWorkerManager`)
3. **Direct Replacement**: Commands and workers are implemented directly using new `DatabaseClient`
4. **No Fallbacks**: New architecture is the only implementation - no compatibility layers

### Database Schema

Database schema remains the same. Only the access layer is completely rewritten.

## Benefits

1. **Process Isolation**: Database driver runs in separate process, avoiding daemon issues
2. **Flexibility**: Easy to switch between database backends (SQLite, PostgreSQL, MySQL)
3. **Scalability**: Can run driver on remote server via TCP
4. **Maintainability**: Clear separation between client and driver
5. **Testability**: Easy to mock RPC client for testing
6. **Object-Oriented API**: Cleaner API for workers and commands

## Risks and Mitigation

### Risks

1. **Performance**: RPC adds latency
   - **Mitigation**: Use efficient protocol (MessagePack), connection pooling, batch operations

2. **Complexity**: More moving parts
   - **Mitigation**: Clear documentation, comprehensive tests, clean implementation

3. **Error Handling**: RPC errors need proper handling
   - **Mitigation**: Robust error handling, retry logic, health checks

4. **Implementation Scope**: Large amount of code to implement
   - **Mitigation**: Step-by-step implementation plan, comprehensive testing at each step

## Timeline

- **Phase 1**: 2-3 weeks (RPC infrastructure)
- **Phase 2**: 1 week (Driver process management)
- **Phase 3**: 2-3 weeks (Client library)
- **Phase 4**: 2-3 weeks (Implementation - Commands and Workers)
- **Phase 5**: 1-2 weeks (Testing and documentation)

**Total**: 8-12 weeks

## Success Criteria

1. ✅ Database driver runs in separate process managed by WorkerManager
2. ✅ All database operations go through RPC
3. ✅ Client library provides object-oriented API
4. ✅ AST/CST operations work with XPath filters and Result objects
5. ✅ All existing functionality works with new architecture
6. ✅ Performance is acceptable (within 10% of current performance)
7. ✅ All tests pass
8. ✅ Documentation is complete
