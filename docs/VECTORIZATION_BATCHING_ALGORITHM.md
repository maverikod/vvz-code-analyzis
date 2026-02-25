# Vectorization batching algorithm

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Purpose

Define how the vectorization worker fills a single chunker request (packet) using `batch_size` as the maximum number of texts per packet. Files are packed into one request so that we process file-by-file awareness and can associate chunker results with files when writing back to the database.

## Inputs

- **batch_size** (from config: `code_analysis.worker.batch_size`): maximum number of texts in one request to the chunker.
- Database: `code_chunks` with `vector_id IS NULL` and `(embedding_model IS NULL OR embedding_vector IS NULL)` and not `vectorization_skipped`, joined to `files` by `file_id`.

## Algorithm (one worker pass)

Work within a single worker cycle until all files with non-vectorized chunks are processed in this pass, then the worker proceeds to the next cycle (e.g. next poll interval).

### Step 1: Table of files and non-vectorized counts

Build a table of files that have at least one non-vectorized chunk:

- For each file (in the current project or scope): count of chunks that need vectorization (e.g. `vector_id IS NULL` and `(embedding_model IS NULL OR embedding_vector IS NULL)` and not skipped).
- Result: list of `(file_id, file_path, non_vectorized_count)`.

### Step 2: Sort by non-vectorized count (descending)

Sort this list by `non_vectorized_count` descending. Files with the most non-vectorized chunks are considered first so that large files can be fully or largely consumed in one packet when possible.

### Step 3: Start a packet; take first file; compute free slots

- Initialize current packet: list of items, each item is `(file_id, file_path, list of chunk records or chunk_ids/texts)`.
- Take the first file from the sorted list (largest count).
- Add all its non-vectorized chunks to the packet (up to `batch_size` in total). If the file has more than `batch_size` chunks, add only the first `batch_size` (in deterministic order, e.g. by `cc.id`).
- **Free slots** = `batch_size` − number of texts already in the packet.

### Step 4: Greedily add next file that fits

- From the remaining files (below in the sorted list), choose a file such that its non-vectorized count is **≤ free_slots** and as large as possible (maximize texts added).
- Add that file’s non-vectorized chunks to the packet (all of them, or up to `free_slots` if the file has more than `free_slots`). Update free_slots: `free_slots -= number_of_texts_added`.
- Remove the chosen file from the candidate list (or mark as partially consumed if only some chunks were added).

### Step 5: Repeat until no room or no files

- If `free_slots > 0` and there are still files with non-vectorized chunks that can fit (count ≤ free_slots), repeat step 4.
- Otherwise the packet is complete.

### Step 6: Request to chunker and write-back

- Build the **request**: one flat list of texts in packet order, and a parallel structure that **links each text index to (file_id, chunk_id)** so we know which chunk(s) of which file each response chunk belongs to.
- Send this list to the chunker (one call with up to `batch_size` texts).
- On response: for each returned chunk (by index), associate it with the corresponding `(file_id, chunk_id)` and write embedding (and optionally update/merge chunks) in the database. All blocks in the packet are written in this pass.

### Step 7: Proceed until no files left in this pass

- Remove or update the counts for files that had all their chunks included in the packet (or mark remaining counts for partially filled files).
- If there are still files with non-vectorized chunks, form the next packet: go back to step 2 (re-sort remaining by count) or step 3 (reuse current sorted list and take next “first” file), and repeat steps 3–6.
- When no files have non-vectorized chunks in the current scope, this worker pass is done; the worker then proceeds to the next cycle (e.g. wait for `poll_interval`, then start again from step 1 if needed).

## Summary

| Step | Action |
|------|--------|
| 1 | Build table: file_id, file_path, count of non-vectorized chunks. |
| 2 | Sort by count descending. |
| 3 | Start packet; take first file; add its chunks (up to batch_size); set free_slots = batch_size − added. |
| 4 | From remaining files, add a file with max count ≤ free_slots; update free_slots. |
| 5 | Repeat step 4 while free_slots > 0 and such files exist. |
| 6 | Send packet to chunker; link each text index to (file_id, chunk_id); on response, write results to DB. |
| 7 | Repeat from step 2/3 until no files with non-vectorized chunks; then next worker cycle. |

## Notes

- **batch_size** is the single parameter that defines how many texts fit in one packet; it is used both to cap the packet and to decide “how many files fit” by comparing each file’s non-vectorized count to the remaining free slots.
- Chunks must be sent and received in a stable order so that response index ↔ (file_id, chunk_id) mapping is correct when writing to the database.
- If the chunker returns fewer or more items than sent, the write-back logic must define how to map response to DB (e.g. by index, or by chunk id if the protocol supports it).
