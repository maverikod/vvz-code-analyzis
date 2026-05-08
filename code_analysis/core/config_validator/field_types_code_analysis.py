"""
Field type validation for code_analysis section (chunker, embedding, file_watcher, database).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, List

from .helpers import validate_field_type
from .result import ValidationResult


def validate_field_types_code_analysis_impl(
    config_data: Dict[str, Any], results: List[ValidationResult]
) -> None:
    """Validate types of code_analysis configuration fields."""
    code_analysis = config_data.get("code_analysis", {})
    if not code_analysis:
        return

    validate_field_type(
        results, "code_analysis", "host", code_analysis.get("host"), str
    )
    validate_field_type(
        results, "code_analysis", "port", code_analysis.get("port"), int
    )
    validate_field_type(results, "code_analysis", "log", code_analysis.get("log"), str)
    validate_field_type(
        results,
        "code_analysis",
        "db_path",
        code_analysis.get("db_path"),
        str,
    )
    validate_field_type(
        results,
        "code_analysis",
        "faiss_index_path",
        code_analysis.get("faiss_index_path"),
        str,
    )
    validate_field_type(
        results,
        "code_analysis",
        "vector_dim",
        code_analysis.get("vector_dim"),
        int,
    )
    validate_field_type(
        results,
        "code_analysis",
        "vector_search_backend",
        code_analysis.get("vector_search_backend"),
        str,
    )
    validate_field_type(
        results,
        "code_analysis",
        "min_chunk_length",
        code_analysis.get("min_chunk_length"),
        int,
    )
    validate_field_type(
        results,
        "code_analysis",
        "vectorization_retry_attempts",
        code_analysis.get("vectorization_retry_attempts"),
        int,
    )
    validate_field_type(
        results,
        "code_analysis",
        "vectorization_retry_delay",
        code_analysis.get("vectorization_retry_delay"),
        (int, float),
    )
    validate_field_type(
        results,
        "code_analysis",
        "log_vectorization_chunker_trace",
        code_analysis.get("log_vectorization_chunker_trace"),
        bool,
    )
    validate_field_type(
        results,
        "code_analysis",
        "allow_line_commands_on_healthy_files",
        code_analysis.get("allow_line_commands_on_healthy_files"),
        bool,
    )
    validate_field_type(
        results,
        "code_analysis",
        "read_project_text_json_structured_max_bytes",
        code_analysis.get("read_project_text_json_structured_max_bytes"),
        (int, type(None)),
    )
    venv_allow = code_analysis.get("venv_site_packages_index_allowlisted_distributions")
    if venv_allow is not None:
        validate_field_type(
            results,
            "code_analysis",
            "venv_site_packages_index_allowlisted_distributions",
            venv_allow,
            list,
        )
        if isinstance(venv_allow, list):
            for idx, item in enumerate(venv_allow):
                if not isinstance(item, str):
                    results.append(
                        ValidationResult(
                            level="error",
                            message=(
                                "code_analysis.venv_site_packages_index_allowlisted_distributions "
                                f"must be a list of strings (invalid item at index {idx})"
                            ),
                            section="code_analysis",
                            key="venv_site_packages_index_allowlisted_distributions",
                            suggestion='Use pip distribution names as strings, e.g. ["requests", "pydantic"]',
                        )
                    )

    ign_ex = code_analysis.get("ignore_exceptions")
    if ign_ex is not None:
        validate_field_type(
            results,
            "code_analysis",
            "ignore_exceptions",
            ign_ex,
            list,
        )
        if isinstance(ign_ex, list):
            for idx, item in enumerate(ign_ex):
                if not isinstance(item, str):
                    results.append(
                        ValidationResult(
                            level="error",
                            message=(
                                "code_analysis.ignore_exceptions must be a list of glob "
                                f"strings (invalid item at index {idx})"
                            ),
                            section="code_analysis",
                            key="ignore_exceptions",
                            suggestion='Use project-relative globs, e.g. [".venv/lib/**/site-packages/mypkg/**/*.py"]',
                        )
                    )

    chunker = code_analysis.get("chunker", {})
    if chunker and isinstance(chunker, dict):
        validate_field_type(
            results,
            "code_analysis",
            "chunker.enabled",
            chunker.get("enabled"),
            bool,
        )
        validate_field_type(
            results, "code_analysis", "chunker.url", chunker.get("url"), str
        )
        validate_field_type(
            results,
            "code_analysis",
            "chunker.port",
            chunker.get("port"),
            int,
        )
        validate_field_type(
            results,
            "code_analysis",
            "chunker.protocol",
            chunker.get("protocol"),
            str,
        )
        validate_field_type(
            results,
            "code_analysis",
            "chunker.cert_file",
            chunker.get("cert_file"),
            (str, type(None)),
        )
        validate_field_type(
            results,
            "code_analysis",
            "chunker.key_file",
            chunker.get("key_file"),
            (str, type(None)),
        )
        validate_field_type(
            results,
            "code_analysis",
            "chunker.ca_cert_file",
            chunker.get("ca_cert_file"),
            (str, type(None)),
        )
        validate_field_type(
            results,
            "code_analysis",
            "chunker.crl_file",
            chunker.get("crl_file"),
            (str, type(None)),
        )
        validate_field_type(
            results,
            "code_analysis",
            "chunker.retry_attempts",
            chunker.get("retry_attempts"),
            int,
        )
        validate_field_type(
            results,
            "code_analysis",
            "chunker.retry_delay",
            chunker.get("retry_delay"),
            (int, float),
        )
        validate_field_type(
            results,
            "code_analysis",
            "chunker.timeout",
            chunker.get("timeout"),
            (int, float, type(None)),
        )

    embedding = code_analysis.get("embedding", {})
    if embedding and isinstance(embedding, dict):
        validate_field_type(
            results,
            "code_analysis",
            "embedding.enabled",
            embedding.get("enabled"),
            bool,
        )
        validate_field_type(
            results,
            "code_analysis",
            "embedding.host",
            embedding.get("host"),
            str,
        )
        validate_field_type(
            results,
            "code_analysis",
            "embedding.port",
            embedding.get("port"),
            int,
        )
        validate_field_type(
            results,
            "code_analysis",
            "embedding.protocol",
            embedding.get("protocol"),
            str,
        )
        validate_field_type(
            results,
            "code_analysis",
            "embedding.cert_file",
            embedding.get("cert_file"),
            (str, type(None)),
        )
        validate_field_type(
            results,
            "code_analysis",
            "embedding.key_file",
            embedding.get("key_file"),
            (str, type(None)),
        )
        validate_field_type(
            results,
            "code_analysis",
            "embedding.ca_cert_file",
            embedding.get("ca_cert_file"),
            (str, type(None)),
        )
        validate_field_type(
            results,
            "code_analysis",
            "embedding.crl_file",
            embedding.get("crl_file"),
            (str, type(None)),
        )
        validate_field_type(
            results,
            "code_analysis",
            "embedding.retry_attempts",
            embedding.get("retry_attempts"),
            int,
        )
        validate_field_type(
            results,
            "code_analysis",
            "embedding.retry_delay",
            embedding.get("retry_delay"),
            (int, float),
        )
        validate_field_type(
            results,
            "code_analysis",
            "embedding.timeout",
            embedding.get("timeout"),
            (int, float, type(None)),
        )

    indexing_worker = code_analysis.get("indexing_worker", {})
    if indexing_worker and isinstance(indexing_worker, dict):
        validate_field_type(
            results,
            "code_analysis",
            "indexing_worker.enabled",
            indexing_worker.get("enabled"),
            (bool, type(None)),
        )
        validate_field_type(
            results,
            "code_analysis",
            "indexing_worker.poll_interval",
            indexing_worker.get("poll_interval"),
            (int, type(None)),
        )
        validate_field_type(
            results,
            "code_analysis",
            "indexing_worker.batch_size",
            indexing_worker.get("batch_size"),
            (int, type(None)),
        )
        validate_field_type(
            results,
            "code_analysis",
            "indexing_worker.log_path",
            indexing_worker.get("log_path"),
            (str, type(None)),
        )

    file_watcher = code_analysis.get("file_watcher", {})
    if file_watcher and isinstance(file_watcher, dict):
        validate_field_type(
            results,
            "code_analysis",
            "file_watcher.enabled",
            file_watcher.get("enabled"),
            (bool, type(None)),
        )
        validate_field_type(
            results,
            "code_analysis",
            "file_watcher.scan_interval",
            file_watcher.get("scan_interval"),
            (int, float, type(None)),
        )
        validate_field_type(
            results,
            "code_analysis",
            "file_watcher.log_path",
            file_watcher.get("log_path"),
            (str, type(None)),
        )
        validate_field_type(
            results,
            "code_analysis",
            "file_watcher.version_dir",
            file_watcher.get("version_dir"),
            (str, type(None)),
        )
        validate_field_type(
            results,
            "code_analysis",
            "file_watcher.max_scan_duration",
            file_watcher.get("max_scan_duration"),
            (int, float, type(None)),
        )
        validate_field_type(
            results,
            "code_analysis",
            "file_watcher.ignore_patterns",
            file_watcher.get("ignore_patterns"),
            (list, type(None)),
        )
        log_rotation = file_watcher.get("log_rotation", {})
        if log_rotation and isinstance(log_rotation, dict):
            validate_field_type(
                results,
                "code_analysis",
                "file_watcher.log_rotation.max_bytes",
                log_rotation.get("max_bytes"),
                (int, type(None)),
            )
            validate_field_type(
                results,
                "code_analysis",
                "file_watcher.log_rotation.backup_count",
                log_rotation.get("backup_count"),
                (int, type(None)),
            )

    docs_indexing = code_analysis.get("docs_indexing")
    if docs_indexing is not None and isinstance(docs_indexing, dict):
        validate_field_type(
            results,
            "code_analysis",
            "docs_indexing.enabled",
            docs_indexing.get("enabled"),
            (bool, type(None)),
        )
        validate_field_type(
            results,
            "code_analysis",
            "docs_indexing.vectorize",
            docs_indexing.get("vectorize"),
            (bool, type(None)),
        )
        roots_di = docs_indexing.get("roots")
        if roots_di is not None:
            validate_field_type(
                results,
                "code_analysis",
                "docs_indexing.roots",
                roots_di,
                list,
            )
        inc_di = docs_indexing.get("include")
        if inc_di is not None:
            validate_field_type(
                results,
                "code_analysis",
                "docs_indexing.include",
                inc_di,
                list,
            )
        exc_di = docs_indexing.get("exclude")
        if exc_di is not None:
            validate_field_type(
                results,
                "code_analysis",
                "docs_indexing.exclude",
                exc_di,
                list,
            )

    database = code_analysis.get("database", {})
    if database and isinstance(database, dict):
        driver = database.get("driver", {})
        if driver and isinstance(driver, dict):
            validate_field_type(
                results,
                "code_analysis",
                "database.driver.type",
                driver.get("type"),
                str,
            )
            validate_field_type(
                results,
                "code_analysis",
                "database.driver.config",
                driver.get("config"),
                dict,
            )

            driver_config = driver.get("config", {})
            if driver_config and isinstance(driver_config, dict):
                validate_field_type(
                    results,
                    "code_analysis",
                    "database.driver.config.path",
                    driver_config.get("path"),
                    (str, type(None)),
                )
                validate_field_type(
                    results,
                    "code_analysis",
                    "database.driver.config.host",
                    driver_config.get("host"),
                    (str, type(None)),
                )
                validate_field_type(
                    results,
                    "code_analysis",
                    "database.driver.config.dbname",
                    driver_config.get("dbname"),
                    (str, type(None)),
                )
                validate_field_type(
                    results,
                    "code_analysis",
                    "database.driver.config.user",
                    driver_config.get("user"),
                    (str, type(None)),
                )
                validate_field_type(
                    results,
                    "code_analysis",
                    "database.driver.config.password_env",
                    driver_config.get("password_env"),
                    (str, type(None)),
                )
                validate_field_type(
                    results,
                    "code_analysis",
                    "database.driver.config.dsn",
                    driver_config.get("dsn"),
                    (str, type(None)),
                )
                validate_field_type(
                    results,
                    "code_analysis",
                    "database.driver.config.port",
                    driver_config.get("port"),
                    (int, type(None)),
                )
                validate_field_type(
                    results,
                    "code_analysis",
                    "database.driver.config.backup_dir",
                    driver_config.get("backup_dir"),
                    (str, type(None)),
                )
                validate_field_type(
                    results,
                    "code_analysis",
                    "database.driver.config.worker_config",
                    driver_config.get("worker_config"),
                    (dict, type(None)),
                )

                worker_config = driver_config.get("worker_config", {})
                if worker_config and isinstance(worker_config, dict):
                    validate_field_type(
                        results,
                        "code_analysis",
                        "database.driver.config.worker_config.command_timeout",
                        worker_config.get("command_timeout"),
                        (int, float, type(None)),
                    )
                    validate_field_type(
                        results,
                        "code_analysis",
                        "database.driver.config.worker_config.poll_interval",
                        worker_config.get("poll_interval"),
                        (int, float, type(None)),
                    )
