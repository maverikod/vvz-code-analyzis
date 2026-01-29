# rebuild_faiss

**Command name:** `rebuild_faiss`  
**Class:** `RebuildFaissCommand`  
**Source:** `code_analysis/commands/vector_commands/rebuild_faiss.py`  
**Category:** vector

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The rebuild_faiss command rebuilds FAISS (Facebook AI Similarity Search) index from database embeddings. It implements dataset-scoped FAISS, allowing rebuilding indexes for specific datasets or all datasets in a project.

Operation flow:
1. Validates root_dir exists and is a directory
2. Validates project_id matches root_dir/projectid file
3. Opens database connection
4. Verifies project exists in database
5. Loads config.json to get storage paths and vector dimension
6. Initializes SVOClientManager for embeddings
7. If dataset_id provided: rebuilds index for that dataset
8. If dataset_id omitted: rebuilds indexes for all datasets in project
9. For each dataset:
   - Gets dataset-scoped FAISS index path
   - Initializes FaissIndexManager
   - Normalizes vector_id to dense range (0..N-1)
   - Rebuilds FAISS index from database embeddings
   - Closes FAISS manager
10. Returns rebuild statistics

FAISS Index Rebuilding:
- Reads embeddings from code_chunks.embedding_vector in database
- Normalizes vector_id to dense range to avoid ID conflicts
- Creates new FAISS index file from embeddings
- Index is dataset-scoped (one index per dataset)
- Index path: {faiss_dir}/{project_id}/{dataset_id}/index.faiss

Vector ID Normalization:
- Reassigns vector_id to dense range 0..N-1
- Uses single SQL statement to avoid per-row UPDATEs
- Prevents ID conflicts and stabilizes sqlite_proxy worker
- Only processes chunks with valid embeddings

Dataset-Scoped FAISS:
- Each dataset has its own FAISS index file
- Allows independent index management per dataset
- Supports multiple datasets per project
- Indexes are stored in separate directories

Use cases:
- Rebuild index after database changes
- Recover from corrupted index file
- Rebuild index after embedding updates
- Initialize index for new dataset
- Sync index with database state
- Rebuild all indexes after project changes

Important notes:
- Requires valid embeddings in database (use revectorize if missing)
- Rebuilds index from existing embeddings (doesn't generate new ones)
- Index file is recreated (old index is replaced)
- Vector dimension must match config.json setting
- Requires SVOClientManager for missing embeddings (if any)
- project_id must match root_dir/projectid file

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `root_dir` | string | **Yes** | Root directory of the project (contains projectid file) |
| `project_id` | string | **Yes** | Project UUID (must match root_dir/projectid) |
| `dataset_id` | string | No | Optional dataset UUID; if omitted, rebuilds all datasets in project |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `project_id`: Project UUID that was processed
- `datasets_rebuilt`: Number of datasets processed
- `total_vectors`: Total number of vectors in all indexes
- `results`: List of rebuild results. Each contains:
- dataset_id: Dataset UUID
- index_path: Path to FAISS index file
- vectors_count: Number of vectors in index
- root_path: Dataset root path (if all datasets)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, CONFIG_NOT_FOUND, DATASET_ID_MISMATCH, NO_DATASETS, REBUILD_FAISS_ERROR (and others).

---

## Examples

### Correct usage

**Rebuild index for specific dataset**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "project_id": "123e4567-e89b-12d3-a456-426614174000",
  "dataset_id": "223e4567-e89b-12d3-a456-426614174001"
}
```

Rebuilds FAISS index for specific dataset. Useful when only one dataset needs index update.

**Rebuild indexes for all datasets**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "project_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

Rebuilds FAISS indexes for all datasets in the project. Useful after project-wide changes.

### Incorrect usage

- **PROJECT_NOT_FOUND**: Project not found in database. Verify project_id is correct. Ensure project is registered in database. Run update_indexes to register project if needed.

- **CONFIG_NOT_FOUND**: Configuration file not found. Ensure config.json exists in root_dir. Config file is required for storage paths and vector dimension.

- **DATASET_ID_MISMATCH**: Dataset ID mismatch. Verify dataset_id is correct. Dataset ID in database must match provided ID. Use list_projects or database queries to find correct dataset_id.

- **NO_DATASETS**: No datasets found for project. Ensure project has datasets. Run update_indexes to create datasets. Datasets are created automatically when indexing files.

- **REBUILD_FAISS_ERROR**: Error during FAISS index rebuild. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Verify project_id is correct. Ensure project is re |
| `CONFIG_NOT_FOUND` | Configuration file not found | Ensure config.json exists in root_dir. Config file |
| `DATASET_ID_MISMATCH` | Dataset ID mismatch | Verify dataset_id is correct. Dataset ID in databa |
| `NO_DATASETS` | No datasets found for project | Ensure project has datasets. Run update_indexes to |
| `REBUILD_FAISS_ERROR` | Error during FAISS index rebuild |  |

## Best practices

- Run revectorize first if embeddings are missing
- Rebuild index after bulk embedding updates
- Use dataset_id to rebuild specific dataset index
- Rebuild all datasets after project-wide changes
- Verify vectors_count matches expected number of chunks
- Check index_path to verify index file location
- Monitor total_vectors to track index size
- Rebuild index after database repairs or restores

---
