"""
MCP command wrapper: export_graph.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand


class ExportGraphMCPCommand(BaseMCPCommand):
    """Export dependency graphs, class hierarchies, or call graphs.

    The goal of this command is to provide stable output (JSON or DOT) without
    failing when the underlying project contains partial or missing data.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Human readable description.
        category: Command category.
        author: Author name.
        email: Author email.
        use_queue: Whether command runs via queue.
    """

    name = "export_graph"
    version = "1.0.0"
    descr = "Export graphs (dependencies, hierarchy, call_graph) in DOT or JSON format"
    category = "ast"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["ExportGraphMCPCommand"]) -> Dict[str, Any]:
        """Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema describing command parameters.
        """
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory (contains data/code_analysis.db)",
                },
                "graph_type": {
                    "type": "string",
                    "description": "Type of graph: 'dependencies', 'hierarchy', or 'call_graph'",
                    "enum": ["dependencies", "hierarchy", "call_graph"],
                    "default": "dependencies",
                },
                "format": {
                    "type": "string",
                    "description": "Output format: 'dot' (Graphviz) or 'json'",
                    "enum": ["dot", "json"],
                    "default": "dot",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to limit scope",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional limit on number of edges",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self: "ExportGraphMCPCommand",
        root_dir: str,
        graph_type: str = "dependencies",
        format: str = "dot",
        file_path: Optional[str] = None,
        limit: Optional[int] = None,
        project_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Export a graph.

        Args:
            self: Command instance.
            root_dir: Project root directory.
            graph_type: Graph type: dependencies, hierarchy, or call_graph.
            format: Output format: dot or json.
            file_path: Optional file path filter.
            limit: Optional limit on number of edges.
            project_id: Optional project UUID.

        Returns:
            SuccessResult with graph data or ErrorResult on failure.
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            db = self._open_database(root_dir)
            try:
                proj_id = self._get_project_id(db, root_path, project_id)
                if not proj_id:
                    return ErrorResult(
                        message="Project not found", code="PROJECT_NOT_FOUND"
                    )

                edge_limit = int(limit) if limit is not None else 5000
                edge_limit = max(1, min(edge_limit, 50000))

                nodes: set[str] = set()
                edges: list[dict[str, str]] = []

                if graph_type == "hierarchy":
                    rows = db._fetchall(
                        """
                        SELECT c.name, c.bases
                        FROM classes c
                        WHERE c.project_id = ?
                        """,
                        (proj_id,),
                    )
                    import json

                    for r in rows:
                        child = r.get("name") if hasattr(r, "get") else r["name"]
                        bases_raw = r.get("bases") if hasattr(r, "get") else r["bases"]
                        if not child:
                            continue
                        child_s = str(child)
                        nodes.add(child_s)
                        if not bases_raw:
                            continue
                        bases: list[str] = []
                        try:
                            bases = json.loads(bases_raw)
                        except Exception:
                            bases = []
                        for b in bases or []:
                            base_s = str(b)
                            if not base_s:
                                continue
                            nodes.add(base_s)
                            edges.append({"from": base_s, "to": child_s})
                            if len(edges) >= edge_limit:
                                break
                        if len(edges) >= edge_limit:
                            break

                elif graph_type == "call_graph":
                    where_extra = ""
                    params: list[Any] = [proj_id]
                    if file_path:
                        where_extra = " AND f.path = ?"
                        params.append(file_path)

                    rows = db._fetchall(
                        """
                        SELECT f.path AS file_path, u.target_name, u.target_class
                        FROM usages u
                        JOIN files f ON f.id = u.file_id
                        WHERE u.project_id = ?
                        """
                        + where_extra,
                        tuple(params),
                    )
                    for r in rows:
                        src = (
                            r.get("file_path") if hasattr(r, "get") else r["file_path"]
                        )
                        target_name = (
                            r.get("target_name")
                            if hasattr(r, "get")
                            else r["target_name"]
                        )
                        target_class = (
                            r.get("target_class")
                            if hasattr(r, "get")
                            else r["target_class"]
                        )
                        if not src or not target_name:
                            continue
                        dst = (
                            f"{target_class}.{target_name}"
                            if target_class
                            else str(target_name)
                        )
                        nodes.add(str(src))
                        nodes.add(str(dst))
                        edges.append({"from": str(src), "to": str(dst)})
                        if len(edges) >= edge_limit:
                            break

                else:
                    where_extra = ""
                    params = [proj_id]
                    if file_path:
                        where_extra = " AND f.path = ?"
                        params.append(file_path)

                    rows = db._fetchall(
                        """
                        SELECT f.path AS file_path, i.module, i.name
                        FROM imports i
                        JOIN files f ON f.id = i.file_id
                        WHERE f.project_id = ?
                        """
                        + where_extra,
                        tuple(params),
                    )
                    for r in rows:
                        src = (
                            r.get("file_path") if hasattr(r, "get") else r["file_path"]
                        )
                        module = r.get("module") if hasattr(r, "get") else r["module"]
                        name = r.get("name") if hasattr(r, "get") else r["name"]
                        dst_val = module or name
                        if not src or not dst_val:
                            continue
                        dst = str(dst_val)
                        nodes.add(str(src))
                        nodes.add(dst)
                        edges.append({"from": str(src), "to": dst})
                        if len(edges) >= edge_limit:
                            break

                node_list = sorted(nodes)

                if format == "json":
                    return SuccessResult(
                        data={
                            "graph_type": graph_type,
                            "format": "json",
                            "nodes": node_list,
                            "edges": edges,
                            "node_count": len(node_list),
                            "edge_count": len(edges),
                        }
                    )

                dot_lines = ["digraph G {"]
                for n in node_list:
                    dot_lines.append(f"  \"{str(n).replace('\\\"', '\\\\"')}\";")
                for e in edges:
                    src = str(e["from"]).replace('\\"', '\\\\"')
                    dst = str(e["to"]).replace('\\"', '\\\\"')
                    dot_lines.append(f'  "{src}" -> "{dst}";')
                dot_lines.append("}")

                return SuccessResult(
                    data={
                        "graph_type": graph_type,
                        "format": "dot",
                        "dot": "\n".join(dot_lines),
                        "node_count": len(node_list),
                        "edge_count": len(edges),
                    }
                )

            finally:
                db.close()

        except Exception as e:
            return self._handle_error(e, "EXPORT_GRAPH_ERROR", "export_graph")
