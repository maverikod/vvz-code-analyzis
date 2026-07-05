"""
MCP command wrapper: export_graph.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import uuid
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ...core.exceptions import ValidationError
from .graph_entity_nodes import (
    build_entity_nodes_call_graph,
    build_entity_nodes_hierarchy,
)
from .graph_metadata import get_export_graph_metadata


def _is_valid_uuid4(value: Optional[str]) -> bool:
    """Return True if value is non-empty and valid UUID4 string; otherwise False."""
    if not value or not isinstance(value, str):
        return False
    s = value.strip()
    if not s:
        return False
    try:
        u = uuid.UUID(s, version=4)
        return str(u) == s
    except (ValueError, TypeError):
        return False


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
        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base_props,
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
                    "description": (
                        "Optional limit on number of edges (1–50000). Default 5000. "
                        "Values outside the range are rejected."
                    ),
                    "default": 5000,
                    "minimum": 1,
                    "maximum": 50000,
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Reject ``limit`` outside schema min/max after schema validation."""
        params = super().validate_params(params)
        schema = self.get_schema()
        props = schema.get("properties") or {}
        key = "limit"
        if key not in params or params[key] is None:
            return params
        value = params[key]
        prop = props.get(key) or {}
        minimum = prop.get("minimum")
        maximum = prop.get("maximum")
        if minimum is not None and value < minimum:
            raise ValidationError(
                f"{self.name}: parameter {key!r} must be >= {minimum}, got {value!r}",
                field=key,
                details={"minimum": minimum, "maximum": maximum},
            )
        if maximum is not None and value > maximum:
            raise ValidationError(
                f"{self.name}: parameter {key!r} must be <= {maximum}, got {value!r}",
                field=key,
                details={"minimum": minimum, "maximum": maximum},
            )
        return params

    async def execute(
        self: "ExportGraphMCPCommand",
        project_id: str,
        graph_type: str = "dependencies",
        format: str = "dot",
        file_path: Optional[str] = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Export a graph.

        Args:
            self: Command instance.
            project_id: Project UUID.
            graph_type: Graph type: dependencies, hierarchy, or call_graph.
            format: Output format: dot or json.
            file_path: Optional file path filter.
            limit: Optional limit on number of edges.

        Returns:
            SuccessResult with graph data or ErrorResult on failure.
        """
        call_params: Dict[str, Any] = {
            "project_id": project_id,
            "graph_type": graph_type,
            "format": format,
            "file_path": file_path,
            "limit": limit,
        }
        call_params.update(kwargs)
        try:
            call_params = self.validate_params(call_params)
        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details=getattr(e, "details", None)
                or {"field": getattr(e, "field", None)},
            )
        project_id = call_params["project_id"]
        graph_type = str(call_params.get("graph_type") or "dependencies")
        format = str(call_params.get("format") or "dot")
        file_path = call_params.get("file_path")
        limit = call_params.get("limit")

        try:
            _ = self._resolve_project_root(project_id)
            db = self._open_database()
            try:
                proj_id = project_id

                edge_limit = int(limit) if limit is not None else 5000

                nodes: set[str] = set()
                edges: list[dict[str, str]] = []
                entity_nodes: List[Dict[str, str]] = []

                if graph_type == "hierarchy":
                    result = db.execute(
                        """
                        SELECT c.name, c.bases, f.path AS file_path, c.cst_node_id
                        FROM classes c
                        JOIN files f ON f.id = c.file_id
                        WHERE f.project_id = ?
                        """,
                        (proj_id,),
                    )
                    rows = result.get("data", [])
                    entity_nodes = build_entity_nodes_hierarchy(rows, _is_valid_uuid4)

                    for r in rows:
                        child = r.get("name") if hasattr(r, "get") else r["name"]
                        bases_raw = r.get("bases") if hasattr(r, "get") else r["bases"]
                        if not child:
                            continue
                        child_s = str(child)
                        nodes.add(child_s)
                        if not bases_raw:
                            continue
                        bases_list: list[str] = []
                        try:
                            bases_list = json.loads(bases_raw)
                        except Exception:
                            bases_list = []
                        for b in bases_list or []:
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

                    result = db.execute(
                        """
                        SELECT f.path AS file_path, u.target_name, u.target_class
                        FROM usages u
                        JOIN files f ON f.id = u.file_id
                        WHERE f.project_id = ?
                        """
                        + where_extra,
                        tuple(params),
                    )
                    rows = result.get("data", [])
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

                    to_node_ids = {str(e["to"]) for e in edges}
                    entity_nodes = build_entity_nodes_call_graph(
                        db, proj_id, to_node_ids, _is_valid_uuid4
                    )

                else:
                    where_extra = ""
                    params = [proj_id]
                    if file_path:
                        where_extra = " AND f.path = ?"
                        params.append(file_path)

                    result = db.execute(
                        """
                        SELECT f.path AS file_path, i.module, i.name
                        FROM imports i
                        JOIN files f ON f.id = i.file_id
                        WHERE f.project_id = ?
                        """
                        + where_extra,
                        tuple(params),
                    )
                    rows = result.get("data", [])
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
                            "entity_nodes": entity_nodes,
                            "node_count": len(node_list),
                            "edge_count": len(edges),
                        }
                    )

                dot_lines = ["digraph G {"]
                for n in node_list:
                    node_label = str(n).replace('\\"', '\\\\"')
                    dot_lines.append(f'  "{node_label}";')
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
        """Return detailed command metadata for AI models."""
        return get_export_graph_metadata(
            cls.name,
            cls.version,
            cls.descr,
            cls.category,
            cls.author,
            cls.email,
        )
