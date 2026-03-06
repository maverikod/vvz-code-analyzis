# Step 02: Tree Snapshot Schema

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md](../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md)

---

## Role

Senior Python backend/database engineer.

## Target code file

`code_analysis/core/database/base.py`

## Goal

Add base schema definitions for full-file tree snapshots so DB stores complete restorable representation.

## Tasks

1. Add table creation for file-level snapshot storage (full source payload + metadata).
2. Add table creation for full node storage bound to a snapshot.
3. Add table creation for explicit root mapping (single root per snapshot).
4. Add required indexes for file/snapshot/node lookups.
5. Keep schema idempotent and compatible with existing initialization flow.

## Acceptance checks

- Fresh DB init creates all new tables/indexes.
- Existing DB init does not fail.
- Snapshot tables support storing full source text and node rows.

## Blackstops

- Stop if table design cannot enforce file-scope binding for all stored nodes.
- Stop if schema init causes breakage in existing startup path.
