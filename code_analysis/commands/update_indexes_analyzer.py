"""
Single-file analysis for update_indexes: AST/CST extraction and entity indexing.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .update_indexes_entities import _extract_docstring, index_entities

logger = logging.getLogger(__name__)

# Short phase labels for progress heartbeat (bounded size)
PHASE_READ = "read"
PHASE_PARSE = "parse"
PHASE_AST = "AST"
PHASE_CST = "CST"
PHASE_ENTITIES = "entities"
PHASE_USAGE = "usage"


def analyze_file(
    database: Any,
    file_path: Path,
    project_id: str,
    root_path: Path,
    progress_callback: Optional[Callable[[str], None]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Analyze a single Python file and add/update entries in the database.

    Uses O(n) classification for functions vs methods (precomputed set of
    method node ids from class bodies). Emits progress_callback(phase) for
    heartbeat during long per-file phases.

    Args:
        database: DatabaseClient instance.
        file_path: File to analyze.
        project_id: Project identifier.
        root_path: Root path to compute relative file paths.
        progress_callback: Optional callback(phase) for progress heartbeat.
        force: If True, force file record update even when mtime matches.

    Returns:
        Per-file result dictionary with status and extracted counts.
    """

    def _heartbeat(phase: str) -> None:
        if progress_callback:
            progress_callback(phase)

    try:
        file_path = file_path.resolve()
        root_path = root_path.resolve()

        try:
            rel_path = str(file_path.relative_to(root_path))
        except ValueError:
            logger.warning(
                "File %s is outside root %s, using absolute path",
                file_path,
                root_path,
            )
            rel_path = str(file_path)

        if not file_path.exists():
            return {
                "file": rel_path,
                "status": "error",
                "error": "File does not exist",
                "error_type": "FileNotFoundError",
            }

        try:
            file_stat = file_path.stat()
            file_mtime = file_stat.st_mtime
        except OSError as e:
            return {
                "file": rel_path,
                "status": "error",
                "error": f"Cannot stat file: {e}",
                "error_type": type(e).__name__,
            }

        _heartbeat(PHASE_READ)
        try:
            file_content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            return {
                "file": rel_path,
                "status": "error",
                "error": f"Unicode decode error: {e}",
                "error_type": "UnicodeDecodeError",
            }
        except Exception as e:
            return {
                "file": rel_path,
                "status": "error",
                "error": f"Cannot read file: {e}",
                "error_type": type(e).__name__,
            }

        lines = len(file_content.splitlines())
        abs_file_path = str(file_path.resolve())

        file_record = database.get_file_by_path(abs_file_path, project_id)
        if file_record:
            file_id = file_record["id"]
            last_modified = file_record.get("last_modified", 0)
            epsilon = 0.01
            if force or abs(last_modified - file_mtime) > epsilon:
                try:
                    has_docstring = bool(_extract_docstring(ast.parse(file_content)))
                except SyntaxError:
                    has_docstring = False
                file_id = database.add_file(
                    abs_file_path,
                    lines,
                    file_mtime,
                    has_docstring,
                    project_id,
                )
        else:
            try:
                has_docstring = bool(_extract_docstring(ast.parse(file_content)))
            except SyntaxError:
                has_docstring = False
            file_id = database.add_file(
                abs_file_path,
                lines,
                file_mtime,
                has_docstring,
                project_id,
            )
            if not file_id:
                return {
                    "file": rel_path,
                    "status": "error",
                    "error": "Failed to create file record",
                    "error_type": "DatabaseError",
                }

        _heartbeat(PHASE_PARSE)
        try:
            from ..core.ast_utils import parse_with_comments

            tree = parse_with_comments(file_content, filename=str(file_path))
        except SyntaxError as e:
            logger.warning("Syntax error in %s: %s", rel_path, e)
            return {"file": rel_path, "status": "syntax_error", "error": str(e)}

        ast_json = json.dumps(ast.dump(tree))
        ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()

        _heartbeat(PHASE_AST)
        try:
            logger.debug(
                "Saving AST for %s, file_id=%s, project_id=%s",
                rel_path,
                file_id,
                project_id,
            )
            database.save_ast_tree(
                file_id,
                project_id,
                ast_json,
                ast_hash,
                file_mtime,
                overwrite=True,
            )
        except Exception as e:
            logger.error("Error saving AST for %s: %s", rel_path, e, exc_info=True)
            return {
                "file": rel_path,
                "status": "error",
                "error": f"Failed to save AST: {e}",
                "error_type": type(e).__name__,
            }

        cst_hash = hashlib.sha256(file_content.encode()).hexdigest()
        _heartbeat(PHASE_CST)
        try:
            logger.debug(
                "Saving CST for %s, file_id=%s, project_id=%s",
                rel_path,
                file_id,
                project_id,
            )
            database.save_cst_tree(
                file_id,
                project_id,
                file_content,
                cst_hash,
                file_mtime,
                overwrite=True,
            )
        except Exception as e:
            logger.error("Error saving CST for %s: %s", rel_path, e, exc_info=True)
            return {
                "file": rel_path,
                "status": "error",
                "error": f"Failed to save CST: {e}",
                "error_type": type(e).__name__,
            }

        _heartbeat(PHASE_ENTITIES)
        classes_added, functions_added, methods_added, imports_added = index_entities(
            database, file_id, tree, file_content, rel_path
        )

        usages_added = 0
        _heartbeat(PHASE_USAGE)
        try:
            from ..core.usage_tracker import UsageTracker

            def add_usage_callback(usage_record: Dict[str, Any]) -> None:
                nonlocal usages_added
                try:
                    database.add_usage(
                        file_id=file_id,
                        line=usage_record["line"],
                        usage_type=usage_record["usage_type"],
                        target_type=usage_record["target_type"],
                        target_name=usage_record["target_name"],
                        target_class=usage_record.get("target_class"),
                        context=usage_record.get("context"),
                    )
                    usages_added += 1
                except Exception as e:
                    logger.debug(
                        "Failed to add usage for %s at line %s: %s",
                        usage_record.get("target_name"),
                        usage_record.get("line"),
                        e,
                        exc_info=True,
                    )

            usage_tracker = UsageTracker(add_usage_callback)
            usage_tracker.visit(tree)
            logger.debug("Tracked %s usages in %s", usages_added, rel_path)
        except Exception as e:
            logger.warning(
                "Failed to track usages for %s: %s",
                rel_path,
                e,
                exc_info=True,
            )

        database.mark_file_needs_chunking(rel_path, project_id)

        return {
            "file": rel_path,
            "status": "success",
            "classes": classes_added,
            "functions": functions_added,
            "methods": methods_added,
            "imports": imports_added,
            "usages": usages_added,
        }

    except Exception as e:
        error_msg = f"Error analyzing {file_path}: {e}"
        logger.error(error_msg, exc_info=True)
        print(f"ERROR: {error_msg}", file=sys.stderr, flush=True)
        print(f"ERROR_TYPE: {type(e).__name__}", file=sys.stderr, flush=True)
        import traceback

        traceback.print_exc(file=sys.stderr)
        return {
            "file": str(file_path),
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
        }
