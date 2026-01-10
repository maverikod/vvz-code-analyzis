# Analysis of Vectorization Statistics Discrepancy

## Problem

Two commands report different vectorization statistics:
- `get_database_status`: reports 9 total chunks, 2 vectorized (22.22%)
- `check_vectors`: reports 12 total chunks, 0 vectorized (0.0%)

## Root Cause Analysis

### Schema of `code_chunks` Table

The `code_chunks` table has two different fields related to vectorization:

1. **`vector_id`** (INTEGER): FAISS index ID. Set when chunk is added to FAISS index.
2. **`embedding_vector`** (TEXT): JSON string containing the embedding vector itself.

### Different SQL Queries

#### `get_database_status` (DatabaseStatusCommand)

**Location**: `code_analysis/commands/worker_status.py:422-423`

```python
vectorized_chunks_row = db._fetchone(
    "SELECT COUNT(*) as count FROM code_chunks WHERE embedding_vector IS NOT NULL"
)
```

**Logic**: Counts chunks that have an `embedding_vector` stored in the database.

#### `check_vectors` (CheckVectorsCommand)

**Location**: `code_analysis/commands/check_vectors_command.py:462-468`

```python
chunks_with_vector_row = db._fetchone(
    "SELECT COUNT(*) as count FROM code_chunks WHERE vector_id IS NOT NULL AND project_id = ?",
    (proj_id,),
)
```

**Logic**: Counts chunks that have a `vector_id` (i.e., are indexed in FAISS).

### Why the Difference?

1. **Different criteria**: 
   - `embedding_vector IS NOT NULL` means the vector data is stored in the database
   - `vector_id IS NOT NULL` means the chunk is indexed in FAISS

2. **Different semantics**:
   - A chunk can have `embedding_vector` but not `vector_id` (vector computed but not yet indexed)
   - A chunk can have `vector_id` but not `embedding_vector` (indexed but vector not stored in DB)
   - Ideally, both should be set when fully vectorized

3. **Total chunks difference**:
   - `get_database_status`: counts all chunks (no project filter)
   - `check_vectors`: counts all chunks when `project_id` is not provided, but may have different counting logic

## Recommendations

### Option 1: Use `vector_id` as Primary Indicator (Recommended)

**Rationale**: `vector_id` indicates that the chunk is actually indexed in FAISS and ready for semantic search. This is the most important metric for vectorization status.

**Action**: Update `get_database_status` to use `vector_id IS NOT NULL` instead of `embedding_vector IS NOT NULL`.

### Option 2: Use Both Fields

**Rationale**: Check both fields to get a complete picture:
- `vector_id IS NOT NULL`: indexed in FAISS
- `embedding_vector IS NOT NULL`: vector stored in database

**Action**: Report both metrics separately.

### Option 3: Standardize on `vector_id`

**Rationale**: `vector_id` is the authoritative indicator of vectorization completion.

**Action**: 
1. Update `get_database_status` to use `vector_id`
2. Ensure both commands use the same logic
3. Document that `vector_id` is the primary metric

## Actual Database State (Verified via SQLite CLI)

**Direct SQL query results:**
```sql
SELECT COUNT(*) as total, 
       COUNT(CASE WHEN vector_id IS NOT NULL THEN 1 END) as with_vector_id, 
       COUNT(CASE WHEN embedding_vector IS NOT NULL THEN 1 END) as with_embedding_vector 
FROM code_chunks;
```

**Result**: 21 total chunks, 3 with `vector_id`, 3 with `embedding_vector`

**Chunks by project:**
- `453abe18-6b15-4897-b7f8-675f34136ccc`: 15 chunks
- `63c99a6d-db46-42cc-a777-a8572f760d91`: 5 chunks
- `b08deff6-2c47-49d1-93bf-9fae0b77db30`: 1 chunk

## Why Commands Show Different Numbers

### Possible Causes

1. **Different database paths**: 
   - `get_database_status` uses: `root_dir/data/code_analysis.db` (direct path)
   - `check_vectors` uses: `_open_database()` which may resolve path differently via config

2. **Different database connections**:
   - `get_database_status`: Creates `CodeDatabase` directly with `db_path`
   - `check_vectors`: Uses `_open_database()` which may use different storage resolution

3. **Transaction isolation**:
   - Commands may be reading from different database states if transactions are not committed

4. **Caching or connection pooling**:
   - Different database connections may see different states

## Current Status

- **File Watcher**: Running (PID 312315, uptime 393 seconds)
- **Database**: 1.04 MB, 4 projects, 14 files
- **Actual chunks in DB**: 21 total, 3 with `vector_id`, 3 with `embedding_vector`
- **Command reports**: 
  - `get_database_status`: 9 chunks, 2 vectorized (WRONG)
  - `check_vectors`: 12 chunks, 0 vectorized (WRONG)

## Database Path Resolution

### `get_database_status`
- **Path resolution**: Direct path construction
- **Code**: `db_path = data_dir / "code_analysis.db"` where `data_dir = root_path / "data"`
- **Result**: `root_dir/data/code_analysis.db`

### `check_vectors`
- **Path resolution**: Via `_open_database()` → `resolve_storage_paths()` → config
- **Config**: `code_analysis.db_path = "data/code_analysis.db"` (relative to config dir)
- **Result**: `config_dir/data/code_analysis.db` (where `config_dir` is parent of `config.json`)

**Note**: If `root_dir` is the same as `config_dir`, both should resolve to the same path. However, if they differ, commands may access different databases.

## Next Steps

1. **Standardize on `vector_id`**: Update `get_database_status` to use `vector_id IS NOT NULL` instead of `embedding_vector IS NOT NULL`
2. **Verify database path**: Ensure both commands use the same database path resolution method
3. **Fix total chunks count**: Investigate why commands report different total chunk counts (9 vs 12 vs actual 21)
4. **Test consistency**: Run both commands and verify they report identical statistics
5. **Document the metric**: Clearly document that `vector_id` is the authoritative indicator of vectorization completion

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
