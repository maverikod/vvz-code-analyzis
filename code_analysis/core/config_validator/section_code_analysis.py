"""
Code analysis section validation (worker, circuit_breaker, watch_dirs, all_logs_rotation).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, List

from ..docs_indexing_defaults import (
    ALLOWED_DOCS_INDEXING_KEYS,
    docs_include_pattern_mentions_indexed_suffix,
)
from ..docs_indexing_eligibility import normalize_project_relative_posix
from .constants import ALLOWED_CODE_ANALYSIS_KEYS
from .result import ValidationResult


def validate_code_analysis_section_impl(
    config_data: Dict[str, Any], results: List[ValidationResult]
) -> None:
    """Validate code_analysis section."""
    code_analysis = config_data.get("code_analysis", {})
    if not code_analysis:
        return

    for key in code_analysis:
        if key not in ALLOWED_CODE_ANALYSIS_KEYS:
            results.append(
                ValidationResult(
                    level="error",
                    message=f"Unknown key 'code_analysis.{key}'; allowed keys: {', '.join(sorted(ALLOWED_CODE_ANALYSIS_KEYS))}",
                    section="code_analysis",
                    key=key,
                    suggestion=f"Remove '{key}' or use only allowed keys",
                )
            )

    rptj = code_analysis.get("read_project_text_json_structured_max_bytes")
    if rptj is not None and rptj < 1:
        results.append(
            ValidationResult(
                level="error",
                message="code_analysis.read_project_text_json_structured_max_bytes must be >= 1 when set",
                section="code_analysis",
                key="read_project_text_json_structured_max_bytes",
                suggestion="Set to a positive byte threshold or omit to use the default constant",
            )
        )

    _validate_docs_indexing(code_analysis, results)
    _validate_vector_search_backend_vs_driver(code_analysis, results)

    worker = code_analysis.get("worker")
    if worker and isinstance(worker, dict):
        poll_interval = worker.get("poll_interval")
        if poll_interval is not None and poll_interval < 1:
            results.append(
                ValidationResult(
                    level="error",
                    message="code_analysis.worker.poll_interval must be at least 1",
                    section="code_analysis",
                    key="worker.poll_interval",
                    suggestion="Set poll_interval to 1 or higher",
                )
            )

        batch_size = worker.get("batch_size")
        if batch_size is not None and batch_size < 1:
            results.append(
                ValidationResult(
                    level="error",
                    message="code_analysis.worker.batch_size must be at least 1",
                    section="code_analysis",
                    key="worker.batch_size",
                    suggestion="Set batch_size to 1 or higher",
                )
            )

        circuit_breaker = worker.get("circuit_breaker")
        if circuit_breaker and isinstance(circuit_breaker, dict):
            failure_threshold = circuit_breaker.get("failure_threshold")
            if failure_threshold is not None and failure_threshold < 1:
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.worker.circuit_breaker.failure_threshold must be at least 1",
                        section="code_analysis",
                        key="worker.circuit_breaker.failure_threshold",
                        suggestion="Set failure_threshold to 1 or higher",
                    )
                )

            recovery_timeout = circuit_breaker.get("recovery_timeout")
            if recovery_timeout is not None and recovery_timeout <= 0:
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.worker.circuit_breaker.recovery_timeout must be > 0",
                        section="code_analysis",
                        key="worker.circuit_breaker.recovery_timeout",
                        suggestion="Set recovery_timeout to a positive value",
                    )
                )

            success_threshold = circuit_breaker.get("success_threshold")
            if success_threshold is not None and success_threshold < 1:
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.worker.circuit_breaker.success_threshold must be at least 1",
                        section="code_analysis",
                        key="worker.circuit_breaker.success_threshold",
                        suggestion="Set success_threshold to 1 or higher",
                    )
                )

            initial_backoff = circuit_breaker.get("initial_backoff")
            if initial_backoff is not None and initial_backoff < 0:
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.worker.circuit_breaker.initial_backoff must be >= 0",
                        section="code_analysis",
                        key="worker.circuit_breaker.initial_backoff",
                        suggestion="Set initial_backoff to 0 or higher",
                    )
                )

            max_backoff = circuit_breaker.get("max_backoff")
            if max_backoff is not None and max_backoff < 0:
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.worker.circuit_breaker.max_backoff must be >= 0",
                        section="code_analysis",
                        key="worker.circuit_breaker.max_backoff",
                        suggestion="Set max_backoff to 0 or higher",
                    )
                )

            if (
                initial_backoff is not None
                and max_backoff is not None
                and max_backoff < initial_backoff
            ):
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.worker.circuit_breaker.max_backoff must be >= initial_backoff",
                        section="code_analysis",
                        key="worker.circuit_breaker.max_backoff",
                        suggestion="Set max_backoff to be at least equal to initial_backoff",
                    )
                )

            backoff_multiplier = circuit_breaker.get("backoff_multiplier")
            if backoff_multiplier is not None and backoff_multiplier < 1:
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.worker.circuit_breaker.backoff_multiplier must be >= 1",
                        section="code_analysis",
                        key="worker.circuit_breaker.backoff_multiplier",
                        suggestion="Set backoff_multiplier to 1 or higher",
                    )
                )
            if backoff_multiplier is not None and backoff_multiplier > 10:
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.worker.circuit_breaker.backoff_multiplier must be <= 10",
                        section="code_analysis",
                        key="worker.circuit_breaker.backoff_multiplier",
                        suggestion="Set backoff_multiplier to 10 or lower",
                    )
                )
            if max_backoff is not None and max_backoff > 3600:
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.worker.circuit_breaker.max_backoff must be <= 3600 (1 hour)",
                        section="code_analysis",
                        key="worker.circuit_breaker.max_backoff",
                        suggestion="Set max_backoff to 3600 or lower",
                    )
                )

        batch_processor = worker.get("batch_processor")
        if batch_processor and isinstance(batch_processor, dict):
            max_empty_iterations = batch_processor.get("max_empty_iterations")
            if max_empty_iterations is not None and max_empty_iterations < 1:
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.worker.batch_processor.max_empty_iterations must be at least 1",
                        section="code_analysis",
                        key="worker.batch_processor.max_empty_iterations",
                        suggestion="Set max_empty_iterations to 1 or higher",
                    )
                )

            empty_delay = batch_processor.get("empty_delay")
            if empty_delay is not None and empty_delay < 0:
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.worker.batch_processor.empty_delay must be >= 0",
                        section="code_analysis",
                        key="worker.batch_processor.empty_delay",
                        suggestion="Set empty_delay to 0 or higher",
                    )
                )

        watch_dirs = worker.get("watch_dirs") if worker else None
        if isinstance(watch_dirs, list):
            for i, wd in enumerate(watch_dirs):
                if not isinstance(wd, dict):
                    results.append(
                        ValidationResult(
                            level="error",
                            message=f"code_analysis.worker.watch_dirs[{i}] must be a dict with 'id' and 'path'",
                            section="code_analysis",
                            key=f"worker.watch_dirs[{i}]",
                            suggestion='Use format: {"id": "uuid4", "path": "/abs/path", "ignore_patterns": ["**/.venv/**"]}',
                        )
                    )
                else:
                    if "id" not in wd or "path" not in wd:
                        results.append(
                            ValidationResult(
                                level="error",
                                message=f"code_analysis.worker.watch_dirs[{i}] must have 'id' and 'path' keys",
                                section="code_analysis",
                                key=f"worker.watch_dirs[{i}]",
                                suggestion='Add "id" and "path" to the watch directory entry',
                            )
                        )
                    ign = wd.get("ignore_patterns")
                    if ign is not None and not isinstance(ign, list):
                        results.append(
                            ValidationResult(
                                level="error",
                                message=f"code_analysis.worker.watch_dirs[{i}].ignore_patterns must be a list of glob patterns",
                                section="code_analysis",
                                key=f"worker.watch_dirs[{i}].ignore_patterns",
                                suggestion='Use a list of strings, e.g. ["**/.venv/**", "**/venv/**"]',
                            )
                        )
                    if "id" in wd and "path" in wd:
                        from code_analysis.core.docker_watch_paths import (
                            validate_docker_watch_dir_entry,
                        )

                        path_err = validate_docker_watch_dir_entry(
                            str(wd["id"]), str(wd["path"])
                        )
                        if path_err:
                            results.append(
                                ValidationResult(
                                    level="error",
                                    message=(
                                        f"code_analysis.worker.watch_dirs[{i}]: {path_err}"
                                    ),
                                    section="code_analysis",
                                    key=f"worker.watch_dirs[{i}].path",
                                    suggestion=(
                                        "Set path to /watched/<same-uuid-as-id> and "
                                        "bind-mount host tree to that container path"
                                    ),
                                )
                            )

        indexing_worker = code_analysis.get("indexing_worker")
        if indexing_worker and isinstance(indexing_worker, dict):
            if (
                indexing_worker.get("poll_interval") is not None
                and indexing_worker.get("poll_interval", 0) < 1
            ):
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.indexing_worker.poll_interval must be at least 1",
                        section="code_analysis",
                        key="indexing_worker.poll_interval",
                        suggestion="Set poll_interval to 1 or higher",
                    )
                )
            if (
                indexing_worker.get("batch_size") is not None
                and indexing_worker.get("batch_size", 0) < 1
            ):
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.indexing_worker.batch_size must be at least 1",
                        section="code_analysis",
                        key="indexing_worker.batch_size",
                        suggestion="Set batch_size to 1 or higher",
                    )
                )

    all_logs = code_analysis.get("all_logs_rotation")
    if all_logs is not None and isinstance(all_logs, dict):
        interval = all_logs.get("interval_seconds")
        if interval is not None:
            if not isinstance(interval, (int, float)):
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.all_logs_rotation.interval_seconds must be a number",
                        section="code_analysis",
                        key="all_logs_rotation.interval_seconds",
                        suggestion="Set interval_seconds to a number (0 to disable periodic rotation)",
                    )
                )
            elif interval < 0:
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.all_logs_rotation.interval_seconds must be >= 0",
                        section="code_analysis",
                        key="all_logs_rotation.interval_seconds",
                        suggestion="Set interval_seconds to 0 or positive (e.g. 86400 for daily)",
                    )
                )
        backup = all_logs.get("backup_count")
        if backup is not None:
            if not isinstance(backup, int):
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.all_logs_rotation.backup_count must be an integer",
                        section="code_analysis",
                        key="all_logs_rotation.backup_count",
                        suggestion="Set backup_count to 1-99",
                    )
                )
            elif backup < 1 or backup > 99:
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.all_logs_rotation.backup_count must be between 1 and 99",
                        section="code_analysis",
                        key="all_logs_rotation.backup_count",
                        suggestion="Set backup_count to 1-99",
                    )
                )
        pack = all_logs.get("pack_rotated")
        if pack is not None and not isinstance(pack, bool):
            results.append(
                ValidationResult(
                    level="error",
                    message="code_analysis.all_logs_rotation.pack_rotated must be a boolean",
                    section="code_analysis",
                    key="all_logs_rotation.pack_rotated",
                    suggestion="Set pack_rotated to true or false",
                )
            )


def _infer_database_driver_type(code_analysis: Dict[str, Any]) -> str:
    """Infer driver type string from ``code_analysis`` (same idea as ``get_driver_config``).

    A legacy ``db_path``-only config (no explicit ``database.driver``) previously
    implied ``sqlite_proxy``; SQLite support was removed, so this is no longer
    inferred here — ``section_database_driver`` / ``config.get_driver_config``
    raise a fatal error for that shape at validation/runtime instead.
    """
    database = code_analysis.get("database")
    if isinstance(database, dict):
        driver = database.get("driver")
        if isinstance(driver, dict):
            t = driver.get("type")
            if t:
                return str(t).strip().lower()
    return ""


def _validate_vector_search_backend_vs_driver(
    code_analysis: Dict[str, Any], results: List[ValidationResult]
) -> None:
    """
    Enforce: pgvector is not a valid choice for SQLite-class drivers (FAISS only).

    SQLite driver types are already rejected as a fatal error in
    ``section_database_driver``; this check remains as defense in depth for the
    ``vector_search_backend`` key specifically.
    """
    raw = code_analysis.get("vector_search_backend")
    if raw is None:
        return
    cfg = str(raw).strip().lower()
    if cfg not in ("auto", "faiss", "pgvector"):
        return

    dt = _infer_database_driver_type(code_analysis)
    if not dt:
        return

    if cfg == "pgvector" and dt in ("sqlite", "sqlite_proxy"):
        results.append(
            ValidationResult(
                level="error",
                message=(
                    "code_analysis.vector_search_backend cannot be 'pgvector' when the "
                    "database driver is sqlite or sqlite_proxy: SQLite support was removed; "
                    "PostgreSQL is required."
                ),
                section="code_analysis",
                key="vector_search_backend",
                suggestion='Use "auto" or "faiss", or switch to the postgres driver for pgvector.',
            )
        )


def _validate_docs_indexing(
    code_analysis: Dict[str, Any], results: List[ValidationResult]
) -> None:
    """Validate ``code_analysis.docs_indexing`` shape and semantics."""
    di = code_analysis.get("docs_indexing")
    if di is None:
        return
    if not isinstance(di, dict):
        results.append(
            ValidationResult(
                level="error",
                message="code_analysis.docs_indexing must be an object",
                section="code_analysis",
                key="docs_indexing",
                suggestion=(
                    "Use a JSON object with keys: enabled, vectorize, roots, include, exclude"
                ),
            )
        )
        return

    for key in di:
        if key not in ALLOWED_DOCS_INDEXING_KEYS:
            results.append(
                ValidationResult(
                    level="error",
                    message=(
                        f"Unknown key 'code_analysis.docs_indexing.{key}'; "
                        f"allowed: {', '.join(sorted(ALLOWED_DOCS_INDEXING_KEYS))}"
                    ),
                    section="code_analysis",
                    key=f"docs_indexing.{key}",
                    suggestion="Remove the unknown key or fix the spelling",
                )
            )

    roots = di.get("roots")
    if roots is not None:
        if not isinstance(roots, list):
            results.append(
                ValidationResult(
                    level="error",
                    message="code_analysis.docs_indexing.roots must be a list of strings",
                    section="code_analysis",
                    key="docs_indexing.roots",
                    suggestion='Use project-relative paths, e.g. ["docs"]',
                )
            )
        elif len(roots) == 0:
            results.append(
                ValidationResult(
                    level="error",
                    message="code_analysis.docs_indexing.roots must not be empty when set",
                    section="code_analysis",
                    key="docs_indexing.roots",
                    suggestion='Add at least one root, e.g. ["docs"]',
                )
            )
        else:
            for i, r in enumerate(roots):
                if not isinstance(r, str) or not r.strip():
                    results.append(
                        ValidationResult(
                            level="error",
                            message=(
                                f"code_analysis.docs_indexing.roots[{i}] must be a non-empty string"
                            ),
                            section="code_analysis",
                            key=f"docs_indexing.roots[{i}]",
                            suggestion="Use a project-relative POSIX path (no absolute paths or ..)",
                        )
                    )
                    continue
                text = r.strip().replace("\\", "/")
                if text.startswith("/") or (
                    ":" in text and len(text) > 1 and text[1] == ":"
                ):
                    results.append(
                        ValidationResult(
                            level="error",
                            message=(
                                f"code_analysis.docs_indexing.roots[{i}] must be project-relative "
                                "(no absolute paths)"
                            ),
                            section="code_analysis",
                            key=f"docs_indexing.roots[{i}]",
                            suggestion="Use paths like docs or docs/guides (no leading slash)",
                        )
                    )
                    continue
                _, terr = normalize_project_relative_posix(text)
                if terr:
                    results.append(
                        ValidationResult(
                            level="error",
                            message=(
                                f"code_analysis.docs_indexing.roots[{i}] must not use path traversal "
                                "or empty segments"
                            ),
                            section="code_analysis",
                            key=f"docs_indexing.roots[{i}]",
                            suggestion="Remove ., .., and empty path components",
                        )
                    )

    inc = di.get("include")
    if inc is not None:
        if not isinstance(inc, list):
            results.append(
                ValidationResult(
                    level="error",
                    message="code_analysis.docs_indexing.include must be a list of strings",
                    section="code_analysis",
                    key="docs_indexing.include",
                    suggestion=(
                        "Use globs that mention .md / .json / .yaml / .yml, "
                        'e.g. ["docs/**/*.md", "docs/**/*.json", "README.md"]'
                    ),
                )
            )
        elif len(inc) == 0:
            results.append(
                ValidationResult(
                    level="error",
                    message="code_analysis.docs_indexing.include must not be empty when set",
                    section="code_analysis",
                    key="docs_indexing.include",
                    suggestion="Add at least one pattern that matches .md / .json / .yaml / .yml files",
                )
            )
        else:
            for i, p in enumerate(inc):
                if not isinstance(p, str) or not p.strip():
                    results.append(
                        ValidationResult(
                            level="error",
                            message=(
                                f"code_analysis.docs_indexing.include[{i}] must be a non-empty string"
                            ),
                            section="code_analysis",
                            key=f"docs_indexing.include[{i}]",
                            suggestion="Use a glob that includes a .md, .json, .yaml, or .yml suffix",
                        )
                    )
                    continue
                if not docs_include_pattern_mentions_indexed_suffix(p):
                    results.append(
                        ValidationResult(
                            level="error",
                            message=(
                                f"code_analysis.docs_indexing.include[{i}] must reference "
                                "an indexed documentation type (.md, .json, .yaml, or .yml)"
                            ),
                            section="code_analysis",
                            key=f"docs_indexing.include[{i}]",
                            suggestion=(
                                "Examples: docs/**/*.md, docs/**/*.json, README.md, **/*.yaml"
                            ),
                        )
                    )

    exc = di.get("exclude")
    if exc is not None:
        if not isinstance(exc, list):
            results.append(
                ValidationResult(
                    level="error",
                    message="code_analysis.docs_indexing.exclude must be a list of strings",
                    section="code_analysis",
                    key="docs_indexing.exclude",
                    suggestion='Use globs such as ["docs/plans/**", "docs/ai_reports/**"]',
                )
            )
        else:
            for i, p in enumerate(exc):
                if not isinstance(p, str) or not p.strip():
                    results.append(
                        ValidationResult(
                            level="error",
                            message=(
                                f"code_analysis.docs_indexing.exclude[{i}] must be a non-empty string"
                            ),
                            section="code_analysis",
                            key=f"docs_indexing.exclude[{i}]",
                            suggestion="Use a non-empty glob pattern",
                        )
                    )
