"""
MCP server for code analysis tool.

Provides code analysis functionality as MCP tools using FastMCP framework.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP, Context

from .api import CodeAnalysisAPI

logger = logging.getLogger(__name__)


def analyze_project(
    root_dir: str,
    max_lines: int = 400,
    comment: Optional[str] = None,
    context: Context | None = None,
) -> Dict[str, Any]:
    """
    Analyze Python project and generate code map.

    Args:
        root_dir: Root directory of the project to analyze
        max_lines: Maximum lines per file (default: 400)
        comment: Optional human-readable comment/identifier for project
        context: MCP context for logging and progress reporting

    Returns:
        Dictionary with analysis results including files_analyzed,
        classes, functions, and issues.
    """
    logger.info(f"Starting analysis of project: {root_dir}")

    api = CodeAnalysisAPI(root_dir, max_lines=max_lines, comment=comment)
    try:
        result = api.analyze_project()
        logger.info(
            f"Analysis complete: {result.get('files_analyzed', 0)} files, "
            f"{result.get('classes', 0)} classes, "
            f"{result.get('functions', 0)} functions"
        )
        return result
    finally:
        api.close()


def find_usages(
    root_dir: str,
    name: str,
    target_type: Optional[str] = None,
    target_class: Optional[str] = None,
    context: Context | None = None,
) -> List[Dict[str, Any]]:
    """
    Find all usages of a method or property.

    Args:
        root_dir: Root directory of the project
        name: Name of method/property to find
        target_type: Filter by target type (method, property, function)
        target_class: Filter by class name
        context: MCP context for logging

    Returns:
        List of usage records with file, line, and context information
    """
    logger.info(f"Searching for usages of '{name}' in {root_dir}")

    api = CodeAnalysisAPI(root_dir)
    try:
        usages = api.find_usages(name, target_type, target_class)
        logger.info(f"Found {len(usages)} usages")
        return usages
    finally:
        api.close()


def full_text_search(
    root_dir: str,
    query: str,
    entity_type: Optional[str] = None,
    limit: int = 20,
    context: Context | None = None,
) -> List[Dict[str, Any]]:
    """
    Perform full-text search in code content and docstrings.

    Args:
        root_dir: Root directory of the project
        query: Search query text
        entity_type: Filter by entity type (class, method, function)
        limit: Maximum number of results (default: 20)
        context: MCP context for logging

    Returns:
        List of matching records with relevance scores
    """
    logger.info(f"Performing full-text search for '{query}' in {root_dir}")

    api = CodeAnalysisAPI(root_dir)
    try:
        results = api.full_text_search(query, entity_type, limit)
        logger.info(f"Found {len(results)} results")
        return results
    finally:
        api.close()


def search_classes(
    root_dir: str,
    pattern: Optional[str] = None,
    context: Context | None = None,
) -> List[Dict[str, Any]]:
    """
    Search classes by name pattern.

    Args:
        root_dir: Root directory of the project
        pattern: Name pattern to search (optional, returns all if not provided)
        context: MCP context for logging

    Returns:
        List of class records with name, file, and inheritance information
    """
    logger.info(
        f"Searching classes in {root_dir}"
        + (f" with pattern '{pattern}'" if pattern else "")
    )

    api = CodeAnalysisAPI(root_dir)
    try:
        classes = api.search_classes(pattern)
        logger.info(f"Found {len(classes)} classes")
        return classes
    finally:
        api.close()


def search_methods(
    root_dir: str,
    pattern: Optional[str] = None,
    context: Context | None = None,
) -> List[Dict[str, Any]]:
    """
    Search methods by name pattern.

    Args:
        root_dir: Root directory of the project
        pattern: Name pattern to search (optional, returns all if not provided)
        context: MCP context for logging

    Returns:
        List of method records with name, class, file, and signature information
    """
    logger.info(
        f"Searching methods in {root_dir}"
        + (f" with pattern '{pattern}'" if pattern else "")
    )

    api = CodeAnalysisAPI(root_dir)
    try:
        methods = api.search_methods(pattern)
        logger.info(f"Found {len(methods)} methods")
        return methods
    finally:
        api.close()


def get_issues(
    root_dir: str,
    issue_type: Optional[str] = None,
    context: Context | None = None,
) -> Dict[str, Any] | List[Dict[str, Any]]:
    """
    Get code quality issues from analysis.

    Args:
        root_dir: Root directory of the project
        issue_type: Filter by issue type (optional, returns all if not provided)
        context: MCP context for logging

    Returns:
        Dictionary of issues grouped by type, or list if issue_type is specified
    """
    logger.info(
        f"Retrieving issues from {root_dir}"
        + (f" (type: {issue_type})" if issue_type else "")
    )

    api = CodeAnalysisAPI(root_dir)
    try:
        issues = api.get_issues(issue_type)
        if isinstance(issues, dict):
            total = sum(len(v) if isinstance(v, list) else 1 for v in issues.values())
            logger.info(f"Found {total} issues across {len(issues)} types")
        else:
            logger.info(f"Found {len(issues)} issues")
        return issues
    finally:
        api.close()


def split_class(
    root_dir: str,
    file_path: str,
    config: Dict[str, Any],
    context: Context | None = None,
) -> Dict[str, Any]:
    """
    Split a class into multiple smaller classes.

    Args:
        root_dir: Root directory of the project
        file_path: Path to Python file to refactor (relative to root_dir or absolute)
        config: Split configuration with src_class and dst_classes
        context: MCP context for logging and progress

    Returns:
        Dictionary with success status and message
    """
    logger.info(f"Splitting class in {file_path}")

    api = CodeAnalysisAPI(root_dir)
    try:
        result = api.split_class(file_path, config)
        return result
    finally:
        api.close()


def extract_superclass(
    root_dir: str,
    file_path: str,
    config: Dict[str, Any],
    context: Context | None = None,
) -> Dict[str, Any]:
    """
    Extract common functionality into base class.

    Args:
        root_dir: Root directory of the project
        file_path: Path to Python file to refactor (relative to root_dir or absolute)
        config: Extraction configuration
        context: MCP context for logging and progress

    Returns:
        Dictionary with success status and message
    """
    logger.info(f"Extracting superclass in {file_path}")

    api = CodeAnalysisAPI(root_dir)
    try:
        result = api.extract_superclass(file_path, config)
        return result
    finally:
        api.close()


def merge_classes(
    root_dir: str,
    file_path: str,
    config: Dict[str, Any],
    context: Context | None = None,
) -> Dict[str, Any]:
    """
    Merge multiple classes into a single base class.

    Args:
        root_dir: Root directory of the project
        file_path: Path to Python file to refactor (relative to root_dir or absolute)
        config: Merge configuration
        context: MCP context for logging and progress

    Returns:
        Dictionary with success status and message
    """
    logger.info(f"Merging classes in {file_path}")

    api = CodeAnalysisAPI(root_dir)
    try:
        result = api.merge_classes(file_path, config)
        return result
    finally:
        api.close()


def main() -> None:
    """Main function to run MCP server."""
    import argparse

    parser = argparse.ArgumentParser(description="Code Analysis MCP Server")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=15000,
        help="Server port (default: 15000)",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="streamable-http",
        help="Transport protocol (default: streamable-http)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Log level (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info(
        f"Starting MCP server on {args.host}:{args.port} "
        f"with transport {args.transport}"
    )

    # Create new FastMCP instance with custom settings
    server = FastMCP(
        name="code-analysis",
        instructions="Code analysis tool for Python projects. Provides code mapping, "
        "issue detection, usage analysis, and refactoring capabilities.",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )

    # Register all tools using add_tool method
    server.add_tool(analyze_project)
    server.add_tool(find_usages)
    server.add_tool(full_text_search)
    server.add_tool(search_classes)
    server.add_tool(search_methods)
    server.add_tool(get_issues)
    server.add_tool(split_class)
    server.add_tool(extract_superclass)
    server.add_tool(merge_classes)

    # Run server
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
