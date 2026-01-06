# Vector Storage and Usage Analysis

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

Comprehensive analysis of vector storage architecture, usage patterns,
and issues after dataset-scoped FAISS implementation.

## Executive Summary

This document provides a comprehensive analysis of vector storage and usage in the code analysis system after implementing dataset-scoped FAISS (Step 2 of refactor plan). The analysis identifies critical issues and provides recommendations.

## 1. Vector Storage Architecture

### 1.1 Dual Storage Model

The system uses a **dual storage model** for vectors:

1. **SQLite Database** (`code_chunks.embedding_vector`):
   - **Purpose**: Source of truth for vector values
   - **Format**: JSON string (array of floats)
   - **Location**: `code_chunks` table, `embedding_vector` column (TEXT)
   - **Persistence**: Permanent, survives FAISS index rebuilds

2. **FAISS Index File** (`{faiss_dir}/{project_id}/{dataset_id}.bin`):
   - **Purpose**: Fast nearest-neighbor search
   - **Format**: Binary FAISS index file
   - **Location**: Service state directory (not in watched source directories)
   - **Persistence**: Can be rebuilt from database at any time

### 1.2 Database Schema

**Table**: `code_chunks`

```sql
CREATE TABLE code_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    chunk_uuid TEXT UNIQUE NOT NULL,
    chunk_type TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    chunk_ordinal INTEGER,
    vector_id INTEGER,              -- FAISS index ID (NULL until vectorized)
    embedding_model TEXT,           -- Model name (NULL until vectorized)
    embedding_vector TEXT,          -- JSON array of floats (source of truth)
    class_id INTEGER,               -- AST binding: class
    function_id INTEGER,            -- AST binding: function
    method_id INTEGER,              -- AST binding: method
    line INTEGER,                  -- AST binding: line number
    ast_node_type TEXT,            -- AST binding: node type
    source_type TEXT,              -- 'docstring', 'comment', 'file_docstring'
    binding_level INTEGER DEFAULT 0,
    created_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    FOREIGN KEY (function_id) REFERENCES functions(id) ON DELETE CASCADE,
    FOREIGN KEY (method_id) REFERENCES methods(id) ON DELETE CASCADE,
    UNIQUE(chunk_uuid)
);
```

**Key Fields**:
- `embedding_vector`: JSON string containing vector values (source of truth)
- `vector_id`: FAISS index position (1:1 mapping to FAISS vector IDs)
- `embedding_model`: Model identifier used for embedding generation

**Index**:
```sql
CREATE INDEX idx_code_chunks_not_vectorized 
ON code_chunks(project_id, vector_id) 
WHERE vector_id IS NULL;
```

### 1.3 Dataset-Scoped FAISS Index Structure

**Path Format**: `{faiss_dir}/{project_id}/{dataset_id}.bin`

**Example**:
```
/var/lib/code_analysis/faiss/
  └── 123e4567-e89b-12d3-a456-426614174000/  (project_id)
      ├── 987fcdeb-51a2-43f7-8b9c-123456789abc.bin  (dataset_id)
      └── 456fcdeb-51a2-43f7-8b9c-987654321def.bin  (dataset_id)
```

**Key Points**:
- Each dataset has its own FAISS index file
- Index files are stored in service state directory (not in watched source directories)
- Index can be rebuilt from database at any time
- `vector_id` is dense and unique within each dataset (0..N-1)

## 2. Vector Lifecycle

### 2.1 Creation Flow

```
1. File Analysis (CodeAnalyzer.analyze_file)
   ↓
2. Docstring Extraction (DocstringChunker)
   ↓
3. Chunking via SVO Service
   ↓
4. Save Chunk to Database
   - embedding_vector = NULL
   - vector_id = NULL
   - embedding_model = NULL
   ↓
5. Vectorization Worker (Background Process)
   ↓
6. Get Embedding from SVO Service
   ↓
7. Save Embedding to Database
   - embedding_vector = JSON array
   - embedding_model = model name
   ↓
8. Add Vector to FAISS Index
   - vector_id = FAISS position
   ↓
9. Update Database
   - vector_id = FAISS position
```

