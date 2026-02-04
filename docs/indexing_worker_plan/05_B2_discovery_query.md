# Step B.2 — Discovery query (which files to index)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Flag and process

The indexer processes only records that **have the flag set** (need indexing): `needs_chunking = 1`. After a successful index, the driver (or handler) **resets** the flag to `needs_chunking = 0` so the file is not picked again. So: **select** files with `needs_chunking = 1` → **process** → **reset** flag to 0 on success.

Project root is **not** passed as a parameter. The list of watch directories and the list of projects come from the database; project root is `projects.root_path`. The worker and driver use `project_id` and paths from the DB only.

## Query sequence

1. **Projects**: Projects that have at least one non-deleted file with `needs_chunking = 1`.  
   Efficient option: `execute("SELECT DISTINCT project_id FROM files WHERE (deleted = 0 OR deleted IS NULL) AND needs_chunking = 1")`.

2. **Per project**:  
   `SELECT id, path, project_id FROM files WHERE project_id = ? AND (deleted = 0 OR deleted IS NULL) AND needs_chunking = 1 ORDER BY updated_at ASC LIMIT ?`

3. For each file row, call `database.index_file(path, project_id)`. The `path` is the value from `files.path` (absolute). No `root_dir` — the driver gets project root from the DB when needed.

4. Restrict to `.py` if desired (optional).

## Batch size

e.g. 5 files per project per cycle to avoid long cycles; configurable.
