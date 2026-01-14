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
                db.disconnect()

        except Exception as e:
            return self._handle_error(e, "EXPORT_GRAPH_ERROR", "export_graph")

    @classmethod
    def metadata(cls: type["ExportGraphMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The export_graph command exports dependency graphs, class hierarchies, or call graphs "
                "in DOT (Graphviz) or JSON format. The command provides stable output without failing "
                "when the underlying project contains partial or missing data.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Applies edge limit (default 5000, max 50000, min 1)\n"
                "5. Based on graph_type:\n"
                "   - 'dependencies': Extracts file-to-module import relationships\n"
                "   - 'hierarchy': Extracts class inheritance relationships\n"
                "   - 'call_graph': Extracts file-to-entity usage relationships\n"
                "6. If file_path provided, filters results to that file\n"
                "7. Formats output as DOT (Graphviz) or JSON\n"
                "8. Returns graph with nodes and edges\n\n"
                "Graph Types:\n"
                "- dependencies: Shows which files import which modules. "
                "Nodes are file paths and module names. Edges represent imports.\n"
                "- hierarchy: Shows class inheritance relationships. "
                "Nodes are class names. Edges go from base class to derived class.\n"
                "- call_graph: Shows which files use which entities. "
                "Nodes are file paths and entity names. Edges represent usages.\n\n"
                "Output Formats:\n"
                "- dot: Graphviz DOT format, can be rendered with tools like Graphviz, "
                "PlantUML, or online viewers\n"
                "- json: Structured JSON with nodes array and edges array\n\n"
                "Important notes:\n"
                "- Edge limit prevents memory issues with large projects\n"
                "- Graph is stable: missing data doesn't cause failures\n"
                "- DOT format escapes special characters in node names\n"
                "- JSON format provides structured data for programmatic use"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative. "
                        "Must contain data/code_analysis.db file."
                    ),
                    "type": "string",
                    "required": True,
                },
                "graph_type": {
                    "description": (
                        "Type of graph to export. Options: 'dependencies' (file imports), "
                        "'hierarchy' (class inheritance), 'call_graph' (entity usages). "
                        "Default is 'dependencies'."
                    ),
                    "type": "string",
                    "required": False,
                    "enum": ["dependencies", "hierarchy", "call_graph"],
                    "default": "dependencies",
                },
                "format": {
                    "description": (
                        "Output format. Options: 'dot' (Graphviz DOT format) or 'json' (structured JSON). "
                        "Default is 'dot'. DOT format can be rendered with Graphviz tools. "
                        "JSON format is better for programmatic processing."
                    ),
                    "type": "string",
                    "required": False,
                    "enum": ["dot", "json"],
                    "default": "dot",
                },
                "file_path": {
                    "description": (
                        "Optional file path to limit graph scope. If provided, only includes "
                        "relationships involving this file. Can be absolute or relative to root_dir."
                    ),
                    "type": "string",
                    "required": False,
                },
                "limit": {
                    "description": (
                        "Optional limit on number of edges. Default is 5000. "
                        "Maximum is 50000, minimum is 1. Prevents memory issues with large projects."
                    ),
                    "type": "integer",
                    "required": False,
                },
                "project_id": {
                    "description": (
                        "Optional project UUID. If omitted, inferred from root_dir."
                    ),
                    "type": "string",
                    "required": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Export dependency graph in DOT format",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "graph_type": "dependencies",
                        "format": "dot",
                    },
                    "explanation": (
                        "Exports file-to-module import relationships in Graphviz DOT format. "
                        "Can be saved to file and rendered with 'dot -Tpng graph.dot -o graph.png'."
                    ),
                },
                {
                    "description": "Export class hierarchy in JSON format",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "graph_type": "hierarchy",
                        "format": "json",
                    },
                    "explanation": (
                        "Exports class inheritance relationships as structured JSON. "
                        "Useful for programmatic analysis or custom visualization."
                    ),
                },
                {
                    "description": "Export call graph for specific file",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "graph_type": "call_graph",
                        "file_path": "src/main.py",
                        "format": "json",
                    },
                    "explanation": (
                        "Exports call graph limited to relationships involving src/main.py. "
                        "Shows what entities this file uses."
                    ),
                },
                {
                    "description": "Export with edge limit",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "graph_type": "dependencies",
                        "limit": 1000,
                    },
                    "explanation": (
                        "Limits output to 1000 edges to reduce memory usage and simplify visualization."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "EXPORT_GRAPH_ERROR": {
                    "description": "General error during graph export",
                    "example": "Database error, invalid graph_type, or corrupted data",
                    "solution": (
                        "Check database integrity, verify parameters, ensure project has been analyzed. "
                        "For large projects, try reducing limit parameter."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data_dot": {
                        "graph_type": "Graph type (dependencies/hierarchy/call_graph)",
                        "format": "Always 'dot'",
                        "dot": "Graphviz DOT format string",
                        "node_count": "Number of nodes in graph",
                        "edge_count": "Number of edges in graph",
                    },
                    "data_json": {
                        "graph_type": "Graph type",
                        "format": "Always 'json'",
                        "nodes": "List of node names (strings)",
                        "edges": "List of edge dictionaries with 'from' and 'to' keys",
                        "node_count": "Number of nodes",
                        "edge_count": "Number of edges",
                    },
                    "example_dot": {
                        "graph_type": "dependencies",
                        "format": "dot",
                        "dot": "digraph G {\n  \"src/main.py\";\n  \"os\";\n  \"src/main.py\" -> \"os\";\n}",
                        "node_count": 2,
                        "edge_count": 1,
                    },
                    "example_json": {
                        "graph_type": "hierarchy",
                        "format": "json",
                        "nodes": ["BaseClass", "DerivedClass"],
                        "edges": [{"from": "BaseClass", "to": "DerivedClass"}],
                        "node_count": 2,
                        "edge_count": 1,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, EXPORT_GRAPH_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use DOT format for visualization with Graphviz or online tools",
                "Use JSON format for programmatic analysis or custom visualizations",
                "Set limit parameter for large projects to avoid memory issues",
                "Use file_path filter to focus on specific file relationships",
                "Export hierarchy graphs to understand class inheritance structure",
                "Export dependencies graphs to understand module import structure",
                "Export call_graph to understand entity usage patterns",
            ],
        }
