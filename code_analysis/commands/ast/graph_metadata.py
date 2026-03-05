"""
Export_graph command metadata for AI models.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict


def get_export_graph_metadata(
    name: str,
    version: str,
    descr: str,
    category: str,
    author: str,
    email: str,
) -> Dict[str, Any]:
    """Build full metadata dict for export_graph command."""
    return {
        "name": name,
        "version": version,
        "description": descr,
        "category": category,
        "author": author,
        "email": email,
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
                    "entity_nodes": "List of entity node payloads: {node_id, file_path, cst_node_id} (UUID4); only for nodes with valid cst_node_id",
                    "node_count": "Number of nodes",
                    "edge_count": "Number of edges",
                },
                "example_dot": {
                    "graph_type": "dependencies",
                    "format": "dot",
                    "dot": 'digraph G {\n  "src/main.py";\n  "os";\n  "src/main.py" -> "os";\n}',
                    "node_count": 2,
                    "edge_count": 1,
                },
                "example_json": {
                    "graph_type": "hierarchy",
                    "format": "json",
                    "nodes": ["BaseClass", "DerivedClass"],
                    "edges": [{"from": "BaseClass", "to": "DerivedClass"}],
                    "entity_nodes": [
                        {
                            "node_id": "DerivedClass",
                            "file_path": "src/foo.py",
                            "cst_node_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                        }
                    ],
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
