# Options for storing worker and database status metrics

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Goal

Persist snapshots of `get_database_status` and `get_worker_status` (or a compact subset) over time so you can:

- See trends (how many files indexed/vectorized per period)
- Diagnose "what happened" when numbers change (e.g. drops in chunk count)
- Compare before/after without keeping manual notes

---

## Option 1: Table in the main database

**Idea:** New table `status_snapshots` (or `metrics_snapshots`) in `code_analysis.db`. Each row = one snapshot at a timestamp.

**Schema (compact, one row per snapshot):**

```sql
CREATE TABLE status_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,           -- ISO timestamp
    -- DB aggregates
    files_total INTEGER,
    files_indexed INTEGER,
    files_indexed_percent REAL,
    files_chunked_percent REAL,
    chunks_total INTEGER,
    chunks_vectorized INTEGER,
    chunks_vectorization_percent REAL,
    db_size_mb REAL,
    files_updated_24h INTEGER,
    chunks_updated_24h INTEGER,
    -- Workers (optional; can be NULL if worker unreachable)
    file_watcher_pid INTEGER,
    file_watcher_operation TEXT,
    file_watcher_progress_percent REAL,
    vectorization_pid INTEGER,
    vectorization_operation TEXT,
    indexing_pid INTEGER,
    indexing_operation TEXT,
    indexing_progress_percent REAL,
    -- Optional: full JSON for drill-down (can be large)
    payload_json TEXT
);
CREATE INDEX idx_status_snapshots_recorded_at ON status_snapshots(recorded_at);
```

**Who writes:** Either:

- A scheduled call (cron/systemd timer) that runs `get_database_status` + `get_worker_status` via MCP/CLI and inserts a row, or
- The server itself: after returning `get_database_status`, optionally call an internal "append snapshot" that inserts into this table (e.g. with rate limit: at most one row per N minutes).

**Pros:** Single place; SQL queries (e.g. "snapshots in last 24h", "delta files_indexed between two times"); integrates with existing DB backups.  
**Cons:** Grows main DB; need migrations; if DB is locked/corrupt, snapshot write can fail.

---

## Option 2: Append-only JSONL file

**Idea:** One file, e.g. `data/status_metrics.jsonl` or `logs/status_snapshots.jsonl`. Each line = one JSON object (one snapshot). No DB schema change.

**Format (example):**

```json
{"ts":"2026-02-06T11:00:00","files_total":12822,"files_indexed":3124,"chunks_total":167,"chunks_vectorized":90,"fw_pid":1248916,"fw_op":"scanning","vec_pid":1248906,"vec_op":"polling","idx_pid":1248900,"idx_op":"indexing","idx_file":"vast_srv/test_ftp_commands.py"}
```

**Who writes:** Same as option 1: external scheduler calling status commands and appending one line, or server-side hook with rate limit.

**Pros:** Simple; no schema; easy to rotate/archive (mv + gzip); parse with `jq`, pandas, or custom script; works even if main DB is read-only or busy.  
**Cons:** No SQL; ad-hoc queries need a script or tool; file can get large (mitigate with rotation by day/week).

---

## Option 3: CSV file (flat table)

**Idea:** Same as JSONL but CSV: one header row, then one row per snapshot. E.g. `data/status_snapshots.csv`.

**Pros:** Opens in Excel/Sheets; trivial to diff and plot.  
**Cons:** Nested or variable-length data (e.g. per-project stats) don’t fit well; escaping; less flexible than JSON.

**Verdict:** Use CSV only if you strictly want a single flat row per snapshot and no nested structure.

---

## Option 4: Dedicated metrics database

**Idea:** Separate SQLite file, e.g. `data/code_analysis_metrics.db`, with the same `status_snapshots` table as in option 1.

**Pros:** Main DB size unchanged; metrics can be retained longer or with different backup policy.  
**Cons:** Two DBs to maintain and back up; need to open second DB when writing snapshots.

---

## Option 5: Hybrid (recommended)

- **Primary:** Append-only **JSONL** in `data/status_snapshots.jsonl` (or under `logs/` if you prefer logs dir). Minimal code: one function that builds a compact dict from current `get_database_status` + `get_worker_status` and appends one line. No migrations, no impact on main DB.
- **Optional:** A small script or command (e.g. "export last N snapshots to CSV") for analysis; or periodic import of JSONL into a table (same or separate DB) for SQL if you need it later.

**Minimal payload to store per snapshot (recommended fields):**

- `ts` (ISO)
- `files_total`, `files_indexed`, `files_indexed_percent`, `chunks_total`, `chunks_vectorized`, `chunks_vectorization_percent`
- `files_updated_24h`, `chunks_updated_24h` (from `recent_activity`)
- Per worker (if available): `file_watcher.pid`, `file_watcher.operation`, `file_watcher.progress_percent`; same for `vectorization` and `indexing`; optionally `indexing.current_file`
- Optionally `db_size_mb` and one line per project (e.g. `projects: [{ "name", "file_count", "files_indexed", "chunk_count", "vectorized_chunks" }]`) for project-level trends

---

## Summary

| Option            | Storage        | Query style | Complexity | Best for                    |
|-------------------|----------------|------------|------------|-----------------------------|
| 1. Table in DB    | code_analysis.db | SQL        | Medium     | Tight integration, SQL     |
| 2. JSONL file     | data/ or logs/ | jq/script  | Low        | Simple, safe, no schema     |
| 3. CSV file       | data/ or logs/ | Excel/script | Low     | Flat, human-friendly        |
| 4. Separate DB     | metrics.db     | SQL        | Medium     | Isolate metrics from main DB |
| 5. Hybrid (JSONL + optional export) | data/ + optional DB | Both | Low then medium | Recommended: start with JSONL |

**Recommendation:** Start with **Option 5 (JSONL)**. Add a writer that runs on a timer (or after each status call with rate limit), then add SQL/CSV export later if you need it.
