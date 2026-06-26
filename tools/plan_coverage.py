#!/usr/bin/env python3
"""Read-only HRS<->MRS coverage check for a git-spec-style plan.

Labels (not line numbers) are the binding link between source_spec.md (HRS) and
spec.yaml (MRS). This tool extracts every {xxxx} label from binding paragraphs of
the HRS, every concept's source_labels from the MRS, and reports:
  - uncovered HRS labels (in HRS, not referenced by any concept)  -> cycle_1 c2
  - orphan label references (referenced by a concept, absent from HRS) -> c1
  - shared labels (one label, many concepts)
  - concept-schema violations (missing required fields)            -> F-3 class
  - relation-type violations (type outside the seven allowed)       -> F-2 class
Line numbers of labels are printed for convenience only; matching is by label.
Changes nothing. Exit 1 on any finding.
"""
import os
import re
import sys

import yaml

PLAN = os.environ.get("PLAN_DIR", "docs/plans/git-spec")
HRS = os.path.join(PLAN, "source_spec.md")
MRS = os.path.join(PLAN, "spec.yaml")

ALLOWED_RELATION_TYPES = {
    "uses",
    "owns",
    "implements",
    "extends",
    "depends_on",
    "produces",
    "consumes",
}
REQUIRED_CONCEPT_FIELDS = (
    "concept_id",
    "name",
    "definition",
    "properties",
    "source_labels",
)
LABEL_RE = re.compile(r"\{([0-9a-z]{4})\}")

findings = []


def finding(msg):
    """Record and print one coverage failure."""
    findings.append(msg)
    print("[FAIL] " + msg)


def info(msg):
    """Print one informational coverage message."""
    print("[info] " + msg)


def extract_hrs_labels(path):
    """Return {label: first_line_no} for labels in binding paragraphs.

    Lines between <!-- non-binding --> and <!-- /non-binding --> are skipped.
    """
    labels = {}
    binding = True
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            stripped = raw.strip()
            if stripped.startswith("<!-- non-binding"):
                binding = False
                continue
            if stripped.startswith("<!-- /non-binding"):
                binding = True
                continue
            if not binding:
                continue
            for m in LABEL_RE.finditer(raw):
                lab = m.group(1)
                labels.setdefault(lab, lineno)
    return labels


def load_mrs(path):
    """Load the MRS YAML document from disk."""
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def strip_label(value):
    """Accept '{a1b2}' or 'a1b2'; return bare 4-char label or None."""
    if not isinstance(value, str):
        return None
    m = LABEL_RE.search(value)
    if m:
        return m.group(1)
    v = value.strip()
    return v if re.fullmatch(r"[0-9a-z]{4}", v) else None


def main():
    """Run coverage checks and return a process exit code."""
    if not os.path.isfile(HRS):
        print(f"HRS not found: {HRS}")
        return 2
    if not os.path.isfile(MRS):
        print(f"MRS not found: {MRS}")
        return 2

    hrs_labels = extract_hrs_labels(HRS)
    info(f"HRS binding labels: {len(hrs_labels)}")

    mrs = load_mrs(MRS)
    concepts = mrs.get("concepts") or []
    relations = mrs.get("relations") or []
    info(f"MRS concepts: {len(concepts)}; relations: {len(relations)}")

    # Schema checks + label index
    label_to_concepts = {}
    concept_ids = set()
    for c in concepts:
        if not isinstance(c, dict):
            finding(f"concept entry is not a mapping: {c!r}")
            continue
        cid = c.get("concept_id", "<no concept_id>")
        concept_ids.add(cid)
        for field in REQUIRED_CONCEPT_FIELDS:
            if field not in c or c.get(field) in (None, "", [], {}):
                finding(f"{cid}: missing or empty required field '{field}'")
        for raw_lab in c.get("source_labels") or []:
            lab = strip_label(raw_lab)
            if lab is None:
                finding(f"{cid}: source_label not a 4-char label: {raw_lab!r}")
                continue
            label_to_concepts.setdefault(lab, []).append(cid)

    # Relation type + reference checks
    for r in relations:
        if not isinstance(r, dict):
            finding(f"relation entry is not a mapping: {r!r}")
            continue
        rtype = r.get("type")
        if rtype not in ALLOWED_RELATION_TYPES:
            finding(f"relation type not allowed: {rtype!r} ({r})")
        for end in ("from_concept", "to_concept"):
            ref = r.get(end)
            if ref not in concept_ids:
                finding(f"relation {end} references unknown concept: {ref!r}")

    # Coverage: HRS -> MRS
    referenced = set(label_to_concepts)
    hrs_set = set(hrs_labels)
    uncovered = sorted(hrs_set - referenced, key=lambda x: hrs_labels[x])
    for lab in uncovered:
        finding(f"uncovered HRS label {{{lab}}} (line {hrs_labels[lab]}) - no concept references it")

    # Orphans: MRS -> HRS
    orphans = sorted(referenced - hrs_set)
    for lab in orphans:
        finding(f"orphan label {{{lab}}} referenced by {label_to_concepts[lab]} but absent from HRS")

    # Shared labels (informational)
    shared = {k: v for k, v in label_to_concepts.items() if len(v) > 1}
    if shared:
        info("shared labels (one label, multiple concepts):")
        for lab in sorted(shared):
            print(f"    {{{lab}}}: {', '.join(shared[lab])}")

    print()
    if findings:
        print(f"COVERAGE RESULT: {len(findings)} FINDING(S)")
        return 1
    print("COVERAGE RESULT: GREEN (every HRS label covered, no orphans, schema clean)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
