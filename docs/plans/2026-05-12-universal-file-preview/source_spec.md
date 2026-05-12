# Universal File Preview — Source Specification

## 1. Purpose

The system shall provide a single MCP command that returns a structured preview
of a project file. The preview lets a caller see the top-level structure of the
file (or of a node within it) and slice through that structure without reading
the whole file or learning a separate command for every file type.

The preview is read-only. It never modifies the project, the database, the
file watcher state, or any tree session that it did not create.

## 2. Outward shape

From outside, there is exactly one MCP command. Its name is
`universal_file_preview`. Its input has a fixed JSON Schema. Its output has a
fixed envelope. Behaviour varies internally by file type, but the contract a
caller sees is uniform.

The command joins the read-only batch whitelist so that it can be combined
with code-analysis queries in a single batch call.

## 3. Internal shape

Internally, the command is a package. The package has a dispatcher that picks
a handler by file extension. Each handler is responsible for one family of
files. New file types are added by adding handlers; the public command schema
does not change.

Handlers share three internal engines:

- a `lines` engine, for files whose addressable set is lines of text;
- a `tree` engine, for files whose addressable set is the children of a node
  in a hierarchical structure;
- a `sequence` engine, for files whose addressable set is the elements of an
  ordered collection.

A handler may use one engine fixed by file type (text, python), or it may
choose an engine per request based on what the root of the document turns
out to be (json, yaml).

## 4. Addressable set and slice

Every preview request operates on one **addressable set**, determined by the
file type and by the node the caller is looking at. The addressable set is
always an ordered, indexable collection. Possible sets are:

- the lines of a text file;
- the top-level statements of a Python module;
- the children of a Python class, function, or any other CST node;
- the keys of a JSON object or a YAML mapping (in file order);
- the elements of a JSON array or YAML sequence;
- the documents of a multi-document YAML file or of a JSONL file.

The caller may request a contiguous slice of the addressable set using a
single `slice` parameter. The slice is **Python-style: zero-based, half-open**.
Examples: `"0:5"` for the first five elements, `":3"` for the first three,
`"-5:"` for the last five, `":"` for the whole set (capped by `preview_lines`).

The `slice` parameter is uniform across all file types. What it slices is
defined by the file type and by the node selected by `node_ref`.

This zero-based half-open semantics is local to this command. Other commands
in the project that work with file line numbers (`get_file_lines`,
`cst_get_node_by_range`, `replace_file_lines`) continue to use their existing
one-based inclusive semantics. The discrepancy is intentional: this command
is for navigation; the others are for precise edits.

## 5. Stable identifiers

The command does not invent identifiers. It reuses the identifiers already
produced by the project's existing tree infrastructure:

- For Python files, the stable identifier of a node is the `stable_id` field
  returned by `cst_load_file` in its `outline_nodes` array. This is a UUID
  that the project persists in node-id blocks inside source files. It is
  stable across reloads as long as the project's CST infrastructure keeps it
  stable. No new identifier scheme is introduced.
- For JSON files, the stable identifier of a node is the `node_id` returned
  by `list_json_blocks`. JSON pointers (`/foo/bar`) are also accepted by the
  JSON handler as an alternative spelling, since the same infrastructure
  produces both.
- For YAML files, the stable identifier scheme depends on whether the project
  already has a YAML tree infrastructure. If it does, those identifiers are
  reused. If it does not, the YAML handler accepts JSON-pointer-style paths
  derived from the loaded YAML document.

The caller passes a stable identifier in the `node_ref` parameter to focus
the preview on a specific node. When `node_ref` is omitted, the focus is the
root of the file.

## 6. Tree sessions

Some callers will work with this command in isolation. Others will already
have a CST or JSON tree loaded in memory via `cst_load_file` or
`json_load_file`, and they will want this command to read from that
in-memory tree rather than reparse the file.

The command supports both:

- If the caller passes only `project_id` and `file_path`, the command may
  open and close any tree session it needs internally. It does not leak
  tree sessions to the caller.
- If the caller passes an existing `tree_id`, the command reads from that
  session and does not create or close anything.

When the command creates a tree session internally and that session is
useful for the caller's next step, the command returns its `tree_id` in
the response so the caller can pass it back next time.

The command never invalidates a `tree_id` it did not create.

## 7. Response envelope

The response has a uniform envelope. It always tells the caller:

- which kind of preview was produced (`tree`, `sequence`, `lines`);
- which slice was applied;
- the total size of the addressable set, so the caller knows what they did
  not see;
- the contents of the slice itself, in the shape appropriate to the kind;
- when relevant, the `tree_id` and root `node_ref` so the caller can navigate
  further.

For tree previews, each child reported in the response carries its own
`stable_id` so the caller can immediately drill into it with another
`universal_file_preview` call.

For sequence previews, each item reported carries its own index in the parent
sequence so the caller can slice deeper.

For lines previews, each line carries its own index.

## 8. Truncation and preview budget

A preview must not return more data than necessary to orient the caller.
Three numeric parameters limit the response size:

- `slice` bounds which part of the addressable set is included;
- `preview_lines` caps how much the command returns when `slice` is omitted
  (default: a small first chunk of the addressable set);
- `value_preview_len` caps the length of any single scalar value shown
  inline in the response.

When the response, after these caps, still exceeds the read-only batch size
threshold, the read-only batch overflow-to-file mechanism applies as usual.
The command itself does not implement file overflow.

## 9. Error model

The command surfaces three classes of error distinctly:

- input errors (unknown file type, malformed `slice`, unknown `node_ref`,
  conflicting parameters) return a deterministic error code per class;
- file-structure errors (a `.json` file that does not parse, a `.yaml` file
  with a syntax error) return a single error code that names the failing
  parser and points to the line range that failed, when possible;
- handler-internal errors (a CST node cannot be resolved, a JSON pointer
  refers outside the document) return a code that names the handler.

The command never silently falls back to a different file type or a
different engine on error. A failed preview returns an error; the caller
decides whether to retry with different parameters or use a different
command.

## 10. Boundaries

The command does not write to files, the database, or tree sessions it did
not create.

The command does not return raw file bytes. All output is structured JSON.

The command does not accept globs or wildcards in `file_path`. One call
operates on exactly one file.

The command does not include XML or HTML in its initial scope. Those file
types are deferred to a later plan.

## 11. Integration with the read-only batch whitelist

After the command is implemented and its handlers stabilise, the command
name is added to `READ_ONLY_BATCH_WHITELIST` in
`code_analysis/commands/read_only_batch_whitelist.py`. From that moment
the command is callable inside `read_only_batch` invocations alongside
the existing analysis queries.

The whitelist edit is its own step in the plan, not part of the command
package. The whitelist edit happens only after the command and its tests
are green.

<!-- non-binding -->
## Notes

The XML/HTML deferral is mentioned only to mark scope; it does not produce
any concept. The 1-based/0-based discrepancy explained in section 4 is
documentation, not behaviour beyond what section 4 already binds.
<!-- /non-binding -->
