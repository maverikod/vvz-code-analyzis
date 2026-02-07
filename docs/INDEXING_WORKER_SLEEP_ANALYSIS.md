# Indexing worker: when it sleeps and why

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## What the new logs show (after adding logging)

Example from a run with thousands of files (needs_chunking=1):

```
[CYCLE #1] files_total_at_start (needs_chunking=1)=4277
[CYCLE #1] project_ids count=1 (batch_size=5)
[CYCLE #1] project_id=928bcf10 files_batch=5
[CYCLE #1] cycle_had_activity=True sleep_seconds=2
[CYCLE #2] files_total_at_start (needs_chunking=1)=4235
...
[CYCLE #2] cycle_had_activity=True sleep_seconds=2
```

So when there is work:

- **files_total_at_start** is in the thousands (queue of files to index).
- **project_ids count=1** (one project with needs_chunking=1).
- **files_batch=5** (batch_size=5 files per project per cycle).
- **cycle_had_activity=True** (we processed at least one file).
- **sleep_seconds=2** (short sleep between cycles).

Conclusion: with "a sea of files" the indexer does **not** use the long 30s sleep; it uses the 2s sleep and keeps cycling.

---

## When does the indexer sleep 30 seconds?

In `processing.py`:

```python
sleep_seconds = 2 if cycle_had_activity else poll_interval  # poll_interval default 30
```

So **sleep_seconds=30** only when **cycle_had_activity=False**. That happens when:

1. **No projects with work:** `SELECT DISTINCT project_id FROM files WHERE ... needs_chunking = 1` returns no rows → `project_ids` is empty → we never enter the file loop → `cycle_had_activity` stays False.
2. **No files in the batch:** For every project, `SELECT ... LIMIT batch_size` returns 0 rows (e.g. all files with needs_chunking=1 were already cleared by another process, or the query/DB is wrong). Then we again process no file → `cycle_had_activity=False`.

So the indexer sleeps 30s only when there is **no work** in the DB for this cycle (no files with needs_chunking=1, or no rows returned for the batch).

---

## "Sleeping" in get_worker_status

In worker status, **process status "sleeping"** is the **OS process state**: the process is blocked in a system call (e.g. `asyncio.sleep()` or I/O). It does **not** mean "idle for 30 seconds". When the indexer is between cycles and does `await asyncio.sleep(2)`, the process is in state "sleeping" for those 2 seconds. So seeing "sleeping" is normal and does not imply the indexer is idle for a long time.

---

## Why it might have looked like the indexer was "sleeping" with many files

Possible reasons from earlier observations:

1. **Worker had crashed** (e.g. disk full, see INDEXING_WORKER_DISK_FULL_ANALYSIS.md). Then `get_worker_status` showed process_count=0 and no activity — the process was gone, not "sleeping".
2. **Confusion with OS state:** The process state "sleeping" was interpreted as "idle for a long time", while in reality it was in the short 2s sleep between cycles.
3. **Temporary empty queue:** Right after a full scan or a mass update, for a short time needs_chunking might have been 0 (or the query returned empty), so one or more cycles used sleep_seconds=30 until new work appeared.

With the new logging, each cycle shows files_total_at_start, project_ids count, files_batch, cycle_had_activity, and sleep_seconds, so we can see exactly whether the indexer had work and which sleep it chose.