### 2.2 Vectorization Worker Process

**Location**: `code_analysis/core/vectorization_worker_pkg/batch_processor.py`

**Process**:
1. **Get non-vectorized chunks**:
   ```python
   chunks = await database.get_non_vectorized_chunks(
       project_id=self.project_id,
       limit=self.batch_size,
   )
   ```
   - Query: `SELECT * FROM code_chunks WHERE embedding_vector IS NOT NULL AND vector_id IS NULL AND project_id = ? ORDER BY id LIMIT ?`
   - Uses index `idx_code_chunks_not_vectorized`

2. **For each chunk**:
   - Get embedding from database (`embedding_vector` column)
   - If missing, request from SVO embedding service
   - Add to FAISS index: `vector_id = faiss_manager.add_vector(embedding_array)`
   - Update database: `UPDATE code_chunks SET vector_id = ? WHERE id = ?`

3. **Save FAISS index** after each batch

### 2.3 FAISS Index Rebuild Flow

**Location**: `code_analysis/core/faiss_manager.py:rebuild_from_database`

**Process**:
1. **Normalize vector_id** (dense range 0..N-1 per dataset):
   ```sql
   WITH ranked AS (
       SELECT id, (ROW_NUMBER() OVER (ORDER BY id) - 1) AS new_vector_id
       FROM code_chunks cc
       INNER JOIN files f ON cc.file_id = f.id
       WHERE cc.project_id = ? AND f.dataset_id = ?
         AND cc.embedding_model IS NOT NULL
         AND cc.embedding_vector IS NOT NULL
   )
   UPDATE code_chunks
   SET vector_id = (SELECT new_vector_id FROM ranked WHERE ranked.id = code_chunks.id)
   WHERE id IN (SELECT id FROM ranked)
   ```

2. **Create fresh FAISS index** (clears all existing vectors)

3. **Load chunks from database** (filtered by project_id and dataset_id)

4. **Add vectors to FAISS index**:
   - Parse `embedding_vector` JSON
   - Add to FAISS with `vector_id` from database
   - If embedding missing, request from SVO service

5. **Save FAISS index** to disk

## 3. Vector Usage Patterns

### 3.1 Semantic Search

**Location**: `code_analysis/commands/semantic_search_mcp.py`

**Process**:
1. **Resolve dataset_id** from `root_dir`:
   ```python
   normalized_root = str(normalize_root_dir(root_dir))
   dataset_id = database.get_dataset_id(actual_project_id, normalized_root)
   ```

2. **Get dataset-scoped FAISS index path**:
   ```python
   index_path = get_faiss_index_path(
       storage_paths.faiss_dir, actual_project_id, dataset_id
   )
   ```

3. **Load FAISS index**:
   ```python
   faiss_manager = FaissIndexManager(
       index_path=str(index_path),
       vector_dim=vector_dim,
   )
   ```

4. **Get query embedding** from SVO service

5. **Search FAISS index**:
   ```python
   distances, vector_ids = faiss_manager.search(query_vec, k=k)
   ```

6. **Filter results by dataset_id** (safety check):
   ```sql
   SELECT c.vector_id, c.chunk_uuid, c.chunk_text, f.path
   FROM code_chunks c
   JOIN files f ON f.id = c.file_id
   WHERE c.project_id = ? 
     AND f.dataset_id = ?
     AND c.vector_id IN (...)
   ```

### 3.2 Vectorization Worker

**Location**: `code_analysis/core/vectorization_worker_pkg/runner.py`

**Current Implementation**:
- Worker is initialized with **single FAISS index path** (legacy mode)
- Worker processes chunks for **entire project** (all datasets)
- **CRITICAL ISSUE**: Worker does NOT filter by dataset_id when getting chunks

