# Vectorization Process Analysis - Docstrings and AST Tree Binding

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Overview

This document analyzes the process of vectorizing docstrings and comments with AST tree binding in the code analysis system. The process involves extracting docstrings/comments from code, chunking them, creating embeddings, and storing them in a vector database with precise AST node binding.

## Architecture Overview

The vectorization process consists of two main phases:

1. **Extraction and Chunking Phase** (during file analysis)
   - Extracts docstrings and comments from AST
   - Chunks text using SVO chunker service
   - Saves chunks to database with AST node binding (without embeddings)

2. **Vectorization Phase** (background worker process)
   - Retrieves non-vectorized chunks from database
   - Gets embeddings from SVO embedding service
   - Adds vectors to FAISS index
   - Updates database with vector_id

## Process Flow

```
File Analysis (CodeAnalyzer.analyze_file)
    ↓
AST Tree Parsing
    ↓
DocstringChunker.process_file()
    ↓
1. Extract docstrings/comments with AST context
    ↓
2. Chunk text via SVO chunker service
    ↓
3. Resolve entity IDs (class_id, function_id, method_id) from database
    ↓
4. Save chunks to database (vector_id = NULL)
    ↓
[Analysis completes]
    ↓
VectorizationWorker.start() (background process)
    ↓
1. Get non-vectorized chunks (WHERE vector_id IS NULL)
    ↓
2. Get embeddings via SVO embedding service
    ↓
3. Add vectors to FAISS index
    ↓
4. Update chunk with vector_id and embedding_model
```

## Detailed Component Analysis

### 1. Docstring Extraction (`DocstringChunker.extract_docstrings_and_comments`)

**Location**: `code_analysis/core/docstring_chunker.py:100-269`

**Process**:
- Extracts file-level docstring using `ast.get_docstring(tree)`
- Recursively visits AST nodes to extract:
  - Class docstrings (`ast.ClassDef`)
  - Function docstrings (`ast.FunctionDef`, `ast.AsyncFunctionDef`)
  - Method docstrings (functions within classes)
  - Comments (inline comments from source code)

**AST Node Binding**:
- Maintains parent context during recursive traversal
- Tracks `parent_class` and `parent_function` for proper context
- Extracts metadata:
  - `ast_node_type`: Type of AST node (ClassDef, FunctionDef, etc.)
  - `entity_type`: "class", "function", "method", "file"
  - `entity_name`: Name of the entity
  - `line`: Line number in source file
  - `class_name`, `function_name`, `method_name`: Context information

**Example Output**:
```python
{
    "type": "docstring",
    "text": "Class description...",
    "line": 25,
    "ast_node_type": "ClassDef",
    "entity_type": "class",
    "entity_name": "MyClass",
    "class_name": "MyClass",
    "function_name": None,
    "method_name": None,
}
```

### 2. Chunking Process (`DocstringChunker.process_file`)

**Location**: `code_analysis/core/docstring_chunker.py:271-400`

**Steps**:

1. **Extract items**: Calls `extract_docstrings_and_comments()` to get all docstrings/comments with AST context

2. **Chunk each item**:
   ```python
   chunks = await self.svo_client_manager.chunk_text(
       text,
       type="DocBlock",  # Documentation block type
   )
   ```
   - Uses SVO chunker service to split text into semantic chunks
   - Returns list of `SemanticChunk` objects

3. **Resolve Entity IDs**:
   - **Class ID**: Queries database `SELECT id FROM classes WHERE file_id = ? AND name = ?`
   - **Method ID**: If within class, queries `SELECT id FROM methods WHERE class_id = ? AND name = ?`
   - **Function ID**: For top-level functions, queries `SELECT id FROM functions WHERE file_id = ? AND name = ?`

4. **Save chunks to database**:
   ```python
   await self.database.add_code_chunk(
       file_id=file_id,
       project_id=project_id,
       chunk_uuid=chunk_uuid,
       chunk_type=chunk_type,  # "DocBlock"
       chunk_text=chunk_text,
       chunk_ordinal=chunk_ordinal,
       vector_id=None,  # Will be set by vectorization worker
       embedding_model=None,  # Will be set by vectorization worker
       class_id=class_id,  # AST binding
       function_id=function_id,  # AST binding
       method_id=method_id,  # AST binding
       line=line,  # AST binding
       ast_node_type=ast_node_type,  # AST binding
       source_type=source_type,  # 'docstring', 'comment', 'file_docstring'
   )
   ```

**Key Points**:
- Chunks are saved **without embeddings** (vector_id = NULL)
- All AST binding information is stored at this stage
- Vectorization happens later in background worker

### 3. Database Schema for Chunks

**Table**: `code_chunks`

**Key Fields for AST Binding**:
- `class_id`: Links chunk to class (if from class docstring)
- `function_id`: Links chunk to function (if from function docstring)
- `method_id`: Links chunk to method (if from method docstring)
- `line`: Line number in source file
- `ast_node_type`: Type of AST node (ClassDef, FunctionDef, etc.)
- `source_type`: 'docstring', 'comment', 'file_docstring'
- `vector_id`: FAISS index ID (NULL until vectorized)
- `embedding_model`: Model used for embedding (NULL until vectorized)

