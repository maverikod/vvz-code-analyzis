# Step E.2 — Tests

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Unit tests

- Mock `DatabaseClient.index_file`.
- Assert that the indexing worker's processing loop:
  - Calls it for files with `needs_chunking = 1`
  - Respects batch size and project order.

## Integration tests

- With a real DB (or test DB) and a test project:
  1. Set `needs_chunking = 1` for a file.
  2. Run one cycle of the indexing worker (or run worker for a few seconds).
  3. Assert that `code_content_fts` (or code_content) has rows for that file and that `needs_chunking` is 0 for that file.
  4. Optionally assert fulltext_search returns the file.
