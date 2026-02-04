# Step A.3 — Optional: clear `needs_chunking` after success

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Decision

Where to set `needs_chunking` to 0:

- **Option 1**: Inside the driver after a successful "index_file".
- **Option 2**: In the worker after a successful RPC.

## Recommendation

Prefer **driver** so that any caller of "index_file" gets consistent state: driver clears `needs_chunking` for that file after successful update.
