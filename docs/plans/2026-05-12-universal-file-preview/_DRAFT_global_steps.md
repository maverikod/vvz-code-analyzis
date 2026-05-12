# Global Step Decomposition (draft for review)

This is a draft of level-3 global steps for the `universal_file_preview` plan.
Each step lists the concepts it covers, the relations it implements, and the
binding source_spec line ranges it occupies. Each step passes the conceptual
test (no files, modules, classes, or functions named here).

## G-001 — Public command contract

**Concepts covered:** C-001 (PreviewCommand), C-012 (ResponseEnvelope),
C-014 (ErrorClassification), C-021 (ScopeBoundary).

**Relations implemented:** C-001→C-012 (produces), C-001→C-014 (produces),
C-001→C-021 (implements).

**Source ranges:** 5–8, 12–18, 20–21, 105–121, 136–148, 150–165.

**Conceptual scope:** the system exposes one MCP command with a fixed input
schema, a uniform response envelope, a deterministic error classification,
and explicit negative scope. This step fixes WHAT the command is to callers,
not HOW it is built.

## G-002 — Dispatcher and engine machinery

**Concepts covered:** C-002 (HandlerDispatcher), C-003 (Handler), C-004
(LinesEngine), C-005 (TreeEngine), C-006 (SequenceEngine), C-007
(AddressableSet), C-008 (Slice), C-013 (PreviewBudget).

**Relations implemented:** C-001→C-002 (owns), C-002→C-003 (uses),
C-003→C-004 (uses), C-003→C-005 (uses), C-003→C-006 (uses),
C-004→C-007 (produces), C-005→C-007 (produces), C-006→C-007 (produces),
C-008→C-007 (consumes), C-001→C-008 (consumes), C-001→C-013 (consumes),
C-004→C-012 (produces), C-005→C-012 (produces), C-006→C-012 (produces).

**Source ranges:** 24–29, 30–38, 41–50, 52–58, 60–66, 105–121, 123–134.

**Conceptual scope:** the dispatcher selects a handler, the handler selects
an engine, the engine operates on the addressable set under a slice and
budget caps, and produces the response envelope content. This is the spine
that every handler reuses.

## G-003 — Stable identifiers and tree sessions

**Concepts covered:** C-009 (StableIdentifier), C-010 (NodeReference),
C-011 (TreeSession).

**Relations implemented:** C-010→C-009 (depends_on), C-005→C-010 (consumes),
C-001→C-010 (consumes), C-005→C-011 (uses), C-001→C-011 (uses).

**Source ranges:** 70–82, 84–86, 88–103.

**Conceptual scope:** the command reuses identifiers from existing project
tree infrastructure; it accepts an optional NodeReference to focus the
preview; it accepts an optional caller-owned TreeSession or opens one
transiently; it never closes or invalidates sessions it did not create.

## G-004 — Per-type handlers

**Concepts covered:** C-016 (PythonHandler), C-017 (TextHandler),
C-018 (JsonHandler), C-019 (JsonLinesHandler), C-020 (YamlHandler).

**Relations implemented:**
C-016→C-003 (extends), C-017→C-003 (extends), C-018→C-003 (extends),
C-019→C-003 (extends), C-020→C-003 (extends),
C-016→C-005 (uses), C-016→C-009 (depends_on),
C-017→C-004 (uses),
C-018→C-005 (uses), C-018→C-006 (uses), C-018→C-009 (depends_on),
C-019→C-004 (uses),
C-020→C-005 (uses), C-020→C-006 (uses), C-020→C-004 (uses).

**Source ranges:** 31–38, 73–83.

**Conceptual scope:** the five concrete handler families. Each handler binds
a set of extensions to engines and identifier sources. This is where the
plan delivers actual file-type support.

## G-005 — Read-only batch integration

**Concepts covered:** C-015 (ReadOnlyBatchIntegration).

**Relations implemented:** C-015→C-001 (depends_on).

**Source ranges:** 19–21, 167–175.

**Conceptual scope:** after G-001 through G-004 are stable, the command name
is added to the read-only batch whitelist. This is a separate step because
the whitelist edit is a contract change for a different command and must not
happen before this command is green.


## I1 Coverage check (informal, to be verified before freeze)

Concepts: C-001..C-021 — all assigned to at least one global step.
Relations: every relation in spec.yaml has a unique home.
Source ranges: 5..175 (binding lines only) — every binding range appears in
at least one global step.

## Dependency order

- G-001 has no plan-internal dependencies.
- G-002 depends_on G-001 (engines produce the envelope defined by G-001).
- G-003 depends_on G-002 (NodeReference and TreeSession flow through engines).
- G-004 depends_on G-002 and G-003 (handlers compose engines and identifier
  sources).
- G-005 depends_on G-004 (do not whitelist before handlers work).
