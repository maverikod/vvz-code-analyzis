# Universal File Preview — Source Specification

## 1. Purpose

The system shall provide a single MCP command that returns a structured
preview of a project file. The preview lets a caller see the top-level
structure of the file (or of a node within it), select a contiguous slice
or an explicit set of blocks by index or identifier, and inspect each
selected block without reading the whole file or learning a separate
command for every file type.

The preview is read-only. It never modifies the project, the database, the
file watcher state, or any tree session that it did not create.

## 2. Outward shape

From outside, there is exactly one MCP command. Its name is
`universal_file_preview`. Its input has a fixed JSON Schema. Its output has
a fixed envelope. Behaviour varies internally by file type, but the
contract a caller sees is uniform.

The command joins the read-only batch whitelist so that it can be combined
with code-analysis queries in a single batch call.

## 3. Internal shape

Internally, the command is a package. The package has a dispatcher that
picks a file handler by file extension. Each file handler is responsible
for opening one family of files and producing a uniform in-memory node
representation that the rest of the command navigates without knowing the
file type. New file types are added by adding new file handlers; the
public command schema does not change.

The command has one navigation procedure that works against the uniform
node representation. The procedure runs in three phases on every request,
on the current focus node:

1. enumerate the blocks of the focus node (its addressable children);
2. select a subset of those blocks via the caller's selector;
3. for each selected block, build a summary via the block handler
   appropriate to that block's own node kind.

The procedure is recursive: drilling into a selected block is a follow-up
request where that block becomes the new focus node, and the same three
phases run against it.

## 4. Uniform node representation

Every node the command works with — the root of a file, a child of a tree
node, an element of a sequence, a line of a text file — carries three
properties:

- a **node kind**, one of: `scalar`, `lines`, `mapping`, `sequence`,
  `tree_node`. `tree_node` is the combined kind for nodes that have both
  named attributes and an ordered child set, such as CST function and
  class definitions.
- an **ordered block set**: the node's addressable children, in file
  order. A scalar node has an empty block set. A `mapping` block's
  contents include both the key and the value as a single self-contained
  unit; nothing about the parent is needed to render it.
- a **node identifier** in the file handler's native format, used as
  `node_ref` when the caller wants to refocus on this node.

A file handler turns a file into a tree of such nodes lazily: only the
root and the children needed by the current request are materialised.
Children are themselves uniform nodes, so the same navigation procedure
can drill down into any of them in a follow-up request.

## 5. Block

A **block** is one element of a focus node's ordered block set. Blocks
are the units that the selector addresses and that block handlers render.
A block is itself a uniform node and carries its own node kind, block
set, and identifier. A block is self-contained: a block handler never
needs information about the parent focus node to render its summary.

The block set of a focus node may be empty (scalar focus) or non-empty
(every other kind). Phase 1 of the navigation procedure produces the
block set for the current focus.

## 6. Selector

A **selector** is a single optional parameter of the command, named
`selector`, that picks which blocks of the focus node's block set to
include in the response.

The selector accepts three forms, and the form is decided by the value's
type and shape, not by a separate parameter:

- a **string with `:` or a leading `-`** is a slice. Python-style,
  zero-based, half-open. Examples: `"0:5"` (first five blocks), `":3"`
  (first three), `"-5:"` (last five), `":"` (all blocks, capped by
  `preview_lines`).
- a **list of integers** is an explicit list of block indices.
  Zero-based.
- a **list of strings** is an explicit list of block node identifiers.

Mixed lists (integers and strings together) are rejected as an input
error: lists are homogeneous.

When the selector is omitted, the response contains the first
`preview_lines` blocks of the focus node's block set, in natural order.

When the selector is a slice, the response contains the blocks of that
slice in natural order.

When the selector is an explicit list, the response contains the
addressed blocks **in the order given by the caller**. Repeating the same
index or identifier in the list is rejected as an input error.
Addressing an index out of range or an unknown identifier is rejected as
an input error.

When the focus node has an empty block set, any selector is rejected as
an input error.

This zero-based half-open and zero-based indexing semantics is local to
this command. Other commands in the project that work with file line
numbers (`get_file_lines`, `cst_get_node_by_range`, `replace_file_lines`)
continue to use their existing one-based inclusive semantics. The
discrepancy is intentional: this command is for navigation; the others
are for precise edits.

## 7. Block handler

A **block handler** is the rendering rule for one node kind. Five block
handlers exist, one per node kind:

- `scalar`: the value, truncated by `value_preview_len`.
- `lines`: a count of lines and the first line truncated by
  `value_preview_len`.
- `sequence`: the length and a coarse summary of element kinds.
- `mapping`: a count of keys and a short list of key names truncated by
  `value_preview_len`.
- `tree_node`: a type label, an optional name, a compact dictionary of
  attributes appropriate to the type (for example, `params` and
  `returns` for a function), and a count of children.

The block handler is chosen by the block's own node kind, not by the
parent focus node's kind. A block handler never includes the block's
own children's content. To see inside a block, the caller issues a
follow-up request with that block's `node_ref`.

The set of five block handlers is closed in this plan. A new node kind
would require adding a new block handler; the navigation procedure
itself would not change.

