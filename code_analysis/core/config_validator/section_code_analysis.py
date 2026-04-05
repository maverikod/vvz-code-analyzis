"""
Code analysis section validation (worker, circuit_breaker, watch_dirs, all_logs_rotation).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, List

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