**Index**: `idx_code_chunks_not_vectorized` on `(project_id, vector_id)` WHERE `vector_id IS NULL`

### 4. Vectorization Worker Startup

**Location**: `code_analysis/commands/analyze.py:225-284`

**Trigger**: After analysis completes, if `svo_client_manager` and `faiss_manager` are available

**Process**:
```python
def _start_vectorization_worker(self) -> None:
    # Get configuration
    svo_config = ...  # From adapter config
    
    # Get FAISS settings
    faiss_index_path = ...
    vector_dim = ...
    
    # Start worker in separate process
    process = multiprocessing.Process(
        target=run_vectorization_worker,
        args=(
            str(self.database.db_path),
            self.project_id,
            faiss_index_path,
            vector_dim,
        ),
        kwargs={
            "svo_config": svo_config,
            "batch_size": 10,
        },
    )
    process.daemon = True
    process.start()
```

**Key Points**:
- Runs in **separate process** (multiprocessing)
- Daemon process (killed when parent exits)
- Initializes fresh SVOClientManager and FaissIndexManager in worker process

### 5. Vectorization Worker Process

**Location**: `code_analysis/core/vectorization_worker.py`

**Main Loop** (`VectorizationWorker.process_chunks`):

1. **Get non-vectorized chunks**:
   ```python
   chunks = await database.get_non_vectorized_chunks(
       project_id=self.project_id,
       limit=self.batch_size,  # Default: 10
   )
   ```
   - Query: `SELECT * FROM code_chunks WHERE vector_id IS NULL AND project_id = ? ORDER BY id LIMIT ?`
   - Uses index `idx_code_chunks_not_vectorized` for fast lookup

2. **For each chunk**:
   - Create dummy chunk object for embedding API
   - Get embedding:
     ```python
     chunks_with_emb = await self.svo_client_manager.get_embeddings([dummy_chunk])
     embedding = chunks_with_emb[0].embedding
     embedding_model = chunks_with_emb[0].embedding_model
     ```
   - Convert to numpy array: `np.array(embedding, dtype="float32")`
   - Add to FAISS index: `vector_id = self.faiss_manager.add_vector(embedding_array)`
   - Update database:
     ```python
     await database.update_chunk_vector_id(
         chunk_id, vector_id, embedding_model
     )
     ```

3. **Save FAISS index** after each batch: `self.faiss_manager.save_index()`

**Database Update** (`CodeDatabase.update_chunk_vector_id`):
```sql
UPDATE code_chunks
SET vector_id = ?, embedding_model = ?
WHERE id = ?
```
- After update, chunk is automatically excluded from `get_non_vectorized_chunks` query
- Index `idx_code_chunks_not_vectorized` only includes rows where `vector_id IS NULL`

## AST Tree Binding Details

### Binding Information Stored

For each chunk, the following AST binding information is stored:

1. **Entity IDs** (foreign keys):
   - `class_id`: Links to `classes` table
   - `function_id`: Links to `functions` table
   - `method_id`: Links to `methods` table

2. **Position Information**:
   - `line`: Line number in source file
   - `ast_node_type`: Type of AST node (ClassDef, FunctionDef, Module, etc.)

3. **Source Type**:
   - `source_type`: 'docstring', 'comment', 'file_docstring'

4. **File Context**:
   - `file_id`: Links to `files` table

### Entity ID Resolution

**Location**: `code_analysis/core/docstring_chunker.py:323-360`

The system resolves entity IDs by querying the database using names extracted from AST:

1. **Class ID Resolution**:
   ```python
   if item.get("class_name"):
       cursor.execute(
           "SELECT id FROM classes WHERE file_id = ? AND name = ?",
           (file_id, item["class_name"]),
       )
   ```

2. **Method ID Resolution** (if within class):
   ```python
   if item.get("method_name"):
       cursor.execute(
           "SELECT id FROM methods WHERE class_id = ? AND name = ?",
           (class_id, item["method_name"]),
       )
   ```

3. **Function ID Resolution** (top-level functions):
   ```python
   if item.get("function_name") and not method_id:
       cursor.execute(
           "SELECT id FROM functions WHERE file_id = ? AND name = ?",
           (file_id, item["function_name"]),
       )
   ```

## Integration Points

### 1. CodeAnalyzer Integration

**Location**: `code_analysis/core/analyzer.py:161-169`

```python
# Process docstrings and comments: chunk and embed
if self.docstring_chunker and file_id and project_id:
    await self.docstring_chunker.process_file(
        file_path=file_path,
        file_id=file_id,
        project_id=project_id,
        tree=tree,
        file_content=content,
    )
```

**Called during**: File analysis, after AST tree is saved

### 2. AnalyzeCommand Integration

**Location**: `code_analysis/commands/analyze.py:212-217`

