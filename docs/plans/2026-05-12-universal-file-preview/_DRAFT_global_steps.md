# Global Step Decomposition (draft for review)

This is a draft of level-3 global steps for the `universal_file_preview` plan.
Each step lists the concepts it covers, the relations it implements, and the
binding source_spec line ranges it occupies. Each step passes the conceptual
test (no files, modules, classes, or functions named here).

## G-001 — Public command contract

**Concepts covered:** C-001 (PreviewCommand), C-012 (ResponseEnvelope),
C-014 (ErrorClassification), C-021 (ScopeBoundary).

**Relations implemented:**
- C-001 produces C-012
- C-001 produces C-014
- C-001 implements C-021

**Source ranges:** 5–8, 13–21, 168–184, 200–213, 215–226.

**Conceptual scope:** the system exposes one MCP command with a fixed input
schema, a uniform response envelope (one shape for all NodeKind values), a
deterministic error classification, and explicit negative scope. This step
fixes WHAT the command is to callers, not HOW it is built.


## G-002 — Uniform node model and navigation step

**Concepts covered:** C-002 (HandlerDispatcher), C-003 (Handler),
C-004 (NodeKind), C-005 (Sliceability), C-006 (ChildPreviewRule),
C-007 (NavigationStep), C-008 (Slice), C-013 (PreviewBudget).

**Relations implemented:**
- C-001 owns C-002
- C-002 uses C-003
- C-001 owns C-007
- C-007 consumes C-005
- C-007 consumes C-008
- C-007 uses C-006
- C-007 produces C-012
- C-005 depends_on C-004
- C-006 depends_on C-004
- C-001 consumes C-008
- C-001 consumes C-013
- C-007 consumes C-013
- C-003 produces C-014
- C-007 produces C-014

**Source ranges:** 25–34, 36–45, 47–70, 75–92, 95–106, 108–122,
186–198, 200–213.

**Conceptual scope:** the dispatcher chooses a handler; the handler produces
the uniform in-memory node representation (NodeKind plus child set); the one
navigation step asks Sliceability of the focus, applies Slice when it can,
and renders each child via the ChildPreviewRule appropriate to that child's
own NodeKind. This is the spine of the command. There are no per-type
engines and no per-type response shapes — only one procedure parameterised
by the node it works on.


## G-003 — Stable identifiers and tree sessions

**Concepts covered:** C-009 (StableIdentifier), C-010 (NodeReference),
C-011 (TreeSession).

**Relations implemented:**
- C-010 depends_on C-009
- C-007 consumes C-010
- C-001 consumes C-010
- C-007 uses C-011
- C-001 uses C-011

**Source ranges:** 124–145, 147–149, 151–166.

**Conceptual scope:** the command reuses identifiers from existing project
tree infrastructure (cst_load_file for Python, list_json_blocks for JSON,
project YAML infra or JSON-pointer-style paths for YAML, zero-based line
index for lines roots). It accepts an optional NodeReference to focus the
preview, and an optional caller-owned TreeSession or opens one transiently.
It never closes or invalidates sessions it did not create.


## G-004 — Per-type handlers

**Concepts covered:** C-016 (PythonHandler), C-017 (TextHandler),
C-018 (JsonHandler), C-019 (JsonLinesHandler), C-020 (YamlHandler).

**Relations implemented:**
- C-016 extends C-003
- C-017 extends C-003
- C-018 extends C-003
- C-019 extends C-003
- C-020 extends C-003
- C-016 produces C-004
- C-017 produces C-004
- C-018 produces C-004
- C-019 produces C-004
- C-020 produces C-004
- C-016 depends_on C-009
- C-018 depends_on C-009
- C-020 depends_on C-009

**Source ranges:** 130–144.

**Conceptual scope:** the five concrete handler families. Each handler does
two things only: open a file and produce its root Node in the uniform
representation; resolve a node_ref to a Node within that representation. No
navigation logic lives in a handler. The PythonHandler root is a tree_node
(Module); TextHandler root is lines; JsonLinesHandler root is lines and a
follow-up request parses a single line as its own JSON root; JsonHandler
and YamlHandler choose mapping/sequence/scalar per the document root, and
YamlHandler treats multi-document files as a sequence of document roots.


## G-005 — Read-only batch integration

**Concepts covered:** C-015 (ReadOnlyBatchIntegration).

**Relations implemented:**
- C-015 depends_on C-001

**Source ranges:** 20–21, 228–238.

**Conceptual scope:** after G-001 through G-004 are stable, the command name
is added to the read-only batch whitelist. This is a separate step because
the whitelist edit is a contract change for a different command and must not
happen before this command is green.


## I1 Coverage check (informal, to be verified before freeze)

Concepts: C-001..C-021 — all assigned to at least one global step. Each
concept appears in exactly one step (no overlaps).

Relations: every relation in spec.yaml (36 relations) is implemented by
exactly one global step. No relation is unassigned, no relation appears in
two steps.

Source ranges: 5..238 (binding lines only). Every binding section of
source_spec is referenced by at least one global step.

## Dependency order

- G-001 has no plan-internal dependencies.
- G-002 depends_on G-001 (navigation step produces the envelope defined by G-001).
- G-003 depends_on G-002 (NodeReference and TreeSession flow into the navigation step).
- G-004 depends_on G-002 and G-003 (handlers produce the node model that G-002 navigates, using identifier sources from G-003).
- G-005 depends_on G-004 (do not whitelist before handlers work).
