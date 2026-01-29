# Miscellaneous Commands — Detailed Descriptions

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Some commands are optional (registered with try/except in hooks). Schema from `get_schema()`; metadata from `metadata()` where available.

---

## check_vectors — CheckVectorsCommand

**File:** `commands/check_vectors_command.py`

**Description:** Check vector statistics in database: total chunks, vectorized count, pending, vectorization percentage, sample chunks. Useful for monitoring vectorization progress and diagnosing issues.

**Behavior:** Queries chunks table for counts (total, with vector_id, with embedding_model, pending); returns summary and optional sample rows.

---

## analyze_project — AnalyzeProjectCommand

**File:** `commands/analyze_project_command` (optional)

**Description:** Run full project analysis (if implemented). May trigger indexing, complexity, or comprehensive analysis.

---

## analyze_file — AnalyzeFileCommand

**File:** `commands/analyze_file_command` (optional)

**Description:** Run analysis on a single file (if implemented).

---

## help — HelpCommand

**File:** `commands/help_command` (optional)

**Description:** Return server or command help (if implemented).

---

## add_watch_dir — AddWatchDirCommand

**File:** `commands/watch_dirs_commands` (optional)

**Description:** Register a directory to be watched for file changes.

---

## remove_watch_dir — RemoveWatchDirCommand

**File:** `commands/watch_dirs_commands` (optional)

**Description:** Unregister a watch directory.
