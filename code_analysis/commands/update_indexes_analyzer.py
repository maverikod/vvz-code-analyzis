"""
Single-file analysis for update_indexes: AST/CST extraction and entity indexing.

File-level DB writes are routed through the shared sync_file_to_db_atomic pipeline
(see code_analysis.core.database.file_tree_sync). No duplicate full-file write path.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import asyncio
import concurrent.futures
import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, Optional

from ..core.constants import FILE_MODIFICATION_TOLERANCE
from ..core.database.file_tree_sync import sync_file_to_db_atomic
from ..core.database.files.helpers import _last_modified_to_unix
from ..core.docs_indexing_defaults import DOCS_INDEX_FILE_SUFFIXES
from ..core.docs_indexing_eligibility import is_docs_markdown_eligible
from ..core.docstring_chunker_pkg.docstring_chunker import DocstringChunker
from ..core.vectorization_helper import get_svo_client_manager
from .update_indexes_entities import _extract_docstring

logger = logging.getLogger(__name__)


def _markdown_first_heading_docstring(body: str) -> Optional[str]:
    """First non-empty markdown heading (``#`` …) for FTS ``docstring`` column."""
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            inner = line.lstrip("#").strip()
            return inner or None
        break
    return None


def _relative_path_docs_suffix(rel_path: str) -> Optional[str]:
    """Return matched documentation suffix (lowercase, with dot) or None."""
    low = rel_path.lower()
    for suf in DOCS_INDEX_FILE_SUFFIXES:
        if low.endswith(suf):
            return suf
    return None


def _docs_file_first_summary_line(body: str) -> Optional[str]:
    """First non-empty line (trimmed), capped length, for JSON/YAML FTS summary column."""
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        return line[:500] if len(line) > 500 else line
    return None


def _docs_virtual_docstring_for_fts(relative_path: str, body: str) -> Optional[str]:
    """Synthetic ``docstring`` column for indexed docs (heading for .md, first line otherwise)."""
    suf = _relative_path_docs_suffix(relative_path) or ""
    if suf == ".md":
        return _markdown_first_heading_docstring(body)
    return _docs_file_first_summary_line(body)


def _mirror_markdown_into_code_content_fulltext(
    database: Any,
    file_id: Any,
    relative_path: str,
    file_body: str,
) -> None:
    """Mirror documentation file body into ``code_content`` / FTS (md/json/yaml)."""
    driver = getattr(database, "_driver_type", None)
    if driver != "postgres":
        try:
            database.execute(
                "DELETE FROM code_content_fts WHERE rowid IN ("
                "SELECT rowid FROM code_content WHERE file_id = ?)",
                (file_id,),
            )
        except Exception as exc:
            logger.debug(
                "Could not prune code_content_fts before markdown mirror file_id=%s: %s",
                file_id,
                exc,
            )
    database.execute("DELETE FROM code_content WHERE file_id = ?", (file_id,))
    heading = _docs_virtual_docstring_for_fts(relative_path, file_body)
    database.add_code_content(
        file_id,
        "file",
        relative_path,
        file_body,
        heading,
        entity_id=file_id,
    )


async def _persist_markdown_doc_chunks_async(
    *,
    database: Any,
    file_id: Any,
    project_id: str,
    abs_file_path: str,
    file_content: str,
    server_config_path: Optional[str],
) -> None:
    """SVO DocBlock chunking for full-file Markdown → ``code_chunks`` (no embeddings required)."""
    cfg: Optional[Dict[str, Any]] = None
    root_for_certs: Optional[Path] = None
    if server_config_path:
        try:
            cfg_path = Path(server_config_path).expanduser().resolve()
            root_for_certs = cfg_path.parent
            with cfg_path.open("r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as exc:
            logger.debug(
                "Markdown index: could not load server config %s: %s",
                server_config_path,
                exc,
            )

    mgr = get_svo_client_manager(cfg, root_for_certs)
    if mgr:
        await mgr.initialize()
    try:
        chunker = DocstringChunker(
            database=database,
            svo_client_manager=mgr,
            faiss_manager=None,
            min_chunk_length=30,
        )
        await chunker.process_markdown_document(
            file_id=str(file_id),
            project_id=project_id,
            file_path=abs_file_path,
            text=file_content,
        )
    finally:
        if mgr:
            await mgr.close()


def _run_coroutine_sync_for_worker(
    factory: Callable[[], Coroutine[Any, Any, None]],
) -> None:
    """Run *factory()* to completion from synchronous code.

    Uses :func:`asyncio.run` when this thread has no running event loop.

    When a loop is already running (e.g. ``index_file`` in-process RPC on the
    indexing worker's asyncio thread), :func:`asyncio.run` is illegal; run the
    coroutine in a single worker thread with its own fresh loop instead.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(factory())
        return

    def _thread_runner() -> None:
        asyncio.run(factory())

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_thread_runner).result()


def _persist_markdown_doc_chunks_sync(
    *,
    database: Any,
    file_id: Any,
    project_id: str,
    abs_file_path: str,
    file_content: str,
    server_config_path: Optional[str],
) -> None:
    _run_coroutine_sync_for_worker(
        lambda: _persist_markdown_doc_chunks_async(
            database=database,
            file_id=file_id,
            project_id=project_id,
            abs_file_path=abs_file_path,
            file_content=file_content,
            server_config_path=server_config_path,
        )
    )


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
    docs_indexing: Any = None,
    server_config_path: Optional[str] = None,
    *,
    skip_file_edit_lock: bool = False,
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
        docs_indexing: Snapshot of ``code_analysis.docs_indexing`` (indexing-worker RPC); docs files.
        server_config_path: Path to server ``config.json`` for optional SVO chunker (docs path).
        skip_file_edit_lock: If True, ``sync_file_to_db_atomic`` does not take ``files.editing_pid``.

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

        def _compute_has_docstring_python() -> bool:
            try:
                return bool(_extract_docstring(ast.parse(file_content)))
            except SyntaxError:
                return False

        docs_suffix = _relative_path_docs_suffix(rel_path)
        is_docs_index_file = docs_suffix is not None
        if is_docs_index_file:
            if docs_indexing is None:
                return {
                    "file": rel_path,
                    "status": "error",
                    "error": (
                        "Documentation indexing requires docs_indexing (pass from indexing worker RPC); "
                        "CLI callers must supply code_analysis.docs_indexing when enabled"
                    ),
                    "error_type": "ConfigurationError",
                }
            verdict = is_docs_markdown_eligible(
                docs_indexing=docs_indexing,
                relative_path=rel_path,
                file_exists=True,
                is_deleted=False,
            )
            if not verdict.eligible:
                return {
                    "file": rel_path,
                    "status": "error",
                    "error": (
                        "Documentation file not eligible for docs indexing "
                        f"({','.join(verdict.reasons) if verdict.reasons else 'no reason'})"
                    ),
                    "error_type": "DocsMarkdownNotEligible",
                }

        has_doc_flag = True if is_docs_index_file else _compute_has_docstring_python()

        if file_record:
            file_id = file_record["id"]
            db_lm = _last_modified_to_unix(file_record.get("last_modified"))
            need_row_update = force or db_lm is None or abs(db_lm - file_mtime) > tol
            if need_row_update:
                file_id = database.add_file(
                    abs_file_path,
                    lines,
                    file_mtime,
                    has_doc_flag,
                    project_id,
                )
        else:
            file_id = database.add_file(
                abs_file_path,
                lines,
                file_mtime,
                has_doc_flag,
                project_id,
            )
            if not file_id:
                return {
                    "file": rel_path,
                    "status": "error",
                    "error": "Failed to create file record",
                    "error_type": "DatabaseError",
                }

        if is_docs_index_file:
            _heartbeat(PHASE_PARSE)
            _heartbeat(PHASE_AST)
            _heartbeat(PHASE_CST)
            _heartbeat(PHASE_ENTITIES)
            try:
                database.execute(
                    "DELETE FROM code_chunks WHERE file_id = ?",
                    (file_id,),
                )
            except Exception as exc:
                logger.warning(
                    "Could not clear old code_chunks for documentation file_id=%s: %s",
                    file_id,
                    exc,
                )
            try:
                _persist_markdown_doc_chunks_sync(
                    database=database,
                    file_id=file_id,
                    project_id=project_id,
                    abs_file_path=abs_file_path,
                    file_content=file_content,
                    server_config_path=server_config_path,
                )
            except Exception as exc:
                logger.error(
                    "Documentation chunk persistence failed for %s: %s",
                    rel_path,
                    exc,
                    exc_info=True,
                )
                return {
                    "file": rel_path,
                    "status": "error",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }

            try:
                _mirror_markdown_into_code_content_fulltext(
                    database=database,
                    file_id=file_id,
                    relative_path=rel_path,
                    file_body=file_content,
                )
            except Exception as exc:
                logger.error(
                    "Documentation code_content FTS mirror failed for %s: %s",
                    rel_path,
                    exc,
                    exc_info=True,
                )
                return {
                    "file": rel_path,
                    "status": "error",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }

            return {
                "file": rel_path,
                "status": "success",
                "classes": 0,
                "functions": 0,
                "methods": 0,
                "imports": 0,
                "entities_updated": 0,
                "usages": 0,
                "markdown_indexed": True,
                "docs_indexed": True,
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
            skip_file_edit_lock=skip_file_edit_lock,
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
