"""
MCP server for code analysis tool.

Provides code analysis functionality as MCP tools using FastMCP framework.

This server offers comprehensive code analysis capabilities for Python projects:
- Project analysis and code mapping
- Code search (classes, methods, functions, full-text)
- Usage analysis and dependency tracking
- Code quality issue detection
- Code refactoring operations (split, extract, merge classes)
- Project management (add, remove, update projects)

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP, Context
from pathlib import Path

from .api import CodeAnalysisAPI
from .commands.project import ProjectCommand
from .commands.update_ast import UpdateASTCommand
from .commands.get_ast import GetASTCommand
from .commands.search_ast_nodes import SearchASTNodesCommand
from .commands.ast_statistics import ASTStatisticsCommand

logger = logging.getLogger(__name__)

# Default timeouts in seconds
DEFAULT_TIMEOUT = 300  # 5 minutes for long operations
SHORT_TIMEOUT = 60  # 1 minute for quick operations
LONG_TIMEOUT = 600  # 10 minutes for very long operations (analyze_project)


async def analyze_project(
    root_dir: str,
    max_lines: int = 400,
    comment: Optional[str] = None,
    force: bool = False,
    context: Context | None = None,
    timeout: int = LONG_TIMEOUT,
) -> Dict[str, Any]:
    """
    Analyze Python project and generate comprehensive code map.

    This tool scans a Python project directory, extracts code structure,
    and stores it in a database for further analysis. It identifies:
    - All Python files and their metadata
    - Classes with their inheritance relationships
    - Methods and functions with signatures
    - Imports and dependencies
    - Code quality issues (missing docstrings, large files, etc.)

    The analysis creates a searchable index that enables fast code navigation,
    usage tracking, and refactoring operations.

    Args:
        root_dir: Root directory of the project to analyze (absolute path)
        max_lines: Maximum lines per file threshold (default: 400).
                  Files exceeding this will be flagged as issues.
        comment: Optional human-readable comment/identifier for the project
        force: If True, process all files regardless of modification time.
               By default, files are only processed if they are newer than
               stored AST trees (default: False)
        context: MCP context for logging and progress reporting
        timeout: Operation timeout in seconds (default: 600)

    Returns:
        Dictionary with analysis results:
        - files_analyzed: Number of Python files processed
        - classes: Total number of classes found
        - functions: Total number of functions found
        - issues: Total number of code quality issues detected
        - project_id: UUID identifier for the project

    Example:
        result = await analyze_project(
            root_dir="/path/to/project",
            max_lines=500,
            comment="Main application",
            force=False  # Only process changed files
        )
        # Returns: {"files_analyzed": 42, "classes": 15, "functions": 87, ...}
        
        # Force re-analysis of all files:
        result = await analyze_project(
            root_dir="/path/to/project",
            force=True  # Process all files regardless of modification time
        )
    """
    if context:
        await context.info(f"Starting analysis of project: {root_dir}")
    else:
        logger.info(f"Starting analysis of project: {root_dir}")

    api = CodeAnalysisAPI(root_dir, max_lines=max_lines, comment=comment)
    try:
        result = await asyncio.wait_for(
            api.analyze_project(force=force), timeout=timeout
        )
        message = (
            f"Analysis complete: {result.get('files_analyzed', 0)} files, "
            f"{result.get('classes', 0)} classes, "
            f"{result.get('functions', 0)} functions"
        )
        if context:
            await context.info(message)
        else:
            logger.info(message)
        return result
    except asyncio.TimeoutError:
        error_msg = f"Analysis timeout after {timeout} seconds"
        if context:
            await context.error(error_msg)
        else:
            logger.error(error_msg)
        raise TimeoutError(error_msg)
    finally:
        api.close()


async def find_usages(
    root_dir: str,
    name: str,
    target_type: Optional[str] = None,
    target_class: Optional[str] = None,
    context: Context | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> List[Dict[str, Any]]:
    """
    Find all usages of a method, property, or function across the project.

    This tool searches the codebase to find everywhere a specific method,
    property, or function is called or referenced. Useful for:
    - Understanding code dependencies
    - Refactoring safety checks
    - Impact analysis before changes

    Args:
        root_dir: Root directory of the project (must be analyzed first)
        name: Name of method/property/function to find (exact match)
        target_type: Filter by target type - "method", "property", or "function"
        target_class: Filter by class name (only for methods/properties)
        context: MCP context for logging
        timeout: Operation timeout in seconds (default: 300)

    Returns:
        List of usage records, each containing:
        - file_path: Path to file where usage was found
        - line: Line number of usage
        - usage_type: Type of usage (call, attribute, etc.)
        - context: Surrounding code context

    Example:
        usages = await find_usages(
            root_dir="/path/to/project",
            name="process_data",
            target_type="method",
            target_class="DataProcessor"
        )
        # Returns list of all places where DataProcessor.process_data is called
    """
    if context:
        await context.info(f"Searching for usages of '{name}' in {root_dir}")
    else:
        logger.info(f"Searching for usages of '{name}' in {root_dir}")

    api = CodeAnalysisAPI(root_dir)
    try:
        usages = await asyncio.wait_for(
            api.find_usages(name, target_type, target_class), timeout=timeout
        )
        message = f"Found {len(usages)} usages"
        if context:
            await context.info(message)
        else:
            logger.info(message)
        return usages
    except asyncio.TimeoutError:
        error_msg = f"Find usages timeout after {timeout} seconds"
        if context:
            await context.error(error_msg)
        else:
            logger.error(error_msg)
        raise TimeoutError(error_msg)
    finally:
        api.close()


async def full_text_search(
    root_dir: str,
    query: str,
    entity_type: Optional[str] = None,
    limit: int = 20,
    context: Context | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> List[Dict[str, Any]]:
    """
    Perform full-text search in code content and docstrings.

    This tool searches through actual code content and documentation,
    not just names. It uses SQLite FTS5 for fast text search across:
    - Class definitions and docstrings
    - Method/function implementations
    - Comments and documentation strings

    Useful for finding code by functionality rather than exact names.

    Args:
        root_dir: Root directory of the project (must be analyzed first)
        query: Search query text (supports SQLite FTS5 syntax)
        entity_type: Filter by entity type - "class", "method", or "function"
        limit: Maximum number of results to return (default: 20)
        context: MCP context for logging
        timeout: Operation timeout in seconds (default: 300)

    Returns:
        List of matching records with relevance scores, each containing:
        - entity_type: Type of entity (class, method, function)
        - entity_name: Name of the entity
        - content: Matching code content
        - docstring: Documentation string if available
        - file_path: Path to file containing the match

    Example:
        results = await full_text_search(
            root_dir="/path/to/project",
            query="database connection",
            entity_type="class",
            limit=10
        )
        # Returns classes/methods that mention "database connection"
    """
    if context:
        await context.info(f"Performing full-text search for '{query}' in {root_dir}")
    else:
        logger.info(f"Performing full-text search for '{query}' in {root_dir}")

    api = CodeAnalysisAPI(root_dir)
    try:
        results = await asyncio.wait_for(
            api.full_text_search(query, entity_type, limit), timeout=timeout
        )
        message = f"Found {len(results)} results"
        if context:
            await context.info(message)
        else:
            logger.info(message)
        return results
    except asyncio.TimeoutError:
        error_msg = f"Full-text search timeout after {timeout} seconds"
        if context:
            await context.error(error_msg)
        else:
            logger.error(error_msg)
        raise TimeoutError(error_msg)
    finally:
        api.close()


async def search_classes(
    root_dir: str,
    pattern: Optional[str] = None,
    context: Context | None = None,
    timeout: int = SHORT_TIMEOUT,
) -> List[Dict[str, Any]]:
    """
    Search classes by name pattern.

    This tool finds classes in the codebase by name. Supports pattern matching
    to find classes with similar names. Useful for:
    - Discovering class hierarchies
    - Finding related classes
    - Understanding project structure

    Args:
        root_dir: Root directory of the project (must be analyzed first)
        pattern: Name pattern to search (SQL LIKE pattern, e.g., "%Manager%")
                 If None, returns all classes
        context: MCP context for logging
        timeout: Operation timeout in seconds (default: 60)

    Returns:
        List of class records, each containing:
        - name: Class name
        - file_path: Path to file containing the class
        - line: Line number where class is defined
        - bases: Base classes (inheritance)
        - docstring: Class documentation

    Example:
        classes = await search_classes(
            root_dir="/path/to/project",
            pattern="%Handler%"
        )
        # Returns all classes with "Handler" in the name
    """
    message = f"Searching classes in {root_dir}" + (
        f" with pattern '{pattern}'" if pattern else ""
    )
    if context:
        await context.info(message)
    else:
        logger.info(message)

    api = CodeAnalysisAPI(root_dir)
    try:
        classes = await asyncio.wait_for(api.search_classes(pattern), timeout=timeout)
        result_message = f"Found {len(classes)} classes"
        if context:
            await context.info(result_message)
        else:
            logger.info(result_message)
        return classes
    except asyncio.TimeoutError:
        error_msg = f"Search classes timeout after {timeout} seconds"
        if context:
            await context.error(error_msg)
        else:
            logger.error(error_msg)
        raise TimeoutError(error_msg)
    finally:
        api.close()


async def search_methods(
    root_dir: str,
    pattern: Optional[str] = None,
    context: Context | None = None,
    timeout: int = SHORT_TIMEOUT,
) -> List[Dict[str, Any]]:
    """
    Search methods by name pattern.

    This tool finds methods across all classes in the codebase by name pattern.
    Useful for:
    - Finding methods with similar functionality
    - Discovering method naming patterns
    - Locating specific method implementations

    Args:
        root_dir: Root directory of the project (must be analyzed first)
        pattern: Name pattern to search (SQL LIKE pattern, e.g., "%get_%")
                 If None, returns all methods
        context: MCP context for logging
        timeout: Operation timeout in seconds (default: 60)

    Returns:
        List of method records, each containing:
        - name: Method name
        - class_name: Name of containing class
        - file_path: Path to file containing the method
        - line: Line number where method is defined
        - args: Method arguments/signature
        - docstring: Method documentation
        - is_abstract: Whether method is abstract

    Example:
        methods = await search_methods(
            root_dir="/path/to/project",
            pattern="%validate%"
        )
        # Returns all methods with "validate" in the name
    """
    message = f"Searching methods in {root_dir}" + (
        f" with pattern '{pattern}'" if pattern else ""
    )
    if context:
        await context.info(message)
    else:
        logger.info(message)

    api = CodeAnalysisAPI(root_dir)
    try:
        methods = await asyncio.wait_for(api.search_methods(pattern), timeout=timeout)
        result_message = f"Found {len(methods)} methods"
        if context:
            await context.info(result_message)
        else:
            logger.info(result_message)
        return methods
    except asyncio.TimeoutError:
        error_msg = f"Search methods timeout after {timeout} seconds"
        if context:
            await context.error(error_msg)
        else:
            logger.error(error_msg)
        raise TimeoutError(error_msg)
    finally:
        api.close()


async def get_issues(
    root_dir: str,
    issue_type: Optional[str] = None,
    context: Context | None = None,
    timeout: int = SHORT_TIMEOUT,
) -> Dict[str, Any] | List[Dict[str, Any]]:
    """
    Get code quality issues detected during analysis.

    This tool retrieves code quality issues found in the project, such as:
    - Methods without docstrings
    - Files/classes without docstrings
    - Methods with 'pass' instead of implementation
    - Files exceeding line limit
    - NotImplemented in non-abstract methods

    Useful for code quality audits and technical debt tracking.

    Args:
        root_dir: Root directory of the project (must be analyzed first)
        issue_type: Filter by issue type. Valid types:
                   - "methods_without_docstrings"
                   - "files_without_docstrings"
                   - "classes_without_docstrings"
                   - "methods_with_pass"
                   - "files_too_large"
                   - "not_implemented_in_non_abstract"
                   If None, returns all issues grouped by type
        context: MCP context for logging
        timeout: Operation timeout in seconds (default: 60)

    Returns:
        If issue_type is specified: List of issue records
        If issue_type is None: Dictionary with issues grouped by type
        Each issue contains:
        - file_path: Path to file with issue
        - line: Line number (if applicable)
        - description: Human-readable issue description
        - metadata: Additional context (JSON string)

    Example:
        # Get all issues
        all_issues = await get_issues(root_dir="/path/to/project")

        # Get specific issue type
        missing_docs = await get_issues(
            root_dir="/path/to/project",
            issue_type="methods_without_docstrings"
        )
    """
    message = f"Retrieving issues from {root_dir}" + (
        f" (type: {issue_type})" if issue_type else ""
    )
    if context:
        await context.info(message)
    else:
        logger.info(message)

    api = CodeAnalysisAPI(root_dir)
    try:
        issues = await asyncio.wait_for(api.get_issues(issue_type), timeout=timeout)
        if isinstance(issues, dict):
            total = sum(len(v) if isinstance(v, list) else 1 for v in issues.values())
            result_message = f"Found {total} issues across {len(issues)} types"
        else:
            result_message = f"Found {len(issues)} issues"
        if context:
            await context.info(result_message)
        else:
            logger.info(result_message)
        return issues
    except asyncio.TimeoutError:
        error_msg = f"Get issues timeout after {timeout} seconds"
        if context:
            await context.error(error_msg)
        else:
            logger.error(error_msg)
        raise TimeoutError(error_msg)
    finally:
        api.close()


async def split_class(
    root_dir: str,
    file_path: str,
    config: Dict[str, Any],
    context: Context | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Split a large class into multiple smaller classes.

    This refactoring tool helps break down large classes that violate
    Single Responsibility Principle. It:
    - Moves specified methods and properties to new classes
    - Creates wrapper methods in original class for backward compatibility
    - Preserves docstrings and code formatting
    - Creates backup before modification

    Args:
        root_dir: Root directory of the project
        file_path: Path to Python file containing the class (relative or absolute)
        config: Split configuration dictionary with:
               - src_class: Name of class to split
               - dst_classes: Dictionary mapping new class names to:
                 - props: List of property names to move
                 - methods: List of method names to move
        context: MCP context for logging and progress
        timeout: Operation timeout in seconds (default: 300)

    Returns:
        Dictionary with:
        - success: Boolean indicating if operation succeeded
        - message: Human-readable result message
        - project_id: Project UUID

    Example:
        result = await split_class(
            root_dir="/path/to/project",
            file_path="models.py",
            config={
                "src_class": "UserManager",
                "dst_classes": {
                    "UserAuth": {
                        "props": ["token", "session"],
                        "methods": ["login", "logout", "validate"]
                    },
                    "UserStorage": {
                        "props": ["db_connection"],
                        "methods": ["save", "load", "delete"]
                    }
                }
            }
        )
    """
    if context:
        await context.info(f"Splitting class in {file_path}")
    else:
        logger.info(f"Splitting class in {file_path}")

    api = CodeAnalysisAPI(root_dir)
    try:
        result = await asyncio.wait_for(api.split_class(file_path, config), timeout=timeout)
        return result
    except asyncio.TimeoutError:
        error_msg = f"Split class timeout after {timeout} seconds"
        if context:
            await context.error(error_msg)
        else:
            logger.error(error_msg)
        raise TimeoutError(error_msg)
    finally:
        api.close()


