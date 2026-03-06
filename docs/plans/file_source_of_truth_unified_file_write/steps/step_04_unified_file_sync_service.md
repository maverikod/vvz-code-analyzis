# Step 04: Unified File-Level Sync Service

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md](../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md)

---

## Role

Senior Python architecture and persistence engineer.

## Target code file

`code_analysis/core/database/file_tree_sync.py`

## Goal

Implement a single reusable file-level pipeline that writes full tree snapshot and node data to DB.

## Tasks

1. Create unified API (e.g. `sync_file_to_db_atomic(...)`).
2. Input contract must be file-centric (project, absolute path, source text, context timestamps).
3. Persist full snapshot payload and full node list for the file.
4. Persist explicit parent-child links and sibling order (`child_index`).
5. Return structured success/error payload.
6. Keep behavior deterministic and reusable by all writer flows.

## Acceptance checks

- Service can write one complete file snapshot and all nodes in one flow.
- Service output is stable and machine-consumable.
- Service contains no flow-specific behavior tied only to one caller.

## Blackstops

- Stop if service cannot represent comments/docstrings/data types with fidelity.
- Stop if service can only support one caller type and not both required flows.
