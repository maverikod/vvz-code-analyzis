"""
Output formatters for analyze_tree (atom A-OUT).

``json`` is the canonical form returned by the service; these helpers render the
same data as ``dot`` (a graph tailored to the mode) or ``markdown`` (a human
report). They consume the JSON ``data`` dict so they stay decoupled from the DB.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations


def _q(text: str) -> str:
    """Quote/escape a string for a DOT node or edge id."""
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def format_dot(data: dict) -> str:
    """Render the mode-relevant graph as Graphviz DOT."""
    mode = data.get("mode")
    lines = ["digraph analyze_tree {", "  rankdir=LR;"]

    if mode == "package_boundary":
        internal = data.get("internal_files", [])
        lines.append("  subgraph cluster_internal {")
        lines.append('    label="sub-tree";')
        for n in internal:
            lines.append(f"    {_q(n)};")
        lines.append("  }")
        for blocker in data.get("outbound", {}).get("project", []):
            target = blocker["target"]
            for src in blocker.get("imported_by", []):
                lines.append(f"  {_q(src)} -> {_q(target)} [color=red];")
        for item in data.get("inbound", []):
            importer = item["importer"]
            for tgt in item.get("targets", []):
                lines.append(f"  {_q(importer)} -> {_q(tgt)} [color=blue,style=dashed];")

    elif mode == "dependencies":
        for e in data.get("edges", {}).get("internal", []):
            lines.append(f"  {_q(e['from'])} -> {_q(e['to'])};")
        for e in data.get("edges", {}).get("external", []):
            style = "dotted" if e.get("kind") == "stdlib" else "dashed"
            lines.append(f"  {_q(e['from'])} -> {_q(e['to'])} [style={style}];")

    elif mode == "structure":
        for f in data.get("files", []):
            fnode = f["file"]
            lines.append(f"  {_q(fnode)} [shape=box];")
            for c in f.get("classes", []):
                cn = f"{fnode}::{c['name']}"
                lines.append(f"  {_q(fnode)} -> {_q(cn)};")
            for fn in f.get("functions", []):
                lines.append(f"  {_q(fnode)} -> {_q(fnode + '::' + str(fn['name']))};")

    elif mode == "cycles":
        for cycle in data.get("cycles", []):
            ring = cycle + [cycle[0]] if cycle else []
            for a, b in zip(ring, ring[1:]):
                lines.append(f"  {_q(a)} -> {_q(b)} [color=red,penwidth=2];")

    lines.append("}")
    return "\n".join(lines)


def _md_header(data: dict) -> list[str]:
    roots = ", ".join(data.get("roots", [])) or "(project root)"
    counts = data.get("staleness", {}).get("counts", {})
    counts_str = ", ".join(f"{k}={v}" for k, v in counts.items())
    out = [
        f"# analyze_tree — `{data.get('mode')}`",
        "",
        f"**Roots:** {roots}",
        f"**Staleness:** {counts_str}",
    ]
    if data.get("truncated"):
        out.append("**Note:** edge limit reached — output truncated.")
    out.append("")
    return out


def format_markdown(data: dict) -> str:
    """Render a human-readable report tailored to the mode."""
    mode = data.get("mode")
    lines = _md_header(data)

    if mode == "package_boundary":
        s = data.get("summary", {})
        lines.append(
            f"Internal files: {s.get('internal_count', 0)} · "
            f"project leaks: {s.get('project_outbound_count', 0)} · "
            f"third-party: {s.get('third_party_count', 0)} · "
            f"inbound callers: {s.get('inbound_count', 0)}"
        )
        lines.append("")
        lines.append("## Outbound — project (BLOCKER)")
        verdict_by_target = {v["target"]: v["verdict"] for v in data.get("verdict", [])}
        for b in data.get("outbound", {}).get("project", []):
            v = f" — _{verdict_by_target[b['target']]}_" if b["target"] in verdict_by_target else ""
            lines.append(f"- `{b['target']}`{v} (imported by {len(b['imported_by'])} file(s))")
        lines.append("")
        lines.append("## Outbound — third party")
        for m in data.get("outbound", {}).get("third_party", []):
            lines.append(f"- `{m}`")
        if "stdlib" in data.get("outbound", {}):
            lines.append("")
            lines.append("## Outbound — stdlib")
            for m in data["outbound"]["stdlib"]:
                lines.append(f"- `{m}`")
        lines.append("")
        lines.append("## Inbound — external callers (replacement sites)")
        for item in data.get("inbound", []):
            lines.append(f"- `{item['importer']}` → {', '.join('`'+t+'`' for t in item['targets'])}")

    elif mode == "dependencies":
        s = data.get("summary", {})
        lines.append(
            f"Internal nodes: {s.get('internal_node_count', 0)} · "
            f"external nodes: {s.get('external_node_count', 0)} · "
            f"internal edges: {s.get('internal_edge_count', 0)} · "
            f"external edges: {s.get('external_edge_count', 0)}"
        )

    elif mode == "structure":
        s = data.get("summary", {})
        lines.append(
            f"Files: {s.get('file_count', 0)} · classes: {s.get('class_count', 0)} · "
            f"functions: {s.get('function_count', 0)} · methods: {s.get('method_count', 0)}"
        )
        lines.append("")
        for f in data.get("files", []):
            lines.append(f"### `{f['file']}`")
            for c in f.get("classes", []):
                methods = ", ".join(m["name"] for m in c.get("methods", []))
                lines.append(f"- class **{c['name']}**" + (f" — {methods}" if methods else ""))
            for fn in f.get("functions", []):
                lines.append(f"- def {fn['name']}")
            lines.append("")

    elif mode == "cycles":
        n = data.get("cycles_found", 0)
        lines.append(f"**Cycles found: {n}**")
        lines.append("")
        for i, cycle in enumerate(data.get("cycles", []), 1):
            chain = " → ".join(f"`{p}`" for p in cycle)
            lines.append(f"{i}. {chain} → (back to start)")

    return "\n".join(lines)


def format_output(data: dict, fmt: str) -> dict:
    """Wrap the JSON data per the requested output format."""
    if fmt == "dot":
        return {
            "mode": data.get("mode"),
            "roots": data.get("roots"),
            "staleness": data.get("staleness"),
            "format": "dot",
            "dot": format_dot(data),
        }
    if fmt == "markdown":
        return {
            "mode": data.get("mode"),
            "roots": data.get("roots"),
            "staleness": data.get("staleness"),
            "format": "markdown",
            "markdown": format_markdown(data),
        }
    data["format"] = "json"
    return data
