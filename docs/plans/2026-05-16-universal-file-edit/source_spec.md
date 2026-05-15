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

Every file being edited has two on-disk artefacts:

- `<file>` — the original file, not modified until `universal_file_write`
  confirms successfully.
- `<file>.draft` — the working copy. For tree-structured formats (Python,
  JSON, YAML) this is the serialised tree. For text formats (md, txt, rst,
  adoc) this is a byte-for-byte copy of the original.

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

### 5.3 Batch validation

Before applying any operation, the full batch is validated:

1. For tree formats: no operation in the batch may address a node that is
   an ancestor or descendant of another node addressed in the same batch.
   Violation produces error `NESTED_BATCH_FORBIDDEN`.
2. For all formats: operations are sorted and applied bottom-up:
   - Text: descending by `start_line`.
   - Tree: descending by node depth (deepest nodes first).
   This guarantees that earlier operations do not shift the addresses
   of later ones.

If validation fails the batch is rejected atomically — no operations are
applied.

### 5.4 Effect

Each operation modifies `<file>.draft` on disk. The original `<file>` is
not touched. After all operations are applied successfully the command
returns the updated draft state (list of top-level nodes or line count).

## 6. universal_file_write

`universal_file_write` is a two-phase command controlled by a lockfile.

Inputs: `project_id`, `session_id`.

### 6.1 First call (lockfile absent)

1. Generate code from `<file>.draft` (for tree formats: serialise tree
   to source; for text formats: the draft is already source).
2. Compute diff between `<file>` (original) and the generated code.
3. Write `<file>.write` containing the current server process PID.
4. Return the diff to the caller. Nothing is written to `<file>`.

### 6.2 Second call (lockfile present, PID matches)

Conditions: `<file>.write` exists AND its PID equals the current server
process PID AND `<file>.write` mtime is newer than `<file>.draft` mtime.

1. Create backup of `<file>` (code) and `<file>.draft` (tree) atomically.
   The backup pair is one entry in backup history.
2. Write generated code to `<file>` (rename from temp).
3. Delete `<file>.write`.
4. If git is configured: create a git commit.
5. Return success.

### 6.3 Lockfile PID mismatch

If `<file>.write` exists but its PID does not match the current server
process PID: treat as a first call (stale lock from a dead process).
Overwrite `<file>.write` with current PID and return a fresh diff.

### 6.4 Write failure

If writing `<file>` fails after backup was created: restore `<file>` from
the backup just created. Return error. `<file>.draft` is left intact so
the session can retry.

## 7. universal_file_close

`universal_file_close` ends the editing session.

Inputs: `project_id`, `session_id`.

Behaviour:

1. If `<file>.draft` does not exist: session is already clean, return
   success.
2. Compute checksum of the tree represented by `<file>.draft` and the
   checksum of `<file>` on disk.
3. If checksums match: delete `<file>.draft`, delete `<file>.write` if
   present, release session. Return success.
4. If checksums do not match: the file on disk is newer or different
   (e.g. written externally or write was not called). Rebuild
   `<file>.draft` from `<file>` (re-parse). Do NOT create a backup.
   Delete `<file>.write` if present. Release session. Return success
   with flag `draft_rebuilt: true`.

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
- `format` — one of: `python`, `json`, `yaml`, `text`.
- `tree_id` — UUID of the in-memory tree (for tree formats), or None.

Sessions are stored in a module-level registry (dict) in the server
process. Sessions are not persisted across server restarts. On restart
the client must call `universal_file_open` again.

## 10. Error codes

- `SESSION_NOT_FOUND` — session_id unknown.
- `DRAFT_NOT_FOUND` — `<file>.draft` missing when expected.
- `NESTED_BATCH_FORBIDDEN` — batch contains ancestor-descendant pair.
- `LOCK_CONFLICT` — reserved (not used; PID mismatch is handled silently).
- `WRITE_FAILED` — code generation or file write failed; backup restored.
- `UNKNOWN_FORMAT` — file extension not supported.
- `PARSE_ERROR` — file could not be parsed on open.