**Problem**:
- Worker may add vectors from different datasets to the same FAISS index
- This breaks dataset-scoped FAISS isolation

## 4. Critical Issues Identified

### 4.1 Issue #1: Vectorization Worker Not Dataset-Aware

**Severity**: 🔴 **CRITICAL**

**Problem**:
- `get_non_vectorized_chunks()` does NOT filter by `dataset_id`
- Vectorization worker uses single FAISS index path (not dataset-scoped)
- Worker may add vectors from different datasets to wrong FAISS index

**Current Code**:
```python
# code_analysis/core/vectorization_worker_pkg/batch_processor.py:56
chunks = await database.get_non_vectorized_chunks(
    project_id=self.project_id,
    limit=self.batch_size,
)
```

**Expected Behavior**:
- Worker should process chunks per dataset
- Each dataset should have its own FAISS index
- Worker should filter chunks by `dataset_id`

**Impact**:
- Vectors from different datasets may be mixed in same FAISS index
- Semantic search may return results from wrong dataset
- Dataset isolation is broken

### 4.2 Issue #2: Missing `get_non_vectorized_chunks` Implementation

**Severity**: 🟡 **HIGH**

**Problem**:
- Method `get_non_vectorized_chunks()` is called but not found in codebase
- May be implemented dynamically or via mixin
- No dataset_id filtering in current implementation

**Expected Implementation**:
```python
def get_non_vectorized_chunks(
    self, 
    project_id: str, 
    dataset_id: Optional[str] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    if dataset_id:
        return self._fetchall(
            """
            SELECT cc.*
            FROM code_chunks cc
            INNER JOIN files f ON cc.file_id = f.id
            WHERE cc.project_id = ?
              AND f.dataset_id = ?
              AND cc.embedding_vector IS NOT NULL
              AND cc.vector_id IS NULL
            ORDER BY cc.id
            LIMIT ?
            """,
            (project_id, dataset_id, limit),
        )
    else:
        # Project-scoped (all datasets)
        return self._fetchall(
            """
            SELECT cc.*
            FROM code_chunks cc
            WHERE cc.project_id = ?
              AND cc.embedding_vector IS NOT NULL
              AND cc.vector_id IS NULL
            ORDER BY cc.id
            LIMIT ?
            """,
            (project_id, limit),
        )
```

### 4.3 Issue #3: Vector ID Collision Risk

**Severity**: 🟡 **MEDIUM**

**Problem**:
- `vector_id` is dense within each dataset (0..N-1)
- Different datasets may have chunks with same `vector_id`
- Semantic search filters by `dataset_id` in SQL, but FAISS search doesn't

**Current Protection**:
- Semantic search filters results by `dataset_id` after FAISS search
- This is safe but inefficient (searches all vectors, then filters)

**Better Approach**:
- Use dataset-scoped FAISS index (already implemented)
- Each dataset has separate FAISS index with its own vector_id space

### 4.4 Issue #4: Startup Vectorization Worker

**Severity**: 🟡 **MEDIUM**

**Problem**:
- Startup worker rebuilds FAISS indexes for all datasets (correct)
- But vectorization worker still uses single FAISS index path (incorrect)

**Current Code** (`code_analysis/main.py:730-810`):
- Startup correctly rebuilds dataset-scoped indexes
- But worker initialization uses legacy single index path

**Expected Behavior**:
- Worker should be initialized per dataset
- Each dataset should have its own worker instance
- Or worker should process datasets sequentially

## 5. Data Flow Diagrams

### 5.1 Vector Creation Flow

```
┌─────────────────┐
│ File Analysis   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Docstring       │
│ Extraction      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Chunking        │
│ (SVO Service)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Save to DB      │
│ - embedding_vector = NULL
│ - vector_id = NULL
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Vectorization   │
│ Worker          │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Get Embedding   │
│ (SVO Service)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Save Embedding  │
│ to DB           │
│ - embedding_vector = JSON
│ - embedding_model = name
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Add to FAISS    │
│ - vector_id = position
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Update DB       │
│ - vector_id = position
└─────────────────┘
```

