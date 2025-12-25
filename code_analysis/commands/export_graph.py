"""
Command for exporting dependency graphs and class hierarchies in visualization formats.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database import CodeDatabase  # noqa: F401

logger = logging.getLogger(__name__)


class ExportGraphCommand:
    """Command for exporting graphs in visualization formats."""

    def __init__(
        self,
        database: "CodeDatabase",
        project_id: str,
        graph_type: str = "dependencies",  # "dependencies", "hierarchy", "call_graph"
        format: str = "dot",  # "dot", "json"
        file_path: Optional[str] = None,
        limit: Optional[int] = None,
    ):
        """
        Initialize export graph command.

        Args:
            database: Database instance
            project_id: Project UUID
            graph_type: Type of graph to export
            format: Output format ("dot" for Graphviz, "json" for JSON)
            file_path: Optional file path to limit scope
            limit: Optional limit on number of nodes
        """
        self.database = database
        self.project_id = project_id
        self.graph_type = graph_type
        self.format = format.lower()
        self.file_path = Path(file_path) if file_path else None
        self.limit = limit

    async def execute(self) -> Dict[str, Any]:
        """
        Execute graph export.

        Returns:
            Dictionary with graph data in requested format
        """
        try:
            if self.graph_type == "dependencies":
                return await self._export_dependencies_graph()
            elif self.graph_type == "hierarchy":
                return await self._export_hierarchy_graph()
            elif self.graph_type == "call_graph":
                return await self._export_call_graph()
            else:
                return {
                    "success": False,
                    "message": f"Unknown graph type: {self.graph_type}",
                }
        except Exception as e:
            logger.error(f"Error exporting graph: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error exporting graph: {e}",
                "error": str(e),
            }

    async def _export_dependencies_graph(self) -> Dict[str, Any]:
        """Export module/class dependencies graph."""
        assert self.database.conn is not None
        cursor = self.database.conn.cursor()

        # Get all imports
        query = """
            SELECT DISTINCT i.module, i.name, f.path as file_path
            FROM imports i
            JOIN files f ON i.file_id = f.id
            WHERE f.project_id = ?
        """
        params = [self.project_id]

        if self.file_path:
            query += " AND f.path = ?"
            params.append(str(self.file_path))

        cursor.execute(query, params)
        imports = cursor.fetchall()

        # Build graph
        nodes: Set[str] = set()
        edges: List[Dict[str, str]] = []

        for imp in imports:
            source_file = Path(imp["file_path"]).stem
            target_module = imp["module"] or imp["name"]
            nodes.add(source_file)
            nodes.add(target_module)
            edges.append(
                {
                    "from": source_file,
                    "to": target_module,
                    "label": imp["name"],
                }
            )

        if self.limit and len(nodes) > self.limit:
            # Limit nodes (keep most connected)
            node_counts: Dict[str, int] = {}
            for edge in edges:
                node_counts[edge["from"]] = node_counts.get(edge["from"], 0) + 1
                node_counts[edge["to"]] = node_counts.get(edge["to"], 0) + 1

            top_nodes = sorted(node_counts.items(), key=lambda x: x[1], reverse=True)[
                : self.limit
            ]
            top_node_set = {node for node, _ in top_nodes}
            nodes = nodes & top_node_set
            edges = [
                e
                for e in edges
                if e["from"] in top_node_set and e["to"] in top_node_set
            ]

        if self.format == "dot":
            dot_content = self._generate_dot(nodes, edges, "Module Dependencies")
            return {
                "success": True,
                "message": f"Exported {len(nodes)} nodes, {len(edges)} edges",
                "format": "dot",
                "content": dot_content,
            }
        else:  # json
            return {
                "success": True,
                "message": f"Exported {len(nodes)} nodes, {len(edges)} edges",
                "format": "json",
                "graph": {
                    "nodes": list(nodes),
                    "edges": edges,
                },
            }

    async def _export_hierarchy_graph(self) -> Dict[str, Any]:
        """Export class hierarchy graph."""
        assert self.database.conn is not None
        cursor = self.database.conn.cursor()

        # Get all classes with their bases
        query = """
            SELECT c.name, c.bases, f.path as file_path
            FROM classes c
            JOIN files f ON c.file_id = f.id
            WHERE f.project_id = ?
        """
        params = [self.project_id]

        if self.file_path:
            query += " AND f.path = ?"
            params.append(str(self.file_path))

        cursor.execute(query, params)
        classes = cursor.fetchall()

        nodes: Set[str] = set()
        edges: List[Dict[str, str]] = []

        for cls in classes:
            class_name = cls["name"]
            nodes.add(class_name)
            bases = json.loads(cls["bases"]) if cls["bases"] else []
            for base in bases:
                # Handle different base formats
                if isinstance(base, str):
                    base_name = base
                elif isinstance(base, dict):
                    # Extract name from AST node representation
                    base_name = base.get("id", base.get("name", str(base)))
                else:
                    base_name = str(base)
                # Skip if base is not a valid identifier
                if (
                    base_name
                    and not base_name.startswith("<")
                    and not base_name.startswith("{")
                ):
                    nodes.add(base_name)
                    edges.append(
                        {
                            "from": base_name,
                            "to": class_name,
                            "label": "inherits",
                        }
                    )

        if self.limit and len(nodes) > self.limit:
            # Limit to most connected nodes
            node_counts: Dict[str, int] = {}
            for edge in edges:
                node_counts[edge["from"]] = node_counts.get(edge["from"], 0) + 1
                node_counts[edge["to"]] = node_counts.get(edge["to"], 0) + 1

            top_nodes = sorted(node_counts.items(), key=lambda x: x[1], reverse=True)[
                : self.limit
            ]
            top_node_set = {node for node, _ in top_nodes}
            nodes = nodes & top_node_set
            edges = [
                e
                for e in edges
                if e["from"] in top_node_set and e["to"] in top_node_set
            ]

        if self.format == "dot":
            dot_content = self._generate_dot(nodes, edges, "Class Hierarchy")
            return {
                "success": True,
                "message": f"Exported {len(nodes)} nodes, {len(edges)} edges",
                "format": "dot",
                "content": dot_content,
            }
        else:  # json
            return {
                "success": True,
                "message": f"Exported {len(nodes)} nodes, {len(edges)} edges",
                "format": "json",
                "graph": {
                    "nodes": list(nodes),
                    "edges": edges,
                },
            }

    async def _export_call_graph(self) -> Dict[str, Any]:
        """Export function/method call graph."""
        assert self.database.conn is not None
        cursor = self.database.conn.cursor()

        # Get all usages (method calls)
        query = """
            SELECT u.target_name, u.target_class, f.path as file_path
            FROM usages u
            JOIN files f ON u.file_id = f.id
            WHERE f.project_id = ? AND u.usage_type = 'method_call'
        """
        params = [self.project_id]

        if self.file_path:
            query += " AND f.path = ?"
            params.append(str(self.file_path))

        cursor.execute(query, params)
        usages = cursor.fetchall()

        nodes: Set[str] = set()
        edges: List[Dict[str, str]] = []

        for usage in usages:
            source_file = Path(usage["file_path"]).stem
            target = usage["target_name"]
            if usage["target_class"]:
                target = f"{usage['target_class']}.{target}"
            nodes.add(source_file)
            nodes.add(target)
            edges.append(
                {
                    "from": source_file,
                    "to": target,
                    "label": "calls",
                }
            )

        if self.limit and len(nodes) > self.limit:
            node_counts: Dict[str, int] = {}
            for edge in edges:
                node_counts[edge["from"]] = node_counts.get(edge["from"], 0) + 1
                node_counts[edge["to"]] = node_counts.get(edge["to"], 0) + 1

            top_nodes = sorted(node_counts.items(), key=lambda x: x[1], reverse=True)[
                : self.limit
            ]
            top_node_set = {node for node, _ in top_nodes}
            nodes = nodes & top_node_set
            edges = [
                e
                for e in edges
                if e["from"] in top_node_set and e["to"] in top_node_set
            ]

        if self.format == "dot":
            dot_content = self._generate_dot(nodes, edges, "Call Graph")
            return {
                "success": True,
                "message": f"Exported {len(nodes)} nodes, {len(edges)} edges",
                "format": "dot",
                "content": dot_content,
            }
        else:  # json
            return {
                "success": True,
                "message": f"Exported {len(nodes)} nodes, {len(edges)} edges",
                "format": "json",
                "graph": {
                    "nodes": list(nodes),
                    "edges": edges,
                },
            }

    def _generate_dot(
        self, nodes: Set[str], edges: List[Dict[str, str]], title: str
    ) -> str:
        """Generate Graphviz DOT format."""
        lines = [f'digraph "{title}" {{']
        lines.append("  rankdir=LR;")
        lines.append("  node [shape=box];")
        lines.append("")

        # Add nodes
        for node in sorted(nodes):
            # Escape special characters for DOT
            node_escaped = node.replace('"', '\\"').replace("\n", " ")
            lines.append(f'  "{node_escaped}";')

        lines.append("")

        # Add edges
        for edge in edges:
            from_node = edge["from"].replace('"', '\\"').replace("\n", " ")
            to_node = edge["to"].replace('"', '\\"').replace("\n", " ")
            label = edge.get("label", "").replace('"', '\\"').replace("\n", " ")
            if label:
                lines.append(f'  "{from_node}" -> "{to_node}" [label="{label}"];')
            else:
                lines.append(f'  "{from_node}" -> "{to_node}";')

        lines.append("}")
        return "\n".join(lines)
