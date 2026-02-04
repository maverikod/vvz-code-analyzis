# Step E.1 — Docs

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Updates

1. **docs/SEARCH_AND_VECTORIZATION_DATA_FLOW.md**  
   State that fulltext (`code_content_fts`) is also updated by the **indexing worker** in the background when files have `needs_chunking = 1`; manual `update_indexes` remains for full project refresh or recovery.

2. **New or existing worker doc**  
   Add a short `docs/INDEXING_WORKER.md` (or section in existing worker doc) with:
   - Purpose
   - How it discovers work (`needs_chunking`)
   - That it runs in a separate process
   - Config (poll_interval, batch_size, log path)
   - How to start/stop via MCP or config