## 8. Stable identifiers

The command does not invent identifiers. It reuses identifiers already
produced by the project's existing tree infrastructure:

- For Python files, the identifier of a node is the `stable_id` field
  returned by `cst_load_file` in its `outline_nodes` array. This is a
  UUID that the project persists in node-id blocks inside source files.
  It is stable across reloads as long as the project's CST
  infrastructure keeps it stable. No new identifier scheme is
  introduced.
- For JSON files, the identifier of a node is the `node_id` returned by
  `list_json_blocks`. JSON pointers (`/foo/bar`) are also accepted by
  the JSON file handler as an alternative spelling, since the same
  infrastructure produces both.
- For YAML files, the identifier scheme depends on whether the project
  already has a YAML tree infrastructure. If it does, those identifiers
  are reused. If it does not, the YAML file handler accepts
  JSON-pointer-style paths derived from the loaded YAML document.
- For text files (`.md`, `.txt`, `.rst`, `.adoc`) and JSON Lines files
  (`.jsonl`, `.ndjson`), the root is a `lines` node. Children are
  addressed by their zero-based index in the file. No separate
  identifier scheme is needed.

The caller passes a stable identifier in the `node_ref` parameter to
focus the preview on a specific node. When `node_ref` is omitted, the
focus is the root of the file.

## 9. Tree sessions

Some callers will work with this command in isolation. Others will
already have a CST or JSON tree loaded in memory via `cst_load_file` or
`json_load_file`, and they will want this command to read from that
in-memory tree rather than reparse the file.

The command supports both:

- If the caller passes only `project_id` and `file_path`, the command
  may open and close any tree session it needs internally. It does not
  leak tree sessions to the caller.
- If the caller passes an existing `tree_id`, the command reads from
  that session and does not create or close anything.

When the command creates a tree session internally and that session is
useful for the caller's next step, the command returns its `tree_id` in
the response so the caller can pass it back next time.

The command never invalidates a `tree_id` it did not create.

## 10. Response envelope

The response has a uniform envelope. It always tells the caller:

- the focus node: its node kind, its node_ref (the identifier the
  caller can pass back to focus on it again), and the node's own
  metadata (type, name, attributes when applicable);
- the selector that was applied: slice string, integer list, or string
  list (echoed back in normalised form), or `null` when no selector
  was given;
- the total size of the focus node's block set, so the caller knows
  what they did not see;
- the list of selected blocks. Order follows the selector: natural
  order for slice and for omitted selector, caller-given order for
  explicit lists. Each block is rendered through its block handler and
  carries its own node_ref for further drill-down;
- when the command created a tree session internally, the `tree_id` for
  reuse.

There is no per-kind envelope variant. The envelope shape is constant;
the `node_kind` field on the focus and on each block tells the caller
how to interpret the rest.

## 11. Truncation and preview budget

A preview must not return more data than necessary to orient the caller.
Three numeric parameters limit the response size:

- `selector` bounds which blocks are returned (when set);
- `preview_lines` caps how many blocks the command returns when
  `selector` is omitted (default: a small first chunk of the block
  set);
- `value_preview_len` caps the length of any single scalar value or
  name shown inline in the response.

When the response, after these caps, still exceeds the read-only batch
size threshold, the read-only batch overflow-to-file mechanism applies
as usual. The command itself does not implement file overflow.

## 12. Error model

The command surfaces three classes of error distinctly:

- input errors return a deterministic error code per class:
  malformed selector value, mixed-type list, duplicate entry in list,
  out-of-range index, unknown identifier, selector on empty block set,
  unknown file extension, unknown `node_ref`, conflicting parameters;
- file-structure errors (a `.json` file that does not parse, a `.yaml`
  file with a syntax error) return a single error code that names the
  failing parser and points to the line range that failed, when
  possible;
- file-handler-internal errors (a CST node cannot be resolved, a JSON
  pointer refers outside the document) return a code that names the
  file handler.

The command never silently falls back to a different file type. A
failed preview returns an error; the caller decides whether to retry
with different parameters or use a different command.

## 13. Boundaries

The command does not write to files, the database, or tree sessions it
did not create.

The command does not return raw file bytes. All output is structured
JSON.

The command does not accept globs or wildcards in `file_path`. One call
operates on exactly one file.

The command does not include XML or HTML in its initial scope. Those
file types are deferred to a later plan.

## 14. Integration with the read-only batch whitelist

After the command is implemented and its file handlers stabilise, the
command name is added to `READ_ONLY_BATCH_WHITELIST` in
`code_analysis/commands/read_only_batch_whitelist.py`. From that moment
the command is callable inside `read_only_batch` invocations alongside
the existing analysis queries.

The whitelist edit is its own step in the plan, not part of the command
package. The whitelist edit happens only after the command and its
file handlers are green.

<!-- non-binding -->
## Notes

The XML/HTML deferral is mentioned only to mark scope; it does not
produce any concept. The 1-based/0-based discrepancy explained in
section 6 is documentation, not behaviour beyond what section 6 already
binds. The explicit enumeration of node kinds in section 4 and the
explicit enumeration of selector forms in section 6 are binding; the
example shapes shown in section 7 are illustrative.
<!-- /non-binding -->
