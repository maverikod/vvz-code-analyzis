"""
Mode post-processors for analyze_tree.

Each function takes the shared ``CoreData`` and returns the mode-specific JSON
blocks. They are pure (operate on the precomputed core), so they can be tested by
constructing a ``CoreData`` directly without a DB.

Modes:
- package_boundary — extraction analysis (internal/outbound/inbound[/verdict])
- dependencies     — plain relation graph (internal vs external), no cycles
- structure        — composition (modules/classes/functions), no quality scoring
- cycles           — circular-import chains within the sub-tree

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Optional

from .core_types import CoreData, Edge

# Default "dirty module" seeds for the package_boundary verdict heuristic. A
# project-outbound dependency whose path contains one of these is server-bound
# (keep_in_server); config-ish ones are parameterize; everything else pull_in.
# Tunable via config: code_analysis.analyze_tree.dirty_module_seeds.
DEFAULT_KEEP_SEEDS = (
    "file_lock",
    "git_integration",
    "git",
    "backup_manager",
    "subprocess",
    "sqlite",
    "database",
    "_db",
    "network",
    "socket",
)
DEFAULT_PARAMETERIZE_SEEDS = ("config", "settings", "env")


def _is_internal(edge: Edge, core: CoreData) -> bool:
    return edge.kind == "project" and edge.target_rel in core.internal_set


def _internal_edges(core: CoreData) -> list[Edge]:
    """Edges whose source is inside the sub-tree."""
    return [e for e in core.edges if e.src in core.internal_set]


def classify_verdict(
    target_rel: str,
    *,
    keep_seeds: tuple[str, ...] = DEFAULT_KEEP_SEEDS,
    parameterize_seeds: tuple[str, ...] = DEFAULT_PARAMETERIZE_SEEDS,
) -> str:
    """Label a project-outbound dependency: keep_in_server / parameterize / pull_in."""
    low = target_rel.lower()
    if any(seed in low for seed in keep_seeds):
        return "keep_in_server"
    if any(seed in low for seed in parameterize_seeds):
        return "parameterize"
    return "pull_in"


def mode_package_boundary(
    core: CoreData,
    *,
    include_stdlib: bool = False,
    with_verdict: bool = False,
    keep_seeds: tuple[str, ...] = DEFAULT_KEEP_SEEDS,
    parameterize_seeds: tuple[str, ...] = DEFAULT_PARAMETERIZE_SEEDS,
) -> dict:
    """Extraction analysis for the sub-tree."""
    internal = _internal_edges(core)

    # Outbound: references that leave the sub-tree, grouped by kind.
    project_out: dict[str, set[str]] = {}
    third_party: set[str] = set()
    stdlib: set[str] = set()
    for e in internal:
        if e.kind == "project":
            if e.target_rel in core.internal_set:
                continue  # intra-subtree, not outbound
            project_out.setdefault(e.target_rel, set()).add(e.src)
        elif e.kind == "stdlib":
            stdlib.add(e.module)
        else:
            third_party.add(e.module)

    project_blockers = [
        {"target": target, "imported_by": sorted(srcs)}
        for target, srcs in sorted(project_out.items())
    ]
    outbound = {
        "project": project_blockers,  # the BLOCKER list
        "third_party": sorted(third_party),
    }
    if include_stdlib:
        outbound["stdlib"] = sorted(stdlib)

    # Inbound: files OUTSIDE the sub-tree that import INTO it (replacement sites).
    inbound_map: dict[str, set[str]] = {}
    for e in core.edges:
        if e.src in core.internal_set:
            continue
        if e.kind == "project" and e.target_rel in core.internal_set:
            inbound_map.setdefault(e.src, set()).add(e.target_rel)
    inbound = [
        {"importer": importer, "targets": sorted(targets)}
        for importer, targets in sorted(inbound_map.items())
    ]

    result = {
        "internal_files": list(core.internal_files),
        "outbound": outbound,
        "inbound": inbound,
        "summary": {
            "internal_count": len(core.internal_files),
            "project_outbound_count": len(project_blockers),
            "third_party_count": len(third_party),
            "stdlib_count": len(stdlib),
            "inbound_count": len(inbound),
        },
    }

    if with_verdict:
        result["verdict"] = [
            {
                "target": blocker["target"],
                "verdict": classify_verdict(
                    blocker["target"],
                    keep_seeds=keep_seeds,
                    parameterize_seeds=parameterize_seeds,
                ),
            }
            for blocker in project_blockers
        ]
    return result


def mode_dependencies(core: CoreData, *, include_stdlib: bool = False) -> dict:
    """Plain dependency graph of the sub-tree (internal vs external). No cycles."""
    internal = _internal_edges(core)
    internal_edges: list[dict] = []
    external_edges: list[dict] = []
    external_nodes: set[str] = set()
    for e in internal:
        if e.kind == "project" and e.target_rel in core.internal_set:
            internal_edges.append({"from": e.src, "to": e.target_rel})
        else:
            if e.kind == "stdlib" and not include_stdlib:
                continue
            external_edges.append({"from": e.src, "to": e.module, "kind": e.kind})
            external_nodes.add(e.module)
    return {
        "nodes": {
            "internal": list(core.internal_files),
            "external": sorted(external_nodes),
        },
        "edges": {
            "internal": internal_edges,
            "external": external_edges,
        },
        "summary": {
            "internal_node_count": len(core.internal_files),
            "external_node_count": len(external_nodes),
            "internal_edge_count": len(internal_edges),
            "external_edge_count": len(external_edges),
        },
    }


def mode_structure(core: CoreData) -> dict:
    """Composition of the sub-tree: per-file modules/classes/functions.

    Composition only — no complexity, long-file, or size scoring (those belong to
    comprehensive_analysis / analyze_complexity / list_long_files).
    """
    files = [
        {"file": rel, **core.structure_by_file.get(rel, {"classes": [], "functions": []})}
        for rel in core.internal_files
    ]
    class_total = sum(len(f.get("classes", [])) for f in files)
    func_total = sum(len(f.get("functions", [])) for f in files)
    method_total = sum(
        len(c.get("methods", [])) for f in files for c in f.get("classes", [])
    )
    return {
        "files": files,
        "summary": {
            "file_count": len(files),
            "class_count": class_total,
            "function_count": func_total,
            "method_count": method_total,
        },
    }


def _find_cycles(adjacency: dict[str, set[str]]) -> list[list[str]]:
    """Return cycles (SCCs of size >= 2, plus self-loops) via Tarjan's algorithm.

    Each cycle is returned as an ordered list of file paths. Iterative to avoid
    recursion limits on large sub-trees.
    """
    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    result: list[list[str]] = []
    nodes = sorted(adjacency.keys())

    for root in nodes:
        if root in indices:
            continue
        # Iterative DFS: work items are (node, neighbor_iterator).
        work: list[tuple[str, list[str]]] = [(root, sorted(adjacency.get(root, ())))]
        indices[root] = lowlink[root] = index_counter[0]
        index_counter[0] += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, neighbors = work[-1]
            progressed = False
            while neighbors:
                w = neighbors.pop(0)
                if w not in indices:
                    indices[w] = lowlink[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, sorted(adjacency.get(w, ()))))
                    progressed = True
                    break
                if w in on_stack:
                    lowlink[node] = min(lowlink[node], indices[w])
            if progressed:
                continue
            # All neighbors processed for `node`.
            if lowlink[node] == indices[node]:
                comp: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                self_loop = node in adjacency.get(node, set())
                if len(comp) >= 2 or self_loop:
                    result.append(list(reversed(comp)))
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
    return result


def mode_cycles(core: CoreData) -> dict:
    """Circular-import chains within the sub-tree (defect view)."""
    adjacency: dict[str, set[str]] = {rel: set() for rel in core.internal_set}
    for e in _internal_edges(core):
        if e.kind == "project" and e.target_rel in core.internal_set:
            adjacency[e.src].add(e.target_rel)
    cycles = _find_cycles(adjacency)
    return {
        "cycles": cycles,
        "cycles_found": len(cycles),
        "summary": {"cycles_found": len(cycles)},
    }


def is_test_path(rel: str) -> bool:
    """Heuristic: is ``rel`` a test file/dir (so its usages are 'test', not production)?"""
    low = rel.lower().replace("\\", "/")
    parts = low.split("/")
    if any(p in ("test", "tests") for p in parts[:-1]):
        return True
    base = parts[-1]
    return base.startswith("test_") or base.endswith("_test.py")


def mode_dead_code(core: CoreData) -> dict:
    """Classify every symbol defined under the roots by inbound usage.

    Buckets (precedence: production caller wins):
    - ``live``        — at least one production (non-test) file uses it
    - ``test_only``   — used only by test files, no production caller
    - ``import_only`` — imported somewhere but never used/called anywhere
    - ``unused``      — no usage and no import anywhere

    Usage matching is by symbol NAME (the index granularity), so identically
    named symbols in different files share attribution — this errs toward
    ``live`` and never toward a false ``unused`` (safe for a removal gate).
    Accuracy depends on a current usage/entity index (see the ``staleness`` block).
    """
    inputs = core.dead_code_inputs or {}
    symbols = inputs.get("symbols", [])
    usage_by_name: dict = inputs.get("usage_by_name", {})
    import_by_name: dict = inputs.get("import_by_name", {})

    results: list[dict] = []
    counts = {"live": 0, "test_only": 0, "import_only": 0, "unused": 0}
    for sym in symbols:
        name = sym["name"]
        own_file = sym["file"]
        # Count ALL usages incl. same-file: an internal helper used only within
        # its own module is still LIVE for a pre-extraction gate (removing it
        # would break the module). Self-references are the safe direction — they
        # never produce a false 'unused'.
        callers = list(usage_by_name.get(name, []))
        importers = [i for i in import_by_name.get(name, []) if i != own_file]
        prod_callers = [c for c in callers if not is_test_path(c)]
        test_callers = [c for c in callers if is_test_path(c)]
        if prod_callers:
            classification = "live"
        elif test_callers:
            classification = "test_only"
        elif importers:
            classification = "import_only"
        else:
            classification = "unused"
        counts[classification] += 1
        results.append(
            {
                "name": name,
                "kind": sym["kind"],
                "class_name": sym.get("class_name"),
                "file": own_file,
                "line": sym.get("line"),
                "classification": classification,
                "production_callers": prod_callers,
                "test_callers": test_callers,
                "importers": sorted(importers),
            }
        )

    # Stable, useful ordering: dead first (unused, import_only, test_only), then live.
    order = {"unused": 0, "import_only": 1, "test_only": 2, "live": 3}
    results.sort(key=lambda r: (order[r["classification"]], r["file"], r["line"] or 0))
    removable = [r for r in results if r["classification"] != "live"]
    return {
        "symbols": results,
        "removable": removable,
        "summary": {
            "total_symbols": len(results),
            **counts,
            "removable_count": len(removable),
        },
        "note": (
            "Usage matching is by symbol name; identically-named symbols share "
            "attribution (errs toward 'live'). Trust requires a current usage index "
            "— see the staleness block."
        ),
    }


def run_mode(
    mode: str,
    core: CoreData,
    *,
    include_stdlib: bool = False,
    with_verdict: bool = False,
    keep_seeds: Optional[tuple[str, ...]] = None,
    parameterize_seeds: Optional[tuple[str, ...]] = None,
) -> dict:
    """Dispatch to the selected mode post-processor."""
    if mode == "dead_code":
        return mode_dead_code(core)
    if mode == "package_boundary":
        return mode_package_boundary(
            core,
            include_stdlib=include_stdlib,
            with_verdict=with_verdict,
            keep_seeds=keep_seeds or DEFAULT_KEEP_SEEDS,
            parameterize_seeds=parameterize_seeds or DEFAULT_PARAMETERIZE_SEEDS,
        )
    if mode == "dependencies":
        return mode_dependencies(core, include_stdlib=include_stdlib)
    if mode == "structure":
        return mode_structure(core)
    if mode == "cycles":
        return mode_cycles(core)
    raise ValueError(f"unknown mode: {mode!r}")
