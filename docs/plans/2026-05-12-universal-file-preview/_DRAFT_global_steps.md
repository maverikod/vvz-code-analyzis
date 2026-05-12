# Global Step Decomposition (draft for review)

Draft of level-3 global steps for the `universal_file_preview` plan.
Each step lists the concepts it covers, the relations it implements, and
the binding source_spec line ranges it occupies. Each step passes the
conceptual test (no files, modules, classes, or functions named here).

The plan has 9 global steps. This is above the typical_range upper bound
of 7 but below the indicator_threshold of 10. The decomposition uses one
step per file handler (G-004..G-008) so future file handlers (XML, TOML,
binary formats, ...) can be added as new G-NNN steps without touching
the existing ones.


## G-001 — Public command contract

**Concepts covered:** C-001 (PreviewCommand), C-012 (ResponseEnvelope),
C-014 (ErrorClassification), C-021 (ScopeBoundary).

**Relations implemented:**
- C-001 produces C-012
- C-001 produces C-014
- C-001 implements C-021

**Source ranges:** 5–12, 14–22, 192–211, 229–246, 248–260.

**Conceptual scope:** the system exposes one MCP command with a fixed
input schema, a uniform response envelope (one shape for all NodeKind
values and all selector forms), a deterministic error classification,
and explicit negative scope. This step fixes WHAT the command is to
callers, not HOW it is built.


## G-002 — Uniform node model and three-phase navigation

**Concepts covered:** C-002 (HandlerDispatcher), C-003 (FileHandler),
C-004 (NodeKind), C-005 (Block), C-006 (NavigationProcedure),
C-007 (Selector), C-008 (BlockHandler), C-013 (PreviewBudget).

**Relations implemented:**
- C-001 owns C-002
- C-002 uses C-003
- C-001 owns C-006
- C-006 produces C-005
- C-006 consumes C-007
- C-006 uses C-008
- C-006 produces C-012
- C-005 depends_on C-004
- C-008 depends_on C-004
- C-001 consumes C-007
- C-001 consumes C-013
- C-006 consumes C-013
- C-003 produces C-014
- C-006 produces C-014

**Source ranges:** 26–47, 51–59, 65–70, 72–81, 83–121, 123–142,
213–227, 229–246.

**Conceptual scope:** the dispatcher chooses a file handler; the file
handler produces the uniform in-memory node representation; the one
three-phase navigation procedure (enumerate blocks of focus, select via
the polymorphic selector, render each selected block via its block
handler) operates on that representation. The Selector accepts three
forms (slice string / int list / string list) dispatched by value shape.
BlockHandler is one concept with five rendering rules keyed by NodeKind
(closed set under this plan). This step is the spine of the command.


## G-003 — Stable identifiers and tree sessions

**Concepts covered:** C-009 (StableIdentifier), C-010 (NodeReference),
C-011 (TreeSession).

**Relations implemented:**
- C-010 depends_on C-009
- C-006 consumes C-010
- C-001 consumes C-010
- C-006 uses C-011
- C-001 uses C-011

**Source ranges:** 144–169, 171–173, 175–190.

**Conceptual scope:** the command reuses identifiers from existing
project tree infrastructure (cst_load_file for Python, list_json_blocks
for JSON, project YAML infra or JSON-pointer-style paths for YAML,
zero-based line index for lines roots). It accepts an optional
NodeReference to focus the preview and an optional caller-owned
TreeSession or opens one transiently. It never closes or invalidates
sessions it did not create.


## G-004 — Python file handler

**Concepts covered:** C-016 (PythonFileHandler).

**Relations implemented:**
- C-016 extends C-003
- C-016 produces C-004
- C-016 depends_on C-009

**Source ranges:** 150–156.

**Conceptual scope:** the file handler for .py, .pyi, .pyw. It opens a
Python file and produces a tree_node root (Module). Interior nodes
follow the CST: FunctionDef and ClassDef are tree_node, their bodies
are sequences of further tree_node statements, leaf values are scalar.
The handler resolves node_ref values that are stable_id UUIDs produced
by cst_load_file. It does not implement navigation.


## G-005 — Text file handler

**Concepts covered:** C-017 (TextFileHandler).

**Relations implemented:**
- C-017 extends C-003
- C-017 produces C-004

**Source ranges:** 163–167.

