# Technical specification: Unified CST node ID persistence and batch read-only output handling

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Canonical rules:** Role explicit; internal consistency; completeness; precision; consistency with project rules; 100% ready for handoff; mandatory blackstops; mandatory re-check after implementation.

---

## 1. Role of the executor

**Developer.** Implements only what is specified in this TZ. No scope creep.

---

## 2. Canonical validation metrics

### 2.1 Valid code metrics

- Full compliance with project and user rules.
- No hardcode, placeholders, compatibility/fallback logic unless explicitly required by user/task.
- No incomplete production code:
  - TODO/FIXME.
  - `NotImplemented` outside abstract methods.
  - `pass` outside exception bodies.
- No deviation from task scope.
- Abstract methods must not contain implementation code other than `NotImplemented`, comments, and docstrings.

### 2.2 Valid task metrics

- Explicit model role.
- Internal consistency.
- Completeness.
- Precision.
- Consistency with project rules.
- 100% handoff readiness.
- Mandatory blackstops.
- Mandatory re-check and fixes after implementation.

### 2.3 Valid plan metrics

- Steps split into separate files in a dedicated steps directory.
- **1 step = 1 code file = 1 step description file**.
- Step sequence respects dependencies.
- Each step is self-sufficient via links/context.
- Separate file describes parallel execution chains.

---

## 3. Unified goal

- Persist a stable CST node identifier for entities in database tables: `classes`, `functions`, `methods`.
- Make entity-level analysis responses return `file_path` and `cst_node_id` as primary semantic reference.
- Provide a batch invocation for read-only commands.
- For oversized batch results, write output to file and return metadata for byte-range extraction per command.

---

## 4. Current state (brief)

- Entity tables currently may not have persisted `cst_node_id` for all rows.
- CST node IDs exist in tree metadata and are UUID4 for new nodes.
- `cst_get_node_info` resolves node details by `tree_id` + `node_id`.
- Batch read-only aggregation with mandatory large-output-to-file contract is not a single unified command yet.

---

## 5. Scope and files to modify

- Schema/migration layer for `classes`, `functions`, `methods`.
- Indexing pipeline that writes entities from CST/AST.
- Read-only analysis commands returning entities.
- New or extended batch read-only command/endpoint.
- Config and file-output logic for oversized batch responses.

---

## 6. Required behavior

### 6.1 `cst_node_id` schema and migration path

- Final state: `cst_node_id TEXT NOT NULL` on `classes`, `functions`, `methods`.
- Allowed migration sequence for current single-DB context:
  1. Add `cst_node_id TEXT` as nullable.
  2. Run backfill script to populate existing rows (match by CST node where possible; if unmatched, generate UUID4 with documented policy).
  3. Enforce `NOT NULL`.
  4. Add runtime validation before insert/update: reject empty/invalid UUID4 with explicit error.
- No row may remain NULL after backfill when moving to final state.
- Do not drop/rename existing columns.

### 6.2 Population at index time

- During indexing, map entities (class/function/method) to CST nodes and write `cst_node_id` from tree metadata.
- Keep immutability policy: do not overwrite an existing valid `cst_node_id` for the same logical entity unless entity is removed and recreated.
- Stored value must always be valid UUID4.

### 6.3 Entity response contract

- Every read-only command that returns entities must include:
  - `file_path`
  - `cst_node_id` (valid UUID4, non-empty)
- Line/range fields may remain auxiliary only.
- In-scope command family includes (non-exhaustive): `get_class_hierarchy`, `list_code_entities`, `get_code_entity_info`, `find_dependencies`, `find_usages`, `get_entity_dependencies`, `get_entity_dependents`, `export_graph`, and similar entity-returning analysis commands.

### 6.4 Node retrieval by ID and descendants

- Existing flow: `cst_get_node_info` with `tree_id` + `node_id` and `include_children=True`.
- Future convenience command should support:
  - input: `cst_node_id` (single) or `cst_node_ids` (list/set), `project_id` optional.
  - no required input `file_path`.
  - resolution via DB: `cst_node_id` -> entity row -> file/project.
  - output per requested ID: node, descendants, `file_path`, and file name.
- This enables model workflows to request a full set of IDs from analysis in one call.
- Scope note: this convenience command is out of scope for the current implementation unless explicitly added by a separate task.

### 6.5 Tree manipulation commands must use immutable UUID4 node IDs

- All CST tree manipulation commands (replace/insert/delete/move and similar) must accept **UUID4 node identifiers** as the primary and required reference to target nodes.
- The identifier contract is immutable: command input must rely on `node_id`/`cst_node_id` only, not on line/range as primary selector.
- Any line/range or textual selector can be kept only as optional compatibility helper, but final target resolution must produce a valid UUID4 node ID before write operation.
- Validation must fail fast with explicit error when incoming node identifier is missing, empty, or not valid UUID4.
- This rule is required to keep inserts/replaces/deletes stable under file edits and to avoid positional drift problems.

### 6.6 Batch read-only command safety

- Batch command accepts multiple read-only commands with params in one request.
- Only commands from hardcoded whitelist are allowed.
- No config/client mechanism may dynamically extend whitelist.
- Mutating commands must be rejected.

### 6.7 Large output handling (batch)

- Use configurable response-size limit (bytes).
- If serialized combined result exceeds limit:
  1. Write full combined result to output file in configured directory.
  2. Return metadata response instead of full payload:
     - `output_file` (or `output_path`)
     - `file_size`
     - `results_metadata` with per-command:
       - `command` (or index/id)
       - `size`
       - `offset`
       - `length`
- `offset`/`length` must match exact serialized fragments in file.
- Document cleanup/retention policy for output files.

---

## 7. Blackstops

- Do not allow NULL/empty/invalid UUID4 in persisted or returned `cst_node_id`.
- Do not break existing callers; extend response objects by adding required fields.
- Do not use line numbers as primary identity.
- Do not perform tree mutation by line/range as the primary target reference; mutation path must resolve to UUID4 node IDs.
- Do not allow mutating commands in batch read-only whitelist.
- Do not return oversized payload inline when threshold is exceeded; must return file metadata path.

---

## 8. Acceptance criteria

1. Schema final state is `TEXT NOT NULL` for `cst_node_id` in `classes`, `functions`, `methods`, with valid UUID4 values.
2. Migration path works end-to-end: nullable add -> backfill -> NOT NULL -> runtime validation.
3. Indexing persists `cst_node_id` for entities and preserves stable IDs for unchanged logical entities.
4. Entity-returning analysis commands include `file_path` and `cst_node_id`.
5. Tree manipulation commands validate UUID4 IDs and use them as primary immutable target references for write operations.
6. Batch read-only command executes only whitelisted read-only commands.
7. If batch output is within limit, response can contain inline data.
8. If batch output exceeds limit, response contains `output_file`, `file_size`, and per-command `size/offset/length`; no oversized inline payload.
9. Optional convenience path supports one-or-many `cst_node_id` retrieval with node+descendants and location data in response.

---

## 9. Mandatory re-check after implementation

- Re-run all acceptance criteria and fix all gaps.
- Verify whitelist contains no mutating command.
- Validate UUID4 checks in schema path and runtime path.
- Re-test byte-range extraction using returned `offset`/`length` on generated output files.

---

*End of TZ.*