### 5.2 Semantic Search Flow

```
┌─────────────────┐
│ Query Text      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Get Query       │
│ Embedding       │
│ (SVO Service)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Resolve         │
│ dataset_id      │
│ from root_dir   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Load Dataset-   │
│ Scoped FAISS    │
│ Index           │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Search FAISS    │
│ - distances     │
│ - vector_ids    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Filter by       │
│ dataset_id      │
│ (SQL JOIN)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Return Results  │
└─────────────────┘
```

## 6. Recommendations

### 6.1 Immediate Actions (Critical)

1. **Fix Vectorization Worker**:
   - Add `dataset_id` parameter to `get_non_vectorized_chunks()`
   - Initialize worker per dataset (or process datasets sequentially)
   - Use dataset-scoped FAISS index path

2. **Implement `get_non_vectorized_chunks` with Dataset Filtering**:
   - Add method to `CodeDatabase` class
   - Filter by `dataset_id` via JOIN with `files` table
   - Support both dataset-scoped and project-scoped modes

3. **Update Worker Initialization**:
   - Initialize worker per dataset
   - Pass dataset-scoped FAISS index path
   - Process chunks for specific dataset only

### 6.2 Short-term Improvements

1. **Add Dataset Validation**:
   - Validate `dataset_id` in all vector operations
   - Ensure chunks belong to correct dataset
   - Add database constraints if needed

2. **Improve Error Handling**:
   - Handle dataset mismatch errors
   - Log dataset information in all vector operations
   - Add metrics for dataset-scoped operations

3. **Documentation**:
   - Document dataset-scoped FAISS architecture
   - Update vectorization worker documentation
   - Add migration guide for existing data

### 6.3 Long-term Enhancements

1. **Worker Architecture**:
   - Consider multi-dataset worker (processes multiple datasets)
   - Add dataset priority/queue system
   - Implement dataset-level metrics

2. **Performance Optimization**:
   - Batch operations per dataset
   - Parallel processing for multiple datasets
   - Cache dataset metadata

3. **Monitoring**:
   - Add dataset-level metrics
   - Track vector counts per dataset
   - Monitor FAISS index sizes

## 7. Migration Path

### 7.1 For Existing Data

1. **Identify Datasets**:
   - Query all datasets for each project
   - Map files to datasets via `files.dataset_id`

2. **Rebuild FAISS Indexes**:
   - Use `rebuild_faiss` command per dataset
   - Verify vector counts match database

3. **Update Workers**:
   - Stop existing workers
   - Initialize new dataset-scoped workers
   - Verify vectorization works correctly

### 7.2 For New Data

1. **Automatic Dataset Creation**:
   - Create dataset on first file indexing
   - Use resolved absolute path as dataset root

2. **Dataset-Scoped Operations**:
   - All vector operations use dataset_id
   - Workers process per dataset
   - FAISS indexes are dataset-scoped

## 8. Testing Checklist

- [ ] Vectorization worker processes chunks per dataset
- [ ] FAISS indexes are isolated per dataset
- [ ] Semantic search returns results from correct dataset
- [ ] Rebuild FAISS works per dataset
- [ ] Revectorize works per dataset
- [ ] Vector IDs are unique within dataset
- [ ] No cross-dataset vector contamination
- [ ] Worker handles multiple datasets correctly
- [ ] Startup rebuilds all dataset indexes
- [ ] Error handling for dataset mismatches

## 9. Conclusion

The dataset-scoped FAISS implementation is **partially complete**. The main issues are:

1. **Vectorization worker is not dataset-aware** (critical)
2. **Missing dataset filtering in chunk queries** (high)
3. **Worker initialization uses legacy single index** (medium)

**Priority**: Fix vectorization worker to be dataset-aware before production use.

**Status**: 🔴 **NOT PRODUCTION READY** - Critical issues must be fixed first.