```python
# Start vectorization worker in background process if SVO and FAISS are available
if self.analyzer.svo_client_manager and self.analyzer.faiss_manager:
    self._start_vectorization_worker()
```

**Called after**: All files are analyzed

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    File Analysis Phase                       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────┐
        │   CodeAnalyzer.analyze_file()     │
        │   - Parse AST                      │
        │   - Save AST tree                  │
        └───────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────┐
        │   DocstringChunker.process_file() │
        │   - Extract docstrings/comments    │
        │   - Chunk text (SVO chunker)      │
        │   - Resolve entity IDs            │
        └───────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────┐
        │   CodeDatabase.add_code_chunk()    │
        │   - Save chunk with AST binding    │
        │   - vector_id = NULL               │
        └───────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Vectorization Worker Phase                      │
│              (Background Process)                            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────┐
        │   VectorizationWorker.start()     │
        │   - Initialize SVO/FAISS clients  │
        └───────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────┐
        │   get_non_vectorized_chunks()      │
        │   - Query: vector_id IS NULL       │
        └───────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────┐
        │   SVOClientManager.get_embeddings()│
        │   - Get embedding vector           │
        └───────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────┐
        │   FaissIndexManager.add_vector()   │
        │   - Add to FAISS index             │
        │   - Get vector_id                  │
        └───────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────┐
        │   update_chunk_vector_id()         │
        │   - Set vector_id                  │
        │   - Set embedding_model            │
        └───────────────────────────────────┘
```

## Key Design Decisions

### 1. Two-Phase Processing

**Why**: Separates extraction/chunking (fast) from vectorization (slow)

**Benefits**:
- Analysis completes quickly (doesn't wait for embeddings)
- Vectorization happens in background
- Can process multiple files in parallel
- Worker can be restarted independently

### 2. AST Node Binding at Chunking Stage

**Why**: Entity IDs are resolved during chunking, not vectorization

**Benefits**:
- All context information available at extraction time
- Database queries happen once during analysis
- Worker process doesn't need to resolve entity names

### 3. Batch Processing

**Why**: Processes chunks in batches (default: 10)

**Benefits**:
- Reduces memory usage
- Allows progress tracking
- FAISS index saved after each batch (fault tolerance)

### 4. Separate Process for Worker

**Why**: Uses `multiprocessing.Process` instead of async task

**Benefits**:
- Isolated from main process (CUDA compatibility)
- Can run independently
- Doesn't block main server

## Database Schema

### code_chunks Table

```sql
CREATE TABLE code_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    chunk_uuid TEXT UNIQUE NOT NULL,
    chunk_type TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    chunk_ordinal INTEGER,
    vector_id INTEGER,  -- FAISS index ID (NULL until vectorized)
    embedding_model TEXT,  -- Model name (NULL until vectorized)
    class_id INTEGER,  -- AST binding: class
    function_id INTEGER,  -- AST binding: function
    method_id INTEGER,  -- AST binding: method
    line INTEGER,  -- AST binding: line number
    ast_node_type TEXT,  -- AST binding: node type
    source_type TEXT,  -- 'docstring', 'comment', 'file_docstring'
    created_at REAL DEFAULT (julianday('now')),
    updated_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (file_id) REFERENCES files(id),
    FOREIGN KEY (class_id) REFERENCES classes(id),
    FOREIGN KEY (function_id) REFERENCES functions(id),
    FOREIGN KEY (method_id) REFERENCES methods(id)
);

-- Index for fast lookup of non-vectorized chunks
CREATE INDEX idx_code_chunks_not_vectorized 
ON code_chunks(project_id, vector_id) 
WHERE vector_id IS NULL;
```

## Error Handling

### Chunking Errors

**Location**: `code_analysis/core/docstring_chunker.py:395-400`

- Errors during chunking are logged and item is skipped
- Analysis continues for other items
- No partial state saved

### Vectorization Errors

**Location**: `code_analysis/core/vectorization_worker.py:147-153`

- Errors during vectorization are logged
- Chunk is skipped (remains with vector_id = NULL)
- Worker continues processing other chunks
- Statistics tracked: `processed`, `errors`

## Performance Considerations

### Index Usage

- `idx_code_chunks_not_vectorized`: Fast lookup of chunks needing vectorization
- Partial index (WHERE vector_id IS NULL) reduces index size
- After vectorization, chunk automatically excluded from index

### Batch Size

- Default: 10 chunks per batch
- Configurable via `batch_size` parameter
- Balance between memory usage and throughput

### FAISS Index Saving

- Saved after each batch
- Ensures progress is not lost on worker crash
- Trade-off: More frequent I/O vs. fault tolerance

## Future Improvements

1. **Progress Tracking**: Add progress updates for vectorization worker
2. **Retry Logic**: Retry failed embeddings
3. **Parallel Processing**: Process multiple chunks in parallel
4. **Incremental Updates**: Only vectorize new/changed chunks
5. **Worker Monitoring**: Health checks and status reporting

