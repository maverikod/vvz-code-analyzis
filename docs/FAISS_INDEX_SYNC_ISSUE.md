# FAISS Index Synchronization Issue

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Problem Description

Vectors are not being added to FAISS index after vectorization, even though:
- Embeddings are saved to database (`embedding_vector` column)
- `vector_id` is assigned and saved to database
- FAISS index is saved after each batch

## Root Cause Analysis

### Current Situation (Project vast_srv)

- **Total chunks**: 295
- **Chunks with embeddings**: 295 (100%)
- **Chunks with vector_id**: 323 (some duplicates)
- **Unique vector_id range**: 0-167 (168 unique IDs)
- **Vectors in FAISS index**: 155

### The Problem

When FAISS index is loaded from disk, `_next_vector_id` is set to `ntotal` (number of vectors in index):

```python
self._next_vector_id = int(getattr(loaded, "ntotal", 0))
```

However, the database may have `vector_id` values that are higher than `ntotal` because:
1. Vectors were added to index in memory
2. `vector_id` was saved to database
3. Index was saved to disk
4. Worker restarted
5. Index was loaded, but some vectors were lost (not saved properly, or index was corrupted)

### Process Flow

1. **Get chunk** → `get_non_vectorized_chunks()` (chunks with `embedding_vector` but no `vector_id`)
2. **Vectorize** → Get embedding from SVO service or database
3. **Save to DB** → Update `embedding_vector` and `embedding_model` in database
4. **Add to FAISS** → `faiss_manager.add_vector(embedding_array)` → returns `vector_id`
5. **Update DB** → `update_chunk_vector_id(chunk_id, vector_id)` → saves `vector_id` to database
6. **Save index** → `faiss_manager.save_index()` → saves index to disk

### The Issue

When worker restarts:
- Index is loaded with 155 vectors
- `_next_vector_id` is set to 155
- Database has `vector_id` up to 167
- New vectors get `vector_id` starting from 155, but IDs 155-167 are already used in database
- This causes conflicts and missing vectors in index

## Solution

### Option 1: Sync `_next_vector_id` with Database (Recommended)

When loading FAISS index, also check database for maximum `vector_id` and use the maximum:

```python
def _load_index(self: "FaissIndexManager") -> None:
    with self._lock:
        try:
            loaded = faiss.read_index(str(self.index_path))
            if not hasattr(loaded, "add_with_ids"):
                logger.warning("Loaded FAISS index is missing add_with_ids (legacy)...")
            self.index = loaded
            index_ntotal = int(getattr(loaded, "ntotal", 0))
            
            # Sync with database to get actual max vector_id
            # This should be done by the worker, not here (FaissIndexManager doesn't have DB access)
            # So we need to pass max_vector_id from database when initializing FaissIndexManager
            
            self._next_vector_id = index_ntotal
            logger.info(
                "Loaded FAISS index: %s, vectors=%d, dim=%d",
                self.index_path,
                index_ntotal,
                self.vector_dim,
            )
        except Exception as e:
            logger.error(f"Failed to load FAISS index from {self.index_path}: {e}")
            self._create_index()
```

**Better approach**: Pass `max_vector_id` from database when initializing `FaissIndexManager` in worker:

```python
# In vectorization worker runner
max_vector_id = database.get_max_vector_id(project_id, dataset_id)
faiss_manager = FaissIndexManager(
    index_path=faiss_index_path,
    vector_dim=vector_dim,
    initial_vector_id=max_vector_id + 1,  # Start from next available ID
)
```

### Option 2: Rebuild Index from Database

Use `rebuild_faiss` command to rebuild index from database, ensuring all vectors with `vector_id` are in index.

### Option 3: Check for Missing Vectors on Startup

When worker starts, check which `vector_id` values exist in database but not in FAISS index, and add them.

## Immediate Fix

For project vast_srv:
1. Run `rebuild_faiss` command to rebuild index from database
2. This will ensure all 168 vectors (0-167) are in the index

## Long-term Fix

**Implemented**: Automatic synchronization check on worker startup.

### Solution Implemented

1. **Added `check_index_sync()` method** to `FaissIndexManager`:
   - Compares `vector_id` values from database with IDs in FAISS index
   - Detects missing vectors, extra vectors, and count mismatches
   - Returns detailed synchronization status

2. **Automatic check on worker startup** in `run_vectorization_worker()`:
   - After initializing FAISS manager, checks synchronization
   - If any mismatch is found, automatically runs `rebuild_from_database()`
   - Worker continues normally after rebuild

3. **Benefits**:
   - Automatic recovery from index corruption or desynchronization
   - No manual intervention needed
   - Ensures index is always in sync with database on worker startup

### Code Changes

- `code_analysis/core/faiss_manager.py`: Added `check_index_sync()` method
- `code_analysis/core/vectorization_worker_pkg/runner.py`: Added automatic sync check and rebuild on startup

