# universal_file_edit — Source Specification

<!-- non-binding -->
Author: Vasiliy Zdanovskiy
Date: 2026-05-16
<!-- /non-binding -->

## 1. Purpose

Replace the existing zoo of file-editing commands with four focused commands
that share a single lifecycle model. The commands are:

- `universal_file_open`
- `universal_file_edit`
- `universal_file_write`
- `universal_file_close`

The existing `universal_file_preview` command is unchanged and remains
registered. All other editing commands are removed from registration.

## 2. Commands removed from registration

The following commands are unregistered (code is not deleted, only
registration is removed from hooks.py):

- `universal_file_save`
- `universal_file_replace`
- `universal_file_read`
- `universal_file_delete`
- `cst_load_file`, `cst_find_node`, `cst_get_node_info`,
  `cst_get_node_by_range`, `cst_modify_tree`, `cst_save_tree`
- `json_load_file`, `json_find_node`, `json_modify_tree`, `json_save_tree`
- `write_project_text_lines`, `replace_file_lines`
- `compose_cst_module`, `query_cst`, `list_cst_blocks`
- `read_project_text_file`

`get_file_lines` remains registered as a fallback for files with syntax
errors that cannot be parsed.

## 3. Draft file model

Every file being edited has on-disk artefacts:

- `<file>` — the original file, not modified until `universal_file_write`
  commits successfully.
- `<file>.draft` — the working copy.
  - For tree formats (Python, JSON, YAML): the serialised tree. Persists
    permanently alongside the original; not deleted on close.
  - For text formats (md, txt, rst, adoc): a byte-for-byte copy of the
    original. Temporary; deleted on close.

A third artefact is used during the write confirmation protocol:

- `<file>.write` — lockfile containing the PID of the server process that
  initiated the write preview. Created by the first call to
  `universal_file_write`. Deleted on successful commit or on
  `universal_file_open`.

## 4. universal_file_open

`universal_file_open` starts an editing session for one file.

Inputs: `project_id`, `file_path`.

Behaviour:

1. Delete `<file>.write` if it exists (stale lockfile from a previous
   session).
2. Delete `<file>.draft` if it exists (stale draft from a previous
   session).
3. Parse the file and write the initial `<file>.draft`.
   - For tree formats: serialise the parsed tree to `<file>.draft`.
   - For text formats: copy `<file>` to `<file>.draft`.
4. If the file has no entry in backup history (`list_backup_versions`
   returns an empty list): create an initial backup (initial commit).
5. Return `session_id` and the list of operations available for this
   file's format.

The session_id is a UUID that identifies this editing session. All
subsequent commands in the session pass `session_id`.

## 5. universal_file_edit

`universal_file_edit` applies a batch of mutation operations to
`<file>.draft`. The original file is not touched.

Inputs: `project_id`, `session_id`, `operations` (list).

### 5.1 Operation types

Three operation types exist for all formats:

- `insert` — insert new content.
- `delete` — remove existing content.
- `replace` — replace existing content with new content.

### 5.2 Addressing

Address space depends on the format:

- Tree formats (Python, JSON, YAML): address is
  `(parent_node_id, position_among_siblings)`. `parent_node_id` is a
  StableIdentifier as returned by `universal_file_open` or
  `universal_file_preview`.
- Text formats (md, txt, rst, adoc): address is
  `(start_line, end_line)` — 1-based inclusive line range.

### 5.3 Batch rules

**Tree formats:**

1. Validate the full batch before applying any operation: no operation may
   address a node that is an ancestor or descendant of another node
   addressed in the same batch. Violation produces error
   `NESTED_BATCH_FORBIDDEN`. Batch is rejected atomically.
2. Operations are applied sequentially in the order received. After each
   operation the tree is written to `<file>.draft`. No reordering is
   performed (tree addresses do not shift between operations).

**Text formats:**

1. Operations are sorted by `start_line` descending before application.
   This ensures that applying a change to a lower line does not shift
   the line numbers of changes above it.
