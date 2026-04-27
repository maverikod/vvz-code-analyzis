"""
Single-file analysis for update_indexes: AST/CST extraction and entity indexing.

File-level DB writes are routed through the shared sync_file_to_db_atomic pipeline
(see code_analysis.core.database.file_tree_sync). No duplicate full-file write path.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..core.constants import FILE_MODIFICATION_TOLERANCE
from ..core.database.file_tree_sync import sync_file_to_db_atomic
from ..core.database.files.helpers import _last_modified_to_unix
from .update_indexes_entities import _extract_docstring

logger = logging.getLogger(__name__)

# Short phase labels for progress heartbeat (bounded size)
PHASE_READ = "read"
PHASE_SKIPPED = "skipped"
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
        force: If True, force full re-analysis even when disk mtime matches ``files.last_modified``.

    Returns:
        Per-file result dictionary with status and extracted counts.
        Status ``skipped`` means disk mtime matches DB within :data:`FILE_MODIFICATION_TOLERANCE`
        and no work was done (no file read, no parse).
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

        abs_file_path = str(file_path.resolve())
        tol = FILE_MODIFICATION_TOLERANCE
        file_record = database.get_file_by_path(abs_file_path, project_id)
        if file_record and not force:
            db_lm = _last_modified_to_unix(file_record.get("last_modified"))
            if db_lm is not None and abs(db_lm - file_mtime) <= tol:
                _heartbeat(PHASE_SKIPPED)
                logger.debug(
                    "Skipping unchanged file %s (db_mtime=%s disk_mtime=%s)",
                    rel_path,
                    db_lm,
                    file_mtime,
                )
                return {
                    "file": rel_path,
                    "status": "skipped",
                    "reason": "mtime_unchanged",
                    "db_mtime": db_lm,
                    "disk_mtime": file_mtime,
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

        if file_record:
            file_id = file_record["id"]
            db_lm = _last_modified_to_unix(file_record.get("last_modified"))
            need_row_update = force or db_lm is None or abs(db_lm - file_mtime) > tol
            if need_row_update:
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

            parse_with_comments(file_content, filename=str(file_path))
        except SyntaxError as e:
            logger.warning("Syntax error in %s: %s", rel_path, e)
            return {"file": rel_path, "status": "syntax_error", "error": str(e)}

        _heartbeat(PHASE_AST)
        _heartbeat(PHASE_CST)
        _heartbeat(PHASE_ENTITIES)
        sync_result = sync_file_to_db_atomic(
            database,
            project_id,
            abs_file_path,
            file_content,
            file_mtime,
            file_id=file_id,
        )
        if not sync_result.get("success"):
            error_msg = sync_result.get("error", "File sync failed")
            logger.error("Sync failed for %s: %s", rel_path, error_msg)
            return {
                "file": rel_path,
                "status": "error",
                "error": error_msg,
                "error_type": "SyncError",
            }

        usages_added = 0
        _heartbeat(PHASE_USAGE)
        try:
            tree = ast.parse(file_content, filename=str(file_path))
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

        database.mark_file_needs_chunking(abs_file_path, project_id)

        entities_updated = sync_result.get("entities_updated", 0)
        return {
            "file": rel_path,
            "status": "success",
            "classes": 0,
            "functions": 0,
            "methods": 0,
            "imports": 0,
            "entities_updated": entities_updated,
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