**Conceptual scope:** the file handler for .md, .txt, .rst, .adoc. It
opens a text file and produces a lines root whose children are scalar
text lines. node_ref values for child lines are zero-based line
indices. Scalar lines have no children of their own.


## G-006 — JSON file handler

**Concepts covered:** C-018 (JsonFileHandler).

**Relations implemented:**
- C-018 extends C-003
- C-018 produces C-004
- C-018 depends_on C-009

**Source ranges:** 158–161.

**Conceptual scope:** the file handler for .json. It opens a JSON file
and produces a root whose NodeKind depends on the document: mapping
for objects, sequence for arrays, scalar for bare scalars. Interior
nodes follow the JSON shape. The handler resolves node_ref values as
node_id from list_json_blocks or as JSON pointers (`/foo/bar`).


## G-007 — JSON Lines file handler

**Concepts covered:** C-019 (JsonLinesFileHandler).

**Relations implemented:**
- C-019 extends C-003
- C-019 produces C-004

**Source ranges:** 163–167.

**Conceptual scope:** the file handler for .jsonl, .ndjson. It opens a
JSONL file and produces a lines root whose children are scalar text
lines, so a selector at the root selects line indices without parsing
any JSON. When the caller drills into a specific line by passing its
index, the follow-up request parses that line as its own root (using
the JSON-handler logic from G-006). This step composes the lines root
and delegates per-line parsing; it does not duplicate JSON parsing.


## G-008 — YAML file handler

**Concepts covered:** C-020 (YamlFileHandler).

**Relations implemented:**
- C-020 extends C-003
- C-020 produces C-004
- C-020 depends_on C-009

**Source ranges:** 163–167.

**Conceptual scope:** the file handler for .yaml, .yml. It opens a YAML
file and produces a root whose NodeKind depends on the document:
mapping for YAML mappings, sequence for YAML sequences, scalar for
bare scalars. A multi-document YAML file (separated by `---`) produces
a sequence root whose elements are the document roots. The handler
resolves node_ref using the project YAML tree infrastructure when
present, otherwise as JSON-pointer-style paths derived from the loaded
document.


## G-009 — Read-only batch integration

**Concepts covered:** C-015 (ReadOnlyBatchIntegration).

**Relations implemented:**
- C-015 depends_on C-001

**Source ranges:** 19–22, 262–272.

**Conceptual scope:** after G-001 through G-008 are stable, the command
name is added to the read-only batch whitelist. This is a separate
step because the whitelist edit is a contract change for a different
command and must not happen before the command and its file handlers
are green.


## I1 Coverage check (verified locally before this draft was written)

Concepts: C-001..C-021 — 21 concepts in spec.yaml. All 21 are assigned
to exactly one global step. No concept appears in two steps.

Relations: 36 relations in spec.yaml. All 36 are implemented by exactly
one global step. No relation is unassigned, no relation appears in two
steps.

Source ranges: 5..272 (binding lines only). Every binding section of
source_spec is referenced by at least one global step.

Step count: 9. Above typical_range upper bound of 7, below
indicator_threshold of 10. The excess is intentional: one file handler
per step allows new handlers to be added as new G-NNN steps without
revising any existing step.


## Dependency order

- G-001 has no plan-internal dependencies.
- G-002 depends_on G-001 (navigation produces the envelope from G-001).
- G-003 depends_on G-002 (NodeReference and TreeSession flow into the
  navigation procedure).
- G-004 depends_on G-002 and G-003 (Python file handler produces nodes
  that G-002 navigates, using identifier source from G-003).
- G-005 depends_on G-002 (text file handler; no identifier source
  needed beyond zero-based index).
- G-006 depends_on G-002 and G-003 (JSON file handler, identifier
  source from G-003).
- G-007 depends_on G-005 and G-006 (JSONL composes a lines root from
  G-005 and reuses JSON parsing from G-006 for per-line drill-down).
- G-008 depends_on G-002 and G-003 (YAML file handler, identifier
  source from G-003).
- G-009 depends_on G-001..G-008 (do not whitelist before all handlers
  work).

## Adding a new file handler in the future

Adding support for a new file type creates one new G-NNN step (the
file handler) and one cascade update to source_spec/spec.yaml to
introduce its concept. Existing handlers and the navigation procedure
are not touched.