2. Applied sequentially in that sorted order. After all operations
   `<file>.draft` is written once.

### 5.4 Effect

For tree formats: each operation modifies the in-memory tree and
immediately writes `<file>.draft`. The original `<file>` is not touched.

For text formats: all operations are applied to an in-memory buffer;
`<file>.draft` is written once after all operations complete.

On success the command returns the updated draft state.

## 6. universal_file_write

`universal_file_write` is a two-phase command controlled by a lockfile.

Inputs: `project_id`, `session_id`.

### 6.1 First call (lockfile absent or PID mismatch)

1. Generate code from `<file>.draft` (for tree formats: serialise tree
   to source; for text formats: the draft is already source).
2. Compute diff between `<file>` (original) and the generated code.
3. Write `<file>.write` containing the current server process PID.
4. Return the diff to the caller. Nothing is written to `<file>`.

If `<file>.write` exists but its PID does not match the current server
process PID: treat as first call (stale lock from a dead process).
Overwrite `<file>.write` with current PID and return a fresh diff.

### 6.2 Second call (lockfile present, PID matches)

Conditions: `<file>.write` exists AND its PID equals the current server
process PID AND `<file>.write` mtime is newer than `<file>.draft` mtime.

1. Create backup of `<file>` (code) and `<file>.draft` (tree) atomically.
   The backup pair is one entry in backup history.
2. Generate code from `<file>.draft` to a temp file.
3. If generation or write fails: restore `<file>` from the backup just
   created. Return error. `<file>.draft` is left intact.
4. If success: rename temp to `<file>`. Delete `<file>.write`.
5. If git is configured: create a git commit.
6. Return success with the diff.

## 7. universal_file_close

`universal_file_close` ends the editing session.

Inputs: `project_id`, `session_id`.

**Text formats:**

1. Delete `<file>.draft` if it exists.
2. Delete `<file>.write` if it exists.
3. Release session. Return success.

**Tree formats:**

1. `<file>.draft` is never deleted (persists as the permanent tree file).
2. Compute checksum of `<file>.draft` and checksum of `<file>`.
3. Checksums match: leave `<file>.draft` as is. Delete `<file>.write`
   if present. Release session. Return success.
4. Checksums do not match (file changed externally or write not called):
   rebuild `<file>.draft` from `<file>` (re-parse). Do NOT create a
   backup. Delete `<file>.write` if present. Release session.
   Return success with flag `draft_rebuilt: true`.

## 8. Reuse of universal_file_preview handlers

All four new commands reuse the existing handler infrastructure from
`universal_file_preview`:

- `HandlerDispatcher` from `universal_file_preview/dispatcher.py`
- `FileHandler` ABC from `universal_file_preview/base_handler.py`
- `resolve_session` from `universal_file_preview/session.py`
- `Node`, `NodeKind` from `universal_file_preview/models.py`
- All concrete handlers from `universal_file_preview/handlers/`

No new package is created. The four command files import directly from
`universal_file_preview`.

## 9. Session storage

A session is an in-memory record keyed by `session_id` (UUID). It stores:

- `file_path` — project-relative path to the file.
- `draft_path` — absolute path to `<file>.draft`.
- `format` — one of: `tree`, `text`.
- `tree_id` — UUID of the in-memory tree (for tree formats), or None.

Sessions are stored in a module-level registry (dict) in the server
process. Sessions are not persisted across server restarts. On restart
the client must call `universal_file_open` again.

## 10. Error codes

- `SESSION_NOT_FOUND` — session_id unknown.
- `DRAFT_NOT_FOUND` — `<file>.draft` missing when expected.
- `NESTED_BATCH_FORBIDDEN` — batch contains ancestor-descendant pair
  (tree formats only).
- `WRITE_FAILED` — code generation or file write failed; backup restored.
- `UNKNOWN_FORMAT` — file extension not supported.
- `PARSE_ERROR` — file could not be parsed on open.