async def extract_superclass(
    root_dir: str,
    file_path: str,
    config: Dict[str, Any],
    context: Context | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Extract common functionality into a base class.

    This refactoring tool identifies common methods and properties across
    multiple classes and extracts them into a base class. Helps reduce
    code duplication and improve maintainability.

    Args:
        root_dir: Root directory of the project
        file_path: Path to Python file containing classes (relative or absolute)
        config: Extraction configuration dictionary with:
               - classes: List of class names to extract from
               - base_class: Name for the new base class
               - common_methods: List of method names to extract
               - common_props: List of property names to extract
        context: MCP context for logging and progress
        timeout: Operation timeout in seconds (default: 300)

    Returns:
        Dictionary with:
        - success: Boolean indicating if operation succeeded
        - message: Human-readable result message
        - project_id: Project UUID

    Example:
        result = await extract_superclass(
            root_dir="/path/to/project",
            file_path="handlers.py",
            config={
                "classes": ["HTTPHandler", "HTTPSHandler", "FTPHandler"],
                "base_class": "BaseHandler",
                "common_methods": ["connect", "disconnect", "send"],
                "common_props": ["timeout", "retries"]
            }
        )
    """
    if context:
        await context.info(f"Extracting superclass in {file_path}")
    else:
        logger.info(f"Extracting superclass in {file_path}")

    api = CodeAnalysisAPI(root_dir)
    try:
        result = await asyncio.wait_for(
            api.extract_superclass(file_path, config), timeout=timeout
        )
        return result
    except asyncio.TimeoutError:
        error_msg = f"Extract superclass timeout after {timeout} seconds"
        if context:
            await context.error(error_msg)
        else:
            logger.error(error_msg)
        raise TimeoutError(error_msg)
    finally:
        api.close()


async def merge_classes(
    root_dir: str,
    file_path: str,
    config: Dict[str, Any],
    context: Context | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Merge multiple classes into a single base class.

    This refactoring tool combines multiple related classes into one,
    useful when classes have become too fragmented or when consolidating
    similar functionality.

    Args:
        root_dir: Root directory of the project
        file_path: Path to Python file containing classes (relative or absolute)
        config: Merge configuration dictionary with:
               - classes: List of class names to merge
               - target_class: Name for the merged class
        context: MCP context for logging and progress
        timeout: Operation timeout in seconds (default: 300)

    Returns:
        Dictionary with:
        - success: Boolean indicating if operation succeeded
        - message: Human-readable result message
        - project_id: Project UUID

    Example:
        result = await merge_classes(
            root_dir="/path/to/project",
            file_path="utils.py",
            config={
                "classes": ["StringUtils", "NumberUtils", "DateUtils"],
                "target_class": "GeneralUtils"
            }
        )
    """
    if context:
        await context.info(f"Merging classes in {file_path}")
    else:
        logger.info(f"Merging classes in {file_path}")

    api = CodeAnalysisAPI(root_dir)
    try:
        result = await asyncio.wait_for(api.merge_classes(file_path, config), timeout=timeout)
        return result
    except asyncio.TimeoutError:
        error_msg = f"Merge classes timeout after {timeout} seconds"
        if context:
            await context.error(error_msg)
        else:
            logger.error(error_msg)
        raise TimeoutError(error_msg)
    finally:
        api.close()


async def add_project(
    config_path: str,
    name: str,
    path: str,
    project_id: Optional[str] = None,
    comment: Optional[str] = None,
    db_path: Optional[str] = None,
    context: Context | None = None,
    timeout: int = SHORT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Add a new project to server configuration and database.

    This tool registers a new project in the server configuration and
    creates an entry in the analysis database. Projects must be added
    before they can be analyzed.

    Args:
        config_path: Path to server configuration file (JSON)
        name: Human-readable project name (required, must be unique)
        path: Absolute path to project directory (required, must exist)
        project_id: Optional UUID4 identifier (auto-generated if not provided)
        comment: Optional comment/description for the project
        db_path: Optional path to database (uses config default if not provided)
        context: MCP context for logging
        timeout: Operation timeout in seconds (default: 60)

    Returns:
        Dictionary with:
        - success: Boolean indicating if operation succeeded
        - message: Human-readable result message
        - project_id: UUID of the created project
        - name: Project name
        - path: Project path

    Example:
        result = await add_project(
            config_path="/etc/code_analysis/server_config.json",
            name="MyProject",
            path="/home/user/projects/myproject",
            comment="Main application project"
        )
    """
    if context:
        await context.info(f"Adding project: {name} at {path}")
    else:
        logger.info(f"Adding project: {name} at {path}")

    cmd = ProjectCommand(Path(config_path), db_path=Path(db_path) if db_path else None)
    try:
        return await asyncio.wait_for(
            cmd.add_project(name, path, project_id, comment), timeout=timeout
        )
    except asyncio.TimeoutError:
        error_msg = f"Add project timeout after {timeout} seconds"
        if context:
            await context.error(error_msg)
        else:
            logger.error(error_msg)
        raise TimeoutError(error_msg)


async def remove_project(
    config_path: str,
    project_id: str,
    context: Context | None = None,
    timeout: int = SHORT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Remove a project from server configuration.

    This tool removes a project from the server configuration file.
    Note: This does not delete the project's analysis data from the database.

    Args:
        config_path: Path to server configuration file (JSON)
        project_id: UUID4 identifier of project to remove
        context: MCP context for logging
        timeout: Operation timeout in seconds (default: 60)

    Returns:
        Dictionary with:
        - success: Boolean indicating if operation succeeded
        - message: Human-readable result message
        - project_id: UUID of removed project

    Example:
        result = await remove_project(
            config_path="/etc/code_analysis/server_config.json",
            project_id="550e8400-e29b-41d4-a716-446655440000"
        )
    """
    if context:
        await context.info(f"Removing project: {project_id}")
    else:
        logger.info(f"Removing project: {project_id}")

    cmd = ProjectCommand(Path(config_path))
    try:
        return await asyncio.wait_for(cmd.remove_project(project_id), timeout=timeout)
    except asyncio.TimeoutError:
        error_msg = f"Remove project timeout after {timeout} seconds"
        if context:
            await context.error(error_msg)
        else:
            logger.error(error_msg)
        raise TimeoutError(error_msg)


async def update_project(
    config_path: str,
    project_id: str,
    name: Optional[str] = None,
    path: Optional[str] = None,
    comment: Optional[str] = None,
    db_path: Optional[str] = None,
    context: Context | None = None,
    timeout: int = SHORT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Update project data in configuration and database.

    This tool updates project information such as name or path. Useful when
    projects are moved or renamed.

    Args:
        config_path: Path to server configuration file (JSON)
        project_id: UUID4 identifier of project to update
        name: New name (optional, must be unique if provided)
        path: New absolute path (optional, must exist if provided)
        comment: New comment/description (optional)
        db_path: Optional path to database (uses config default if not provided)
        context: MCP context for logging
        timeout: Operation timeout in seconds (default: 60)

    Returns:
        Dictionary with:
        - success: Boolean indicating if operation succeeded
        - message: Human-readable result message
        - project_id: UUID of updated project

    Example:
        result = await update_project(
            config_path="/etc/code_analysis/server_config.json",
            project_id="550e8400-e29b-41d4-a716-446655440000",
            name="RenamedProject",
            path="/new/path/to/project"
        )
    """
    if context:
        await context.info(f"Updating project: {project_id}")
    else:
        logger.info(f"Updating project: {project_id}")

    cmd = ProjectCommand(Path(config_path), db_path=Path(db_path) if db_path else None)
    try:
        return await asyncio.wait_for(
            cmd.update_project(project_id, name, path, comment), timeout=timeout
        )
    except asyncio.TimeoutError:
        error_msg = f"Update project timeout after {timeout} seconds"
        if context:
            await context.error(error_msg)
        else:
            logger.error(error_msg)
        raise TimeoutError(error_msg)


async def update_ast(
    root_dir: str,
    file_path: str,
    force: bool = False,
    context: Context | None = None,
    timeout: int = SHORT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Update AST tree for a specific file.

    This tool updates the AST tree for a single file in the database.
    By default, it only updates if the file has been modified since the
    last AST was stored. Use force=True to always update.

    Args:
        root_dir: Root directory of the project
        file_path: Path to file (relative to project root or absolute)
        force: If True, update AST regardless of modification time (default: False)
        context: MCP context for logging
        timeout: Operation timeout in seconds (default: 60)

    Returns:
        Dictionary with:
        - success: Boolean indicating if operation succeeded
        - message: Human-readable result message
        - file_id: File ID in database
        - ast_id: AST tree ID
        - ast_hash: Hash of AST tree
        - skipped: True if update was skipped (file not outdated)

    Example:
        result = await update_ast(
            root_dir="/path/to/project",
            file_path="src/main.py",
            force=False  # Only update if file changed
        )
    """
    if context:
        await context.info(f"Updating AST for file: {file_path} in {root_dir}")
    else:
        logger.info(f"Updating AST for file: {file_path} in {root_dir}")

    api = CodeAnalysisAPI(root_dir)
    try:
        # Get project ID
        project_id = api.project_id

        # Create update command
        update_cmd = UpdateASTCommand(api.database, project_id, file_path, force=force)

        result = await asyncio.wait_for(update_cmd.execute(), timeout=timeout)

        if result.get("success"):
            if result.get("skipped"):
                message = f"AST for {file_path} is up to date, skipped"
            else:
                message = f"AST updated for {file_path}"
        else:
            message = f"Failed to update AST: {result.get('message', 'Unknown error')}"

        if context:
            await context.info(message)
        else:
            logger.info(message)

        return result
    except asyncio.TimeoutError:
        error_msg = f"Update AST timeout after {timeout} seconds"
        if context:
            await context.error(error_msg)
        else:
            logger.error(error_msg)
        raise TimeoutError(error_msg)
    finally:
        api.close()


async def get_ast(
    root_dir: str,
    file_path: str,
    include_json: bool = True,
    context: Context | None = None,
    timeout: int = SHORT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Retrieve AST tree for a file.

    This tool retrieves the stored AST tree for a specific file from the database.
    Returns AST metadata and optionally the full AST JSON structure.

    Args:
        root_dir: Root directory of the project
        file_path: Path to file (relative to project root or absolute)
        include_json: If True, include full AST JSON in response (default: True)
        context: MCP context for logging
        timeout: Operation timeout in seconds (default: 60)

    Returns:
        Dictionary with:
        - success: Boolean indicating if operation succeeded
        - message: Human-readable result message
        - file_id: File ID in database
        - file_path: Absolute file path
        - ast_id: AST tree ID
        - ast_hash: Hash of AST tree
        - file_last_modified_at: File modification timestamp
        - updated_at: AST update timestamp
        - ast_json: Full AST structure (if include_json=True)

    Example:
        result = await get_ast(
            root_dir="/path/to/project",
            file_path="src/main.py",
            include_json=True
        )
        ast_tree = result["ast_json"]
    """
    if context:
        await context.info(f"Retrieving AST for file: {file_path} in {root_dir}")
    else:
        logger.info(f"Retrieving AST for file: {file_path} in {root_dir}")

    api = CodeAnalysisAPI(root_dir)
    try:
        # Get project ID
        project_id = api.project_id

        # Create get AST command
        get_cmd = GetASTCommand(api.database, project_id, file_path, include_json=include_json)

        result = await asyncio.wait_for(get_cmd.execute(), timeout=timeout)

        if context:
            await context.info(result.get("message", "AST retrieved"))
        else:
            logger.info(result.get("message", "AST retrieved"))

        return result
    except asyncio.TimeoutError:
        error_msg = f"Get AST timeout after {timeout} seconds"
        if context:
            await context.error(error_msg)
        else:
            logger.error(error_msg)
        raise TimeoutError(error_msg)
    finally:
        api.close()


async def search_ast_nodes(
    root_dir: str,
    node_type: Optional[str] = None,
    file_path: Optional[str] = None,
    limit: int = 100,
    context: Context | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Search for specific node types in AST trees.

    This tool searches through AST trees to find nodes of a specific type
    (e.g., ClassDef, FunctionDef, Call). Can search in a single file or
    across all files in a project.

    Args:
        root_dir: Root directory of the project
        node_type: Type of AST node to search for (e.g., "ClassDef", "FunctionDef")
                   If None, returns all nodes
        file_path: Path to specific file (if None, searches all files)
        limit: Maximum number of results (default: 100)
        context: MCP context for logging
        timeout: Operation timeout in seconds (default: 300)

    Returns:
        Dictionary with:
        - success: Boolean indicating if operation succeeded
        - message: Human-readable result message
        - results: List of matching nodes with type, path, name, lineno, etc.
        - count: Total number of results found
        - node_type: Type of node searched for
        - limit: Maximum results limit

    Example:
        # Find all class definitions in a file
        result = await search_ast_nodes(
            root_dir="/path/to/project",
            node_type="ClassDef",
            file_path="src/models.py"
        )
        
        # Find all function calls across project
        result = await search_ast_nodes(
            root_dir="/path/to/project",
            node_type="Call"
        )
    """
    if context:
        await context.info(f"Searching AST nodes in {root_dir}")
    else:
        logger.info(f"Searching AST nodes in {root_dir}")

    api = CodeAnalysisAPI(root_dir)
    try:
        # Get project ID
        project_id = api.project_id

        # Create search command
        search_cmd = SearchASTNodesCommand(
            api.database, project_id, node_type, file_path, limit
        )

        result = await asyncio.wait_for(search_cmd.execute(), timeout=timeout)

        if context:
            await context.info(f"Found {result.get('count', 0)} nodes")
        else:
            logger.info(f"Found {result.get('count', 0)} nodes")

        return result
    except asyncio.TimeoutError:
        error_msg = f"Search AST nodes timeout after {timeout} seconds"
        if context:
            await context.error(error_msg)
        else:
            logger.error(error_msg)
        raise TimeoutError(error_msg)
    finally:
        api.close()


async def ast_statistics(
    root_dir: str,
    file_path: Optional[str] = None,
    context: Context | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Get statistics about AST trees.

    This tool calculates statistics about AST trees, including node counts,
    tree depth, and node type distribution. Can analyze a single file or
    entire project.

    Args:
        root_dir: Root directory of the project
        file_path: Path to specific file (if None, returns project-wide stats)
        context: MCP context for logging
        timeout: Operation timeout in seconds (default: 300)

    Returns:
        Dictionary with:
        - success: Boolean indicating if operation succeeded
        - message: Human-readable result message
        - statistics: Dictionary with:
            - total_nodes: Total number of AST nodes
            - max_depth: Maximum tree depth
            - node_types: Dictionary mapping node types to counts
            - (for project-wide): total_files, files_with_ast, file_statistics

    Example:
        # Get statistics for a single file
        result = await ast_statistics(
            root_dir="/path/to/project",
            file_path="src/main.py"
        )
        print(f"Total nodes: {result['statistics']['total_nodes']}")
        
        # Get project-wide statistics
        result = await ast_statistics(
            root_dir="/path/to/project"
        )
        print(f"Files with AST: {result['statistics']['files_with_ast']}")
    """
    if context:
        await context.info(f"Calculating AST statistics for {root_dir}")
    else:
        logger.info(f"Calculating AST statistics for {root_dir}")

    api = CodeAnalysisAPI(root_dir)
    try:
        # Get project ID
        project_id = api.project_id

        # Create statistics command
        stats_cmd = ASTStatisticsCommand(api.database, project_id, file_path)

        result = await asyncio.wait_for(stats_cmd.execute(), timeout=timeout)

        if context:
            await context.info(result.get("message", "Statistics calculated"))
        else:
            logger.info(result.get("message", "Statistics calculated"))

        return result
    except asyncio.TimeoutError:
        error_msg = f"AST statistics timeout after {timeout} seconds"
        if context:
            await context.error(error_msg)
        else:
            logger.error(error_msg)
        raise TimeoutError(error_msg)
    finally:
        api.close()


async def help(
    command: Optional[str] = None,
    context: Context | None = None,
) -> str:
    """
    Get help information about the code analysis server and its commands.

    This tool provides comprehensive documentation about:
    - Server overview and capabilities
    - Available commands and their usage
    - Examples for each command

    Args:
        command: Optional command name to get detailed help for.
                If None, returns general server information.
                Valid commands:
                - analyze_project
                - find_usages
                - full_text_search
                - search_classes
                - search_methods
                - get_issues
                - split_class
                - extract_superclass
                - merge_classes
                - add_project
                - remove_project
                - update_project
                - update_ast
                - get_ast
                - search_ast_nodes
                - ast_statistics
        context: MCP context for logging

    Returns:
        Multi-line string with help information

    Example:
        # Get general help
        help_text = await help()

        # Get help for specific command
        analyze_help = await help(command="analyze_project")
    """
    if command:
        # Detailed help for specific command
        help_texts = {
            "analyze_project": """
ANALYZE_PROJECT - Analyze Python project and generate code map

DESCRIPTION:
    Scans a Python project directory, extracts code structure, and stores it
    in a database for further analysis. Identifies files, classes, methods,
    functions, imports, and code quality issues.

USAGE:
    await analyze_project(
        root_dir="/path/to/project",
        max_lines=400,
        comment="Project description"
    )

PARAMETERS:
    root_dir (required): Absolute path to project root directory
    max_lines (optional): Maximum lines per file threshold (default: 400)
    comment (optional): Human-readable project identifier
    force (optional): If True, process all files regardless of modification time.
                     By default, files are only processed if they are newer than
                     stored AST trees. This enables incremental analysis where
                     only changed files are re-analyzed (default: False)

RETURNS:
    Dictionary with:
    - files_analyzed: Number of Python files processed
    - classes: Total classes found
    - functions: Total functions found
    - issues: Total code quality issues
    - project_id: Project UUID

EXAMPLE:
    result = await analyze_project(
        root_dir="/home/user/myproject",
        max_lines=500
    )
    print(f"Analyzed {result['files_analyzed']} files")
""",
            "find_usages": """
FIND_USAGES - Find all usages of a method, property, or function

DESCRIPTION:
    Searches the codebase to find everywhere a specific method, property,
    or function is called or referenced. Useful for dependency analysis
    and refactoring safety checks.

USAGE:
    await find_usages(
        root_dir="/path/to/project",
        name="method_name",
        target_type="method",
        target_class="ClassName"
    )

PARAMETERS:
    root_dir (required): Project root directory
    name (required): Name of method/property/function to find
    target_type (optional): Filter by "method", "property", or "function"
    target_class (optional): Filter by class name

RETURNS:
    List of usage records with file_path, line, usage_type, context

EXAMPLE:
    usages = await find_usages(
        root_dir="/home/user/myproject",
        name="process_data",
        target_type="method"
    )
    for usage in usages:
        print(f"Found at {usage['file_path']}:{usage['line']}")
""",
            "full_text_search": """
FULL_TEXT_SEARCH - Search code content and docstrings

DESCRIPTION:
    Performs full-text search through actual code content and documentation
    using SQLite FTS5. Finds code by functionality rather than exact names.

USAGE:
    await full_text_search(
        root_dir="/path/to/project",
        query="search text",
        entity_type="class",
        limit=20
    )

PARAMETERS:
    root_dir (required): Project root directory
    query (required): Search query (supports SQLite FTS5 syntax)
    entity_type (optional): Filter by "class", "method", or "function"
    limit (optional): Maximum results (default: 20)

RETURNS:
    List of matching records with relevance scores

EXAMPLE:
    results = await full_text_search(
        root_dir="/home/user/myproject",
        query="database connection",
        limit=10
    )
""",
            "search_classes": """
SEARCH_CLASSES - Search classes by name pattern

DESCRIPTION:
    Finds classes in the codebase by name pattern. Supports SQL LIKE patterns
    for flexible searching.

USAGE:
    await search_classes(
        root_dir="/path/to/project",
        pattern="%Manager%"
    )

PARAMETERS:
    root_dir (required): Project root directory
    pattern (optional): SQL LIKE pattern (e.g., "%Handler%")
                        If None, returns all classes

RETURNS:
    List of class records with name, file_path, line, bases, docstring

EXAMPLE:
    classes = await search_classes(
        root_dir="/home/user/myproject",
        pattern="%Service%"
    )
""",
            "search_methods": """
SEARCH_METHODS - Search methods by name pattern

DESCRIPTION:
    Finds methods across all classes by name pattern. Useful for discovering
    method naming patterns and locating implementations.

USAGE:
    await search_methods(
        root_dir="/path/to/project",
        pattern="%get_%"
    )

PARAMETERS:
    root_dir (required): Project root directory
    pattern (optional): SQL LIKE pattern (e.g., "%validate%")
                        If None, returns all methods

RETURNS:
    List of method records with name, class_name, file_path, line, args

EXAMPLE:
    methods = await search_methods(
        root_dir="/home/user/myproject",
        pattern="%validate%"
    )
""",
            "get_issues": """
GET_ISSUES - Get code quality issues

DESCRIPTION:
    Retrieves code quality issues detected during analysis, such as missing
    docstrings, large files, or methods with 'pass'.

USAGE:
    await get_issues(
        root_dir="/path/to/project",
        issue_type="methods_without_docstrings"
    )

PARAMETERS:
    root_dir (required): Project root directory
    issue_type (optional): Filter by issue type:
        - "methods_without_docstrings"
        - "files_without_docstrings"
        - "classes_without_docstrings"
        - "methods_with_pass"
        - "files_too_large"
        - "not_implemented_in_non_abstract"
        If None, returns all issues grouped by type

RETURNS:
    Dictionary (if no type) or List (if type specified) of issue records

EXAMPLE:
    issues = await get_issues(
        root_dir="/home/user/myproject",
        issue_type="methods_without_docstrings"
    )
""",
            "split_class": """
SPLIT_CLASS - Split large class into smaller classes

DESCRIPTION:
    Refactoring tool that breaks down large classes by moving specified
    methods and properties to new classes while maintaining backward
    compatibility with wrapper methods.

USAGE:
    await split_class(
        root_dir="/path/to/project",
        file_path="models.py",
        config={
            "src_class": "UserManager",
            "dst_classes": {
                "UserAuth": {
                    "props": ["token"],
                    "methods": ["login", "logout"]
                }
            }
        }
    )

PARAMETERS:
    root_dir (required): Project root directory
    file_path (required): Path to file containing class
    config (required): Split configuration dictionary

RETURNS:
    Dictionary with success status and message

EXAMPLE:
    result = await split_class(
        root_dir="/home/user/myproject",
        file_path="handlers.py",
        config={
            "src_class": "RequestHandler",
            "dst_classes": {
                "AuthHandler": {"methods": ["authenticate"]},
                "DataHandler": {"methods": ["process"]}
            }
        }
    )
""",
            "extract_superclass": """
EXTRACT_SUPERCLASS - Extract common functionality into base class

DESCRIPTION:
    Refactoring tool that identifies common methods and properties across
    multiple classes and extracts them into a base class to reduce
    code duplication.

USAGE:
    await extract_superclass(
        root_dir="/path/to/project",
        file_path="handlers.py",
        config={
            "classes": ["HTTPHandler", "HTTPSHandler"],
            "base_class": "BaseHandler",
            "common_methods": ["connect", "disconnect"]
        }
    )

PARAMETERS:
    root_dir (required): Project root directory
    file_path (required): Path to file containing classes
    config (required): Extraction configuration dictionary

RETURNS:
    Dictionary with success status and message

EXAMPLE:
    result = await extract_superclass(
        root_dir="/home/user/myproject",
        file_path="handlers.py",
        config={
            "classes": ["HandlerA", "HandlerB"],
            "base_class": "BaseHandler",
            "common_methods": ["process"]
        }
    )
""",
            "merge_classes": """
MERGE_CLASSES - Merge multiple classes into one

DESCRIPTION:
    Refactoring tool that combines multiple related classes into a single
    class, useful when classes have become too fragmented.

USAGE:
    await merge_classes(
        root_dir="/path/to/project",
        file_path="utils.py",
        config={
            "classes": ["StringUtils", "NumberUtils"],
            "target_class": "GeneralUtils"
        }
    )

PARAMETERS:
    root_dir (required): Project root directory
    file_path (required): Path to file containing classes
    config (required): Merge configuration dictionary

RETURNS:
    Dictionary with success status and message

EXAMPLE:
    result = await merge_classes(
        root_dir="/home/user/myproject",
        file_path="utils.py",
        config={
            "classes": ["UtilsA", "UtilsB"],
            "target_class": "MergedUtils"
        }
    )
""",
            "add_project": """
ADD_PROJECT - Add new project to server configuration

DESCRIPTION:
    Registers a new project in the server configuration and creates an entry
    in the analysis database. Projects must be added before they can be analyzed.

USAGE:
    await add_project(
        config_path="/path/to/config.json",
        name="MyProject",
        path="/path/to/project",
        project_id="optional-uuid",
        comment="Project description"
    )

PARAMETERS:
    config_path (required): Path to server configuration file
    name (required): Human-readable project name (must be unique)
    path (required): Absolute path to project directory (must exist)
    project_id (optional): UUID4 identifier (auto-generated if not provided)
    comment (optional): Project description
    db_path (optional): Path to database

RETURNS:
    Dictionary with success status, project_id, name, path

EXAMPLE:
    result = await add_project(
        config_path="/etc/code_analysis/config.json",
        name="MyApp",
        path="/home/user/myapp"
    )
""",
            "remove_project": """
REMOVE_PROJECT - Remove project from server configuration

DESCRIPTION:
    Removes a project from the server configuration file. Note: This does not
    delete the project's analysis data from the database.

USAGE:
    await remove_project(
        config_path="/path/to/config.json",
        project_id="uuid-of-project"
    )

PARAMETERS:
    config_path (required): Path to server configuration file
    project_id (required): UUID4 identifier of project to remove

RETURNS:
    Dictionary with success status and message

EXAMPLE:
    result = await remove_project(
        config_path="/etc/code_analysis/config.json",
        project_id="550e8400-e29b-41d4-a716-446655440000"
    )
""",
            "update_project": """
UPDATE_PROJECT - Update project data in configuration

DESCRIPTION:
    Updates project information such as name or path. Useful when projects
    are moved or renamed.

USAGE:
    await update_project(
        config_path="/path/to/config.json",
        project_id="uuid-of-project",
        name="NewName",
        path="/new/path"
    )

PARAMETERS:
    config_path (required): Path to server configuration file
    project_id (required): UUID4 identifier of project to update
    name (optional): New name (must be unique if provided)
    path (optional): New absolute path (must exist if provided)
    comment (optional): New comment/description
    db_path (optional): Path to database

RETURNS:
    Dictionary with success status and message

EXAMPLE:
    result = await update_project(
        config_path="/etc/code_analysis/config.json",
        project_id="550e8400-e29b-41d4-a716-446655440000",
        name="RenamedProject"
    )
""",
            "update_ast": """
UPDATE_AST - Update AST tree for a specific file

DESCRIPTION:
    Updates the AST tree for a single file in the database. By default, only
    updates if the file has been modified since the last AST was stored.
    Use force=True to always update regardless of modification time.

USAGE:
    await update_ast(
        root_dir="/path/to/project",
        file_path="src/main.py",
        force=False
    )

PARAMETERS:
    root_dir (required): Root directory of the project
    file_path (required): Path to file (relative to project root or absolute)
    force (optional): If True, update AST regardless of modification time.
                     By default, only updates if file is newer than stored AST
                     (default: False)

RETURNS:
    Dictionary with:
    - success: Boolean indicating if operation succeeded
    - message: Human-readable result message
    - file_id: File ID in database
    - ast_id: AST tree ID (if updated)
    - ast_hash: Hash of AST tree (if updated)
    - skipped: True if update was skipped (file not outdated)

EXAMPLE:
    # Update only if file changed
    result = await update_ast(
        root_dir="/home/user/myproject",
        file_path="src/main.py",
        force=False
    )
    
    # Force update regardless of modification time
    result = await update_ast(
        root_dir="/home/user/myproject",
        file_path="src/main.py",
        force=True
    )
""",
            "get_ast": """
GET_AST - Retrieve AST tree for a file

DESCRIPTION:
    Retrieves the stored AST tree for a specific file from the database.
    Returns AST metadata and optionally the full AST JSON structure.

USAGE:
    await get_ast(
        root_dir="/path/to/project",
        file_path="src/main.py",
        include_json=True
    )

PARAMETERS:
    root_dir (required): Root directory of the project
    file_path (required): Path to file (relative to project root or absolute)
    include_json (optional): If True, include full AST JSON in response
                            (default: True)

RETURNS:
    Dictionary with:
    - success: Boolean indicating if operation succeeded
    - message: Human-readable result message
    - file_id: File ID in database
    - file_path: Absolute file path
    - ast_id: AST tree ID
    - ast_hash: Hash of AST tree
    - file_last_modified_at: File modification timestamp
    - updated_at: AST update timestamp
    - ast_json: Full AST structure (if include_json=True)

EXAMPLE:
    result = await get_ast(
        root_dir="/home/user/myproject",
        file_path="src/main.py",
        include_json=True
    )
    ast_tree = result["ast_json"]
""",
            "search_ast_nodes": """
SEARCH_AST_NODES - Search for specific node types in AST trees

DESCRIPTION:
    Searches through AST trees to find nodes of a specific type (e.g., ClassDef,
    FunctionDef, Call). Can search in a single file or across all files in a project.

USAGE:
    await search_ast_nodes(
        root_dir="/path/to/project",
        node_type="ClassDef",
        file_path="src/main.py",
        limit=100
    )

PARAMETERS:
    root_dir (required): Root directory of the project
    node_type (optional): Type of AST node to search for (e.g., "ClassDef", "FunctionDef")
                          If None, returns all nodes
    file_path (optional): Path to specific file (if None, searches all files)
    limit (optional): Maximum number of results (default: 100)

RETURNS:
    Dictionary with:
    - success: Boolean indicating if operation succeeded
    - message: Human-readable result message
    - results: List of matching nodes with type, path, name, lineno, etc.
    - count: Total number of results found
    - node_type: Type of node searched for
    - limit: Maximum results limit

EXAMPLE:
    # Find all class definitions in a file
    result = await search_ast_nodes(
        root_dir="/home/user/myproject",
        node_type="ClassDef",
        file_path="src/models.py"
    )
    
    # Find all function calls across project
    result = await search_ast_nodes(
        root_dir="/home/user/myproject",
        node_type="Call"
    )
""",
            "ast_statistics": """
AST_STATISTICS - Get statistics about AST trees

DESCRIPTION:
    Calculates statistics about AST trees, including node counts, tree depth,
    and node type distribution. Can analyze a single file or entire project.

USAGE:
    await ast_statistics(
        root_dir="/path/to/project",
        file_path="src/main.py"
    )

PARAMETERS:
    root_dir (required): Root directory of the project
    file_path (optional): Path to specific file (if None, returns project-wide stats)

RETURNS:
    Dictionary with:
    - success: Boolean indicating if operation succeeded
    - message: Human-readable result message
    - statistics: Dictionary with:
        - total_nodes: Total number of AST nodes
        - max_depth: Maximum tree depth
        - node_types: Dictionary mapping node types to counts
        - (for project-wide): total_files, files_with_ast, file_statistics

EXAMPLE:
    # Get statistics for a single file
    result = await ast_statistics(
        root_dir="/home/user/myproject",
        file_path="src/main.py"
    )
    print(f"Total nodes: {result['statistics']['total_nodes']}")
    
    # Get project-wide statistics
    result = await ast_statistics(
        root_dir="/home/user/myproject"
    )
    print(f"Files with AST: {result['statistics']['files_with_ast']}")
""",
        }

        help_text = help_texts.get(command.lower())
        if help_text:
            return help_text.strip()
        else:
            available = ", ".join(help_texts.keys())
            return (
                f"Unknown command: {command}\n\n"
                f"Available commands: {available}"
            )

    # General server help
    return """
CODE ANALYSIS MCP SERVER

OVERVIEW:
    The Code Analysis MCP Server provides comprehensive code analysis capabilities
    for Python projects. It offers static code analysis, code search, usage tracking,
    issue detection, and automated refactoring tools.

CAPABILITIES:
    1. Project Analysis
       - Scan Python projects and extract code structure
       - Identify classes, methods, functions, and dependencies
       - Detect code quality issues

    2. Code Search
       - Search by class/method names with pattern matching
       - Full-text search in code content and docstrings
       - Find usages of specific methods/functions

    3. Code Quality
       - Detect missing docstrings
       - Identify large files
       - Find methods with incomplete implementations

    4. Refactoring
       - Split large classes into smaller ones
       - Extract common functionality into base classes
       - Merge related classes

    5. Project Management
       - Add/remove/update projects in server configuration
       - Manage multiple projects with UUID identifiers

AVAILABLE COMMANDS:
    Analysis:
      - analyze_project: Analyze project and generate code map
      - update_ast: Update AST tree for a specific file
      - get_ast: Retrieve AST tree for a file
      - search_ast_nodes: Search for specific node types in AST trees
      - ast_statistics: Get statistics about AST trees

    Search:
      - find_usages: Find all usages of a method/property/function
      - full_text_search: Search code content and docstrings
      - search_classes: Search classes by name pattern
      - search_methods: Search methods by name pattern

    Quality:
      - get_issues: Get code quality issues

    Refactoring:
      - split_class: Split large class into smaller classes
      - extract_superclass: Extract common functionality into base class
      - merge_classes: Merge multiple classes into one

    Project Management:
      - add_project: Add new project to configuration
      - remove_project: Remove project from configuration
      - update_project: Update project data

USAGE:
    Use help(command="command_name") to get detailed help for a specific command.

    Example workflow:
    1. Add project: await add_project(config_path="...", name="...", path="...")
    2. Analyze: await analyze_project(root_dir="...")
    3. Search: await search_classes(root_dir="...", pattern="%Manager%")
    4. Check issues: await get_issues(root_dir="...")

REQUIREMENTS:
    - Projects must be added before analysis
    - Projects must be analyzed before search operations
    - All paths must be absolute
    - Project names must be unique

For detailed help on a specific command, use: help(command="command_name")
""".strip()


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
    server.add_tool(add_project)
    server.add_tool(remove_project)
    server.add_tool(update_project)
    server.add_tool(update_ast)
    server.add_tool(get_ast)
    server.add_tool(search_ast_nodes)
    server.add_tool(ast_statistics)
    server.add_tool(help)

    # Run server
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
