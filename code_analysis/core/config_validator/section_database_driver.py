"""
Database driver section validation (code_analysis.database.driver, rpc).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, List

from .result import ValidationResult

_WRITE_RETRY_CANONICAL = (
    "write_retry_attempts",
    "write_retry_delay_seconds",
    "write_retry_backoff_multiplier",
    "write_retry_jitter_seconds",
)
_TIMEOUT_CANONICAL = ("lock_timeout_seconds", "statement_timeout_seconds")


def _is_number_non_bool(value: Any) -> bool:
    """Return is number non bool."""
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float))


def _is_int_non_bool(value: Any) -> bool:
    """Return is int non bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_driver_retry_timeout_config(
    driver_config: Dict[str, Any], results: List[ValidationResult]
) -> None:
    """Validate retry and timeout keys under code_analysis.database.driver.config."""
    cfg_prefix = "code_analysis.database.driver.config"

    if "retry_attempts" in driver_config:
        results.append(
            ValidationResult(
                level="error",
                message=f"{cfg_prefix}.retry_attempts is not supported; use {cfg_prefix}.write_retry_attempts",
                section="code_analysis",
                key="database.driver.config.retry_attempts",
                suggestion="Rename retry_attempts to write_retry_attempts",
            )
        )
    if "retry_delay_seconds" in driver_config:
        results.append(
            ValidationResult(
                level="error",
                message=f"{cfg_prefix}.retry_delay_seconds is not supported; use {cfg_prefix}.write_retry_delay_seconds",
                section="code_analysis",
                key="database.driver.config.retry_delay_seconds",
                suggestion="Rename retry_delay_seconds to write_retry_delay_seconds",
            )
        )

    for key in list(driver_config.keys()):
        if key in ("retry_attempts", "retry_delay_seconds"):
            continue
        if key.startswith("write_retry_") and key not in _WRITE_RETRY_CANONICAL:
            results.append(
                ValidationResult(
                    level="error",
                    message=(
                        f"{cfg_prefix}.{key} is not a recognized setting; "
                        f"use canonical write_retry_* keys: "
                        f"{', '.join(_WRITE_RETRY_CANONICAL)}"
                    ),
                    section="code_analysis",
                    key=f"database.driver.config.{key}",
                    suggestion=(
                        "Use write_retry_attempts, write_retry_delay_seconds, "
                        "write_retry_backoff_multiplier, and write_retry_jitter_seconds only"
                    ),
                )
            )
        if key.endswith("_timeout_seconds") and key not in _TIMEOUT_CANONICAL:
            results.append(
                ValidationResult(
                    level="error",
                    message=(
                        f"{cfg_prefix}.{key} is not a recognized timeout setting; "
                        f"use {cfg_prefix}.lock_timeout_seconds or "
                        f"{cfg_prefix}.statement_timeout_seconds"
                    ),
                    section="code_analysis",
                    key=f"database.driver.config.{key}",
                    suggestion="Use lock_timeout_seconds or statement_timeout_seconds",
                )
            )
        if key.startswith("lock_timeout") and key != "lock_timeout_seconds":
            results.append(
                ValidationResult(
                    level="error",
                    message=(
                        f"{cfg_prefix}.{key} is not valid; "
                        f"use {cfg_prefix}.lock_timeout_seconds"
                    ),
                    section="code_analysis",
                    key=f"database.driver.config.{key}",
                    suggestion="Rename to lock_timeout_seconds",
                )
            )
        if key.startswith("statement_timeout") and key != "statement_timeout_seconds":
            results.append(
                ValidationResult(
                    level="error",
                    message=(
                        f"{cfg_prefix}.{key} is not valid; "
                        f"use {cfg_prefix}.statement_timeout_seconds"
                    ),
                    section="code_analysis",
                    key=f"database.driver.config.{key}",
                    suggestion="Rename to statement_timeout_seconds",
                )
            )

    if "write_retry_attempts" in driver_config:
        v = driver_config["write_retry_attempts"]
        if v is not None:
            key = "write_retry_attempts"
            if not _is_int_non_bool(v):
                results.append(
                    ValidationResult(
                        level="error",
                        message=(
                            f"{cfg_prefix}.{key} must be an integer (not bool, float, or string), "
                            f"in range 1..20"
                        ),
                        section="code_analysis",
                        key=f"database.driver.config.{key}",
                        suggestion="Set write_retry_attempts to an integer from 1 to 20",
                    )
                )
            elif v < 1 or v > 20:
                results.append(
                    ValidationResult(
                        level="error",
                        message=(
                            f"{cfg_prefix}.{key} must be between 1 and 20 inclusive, got {v!r}"
                        ),
                        section="code_analysis",
                        key=f"database.driver.config.{key}",
                        suggestion="Use an integer from 1 to 20",
                    )
                )

    for key, lo, hi in (
        ("write_retry_delay_seconds", 0.0, 60.0),
        ("write_retry_jitter_seconds", 0.0, 10.0),
    ):
        if key not in driver_config:
            continue
        v = driver_config[key]
        if v is None:
            continue
        if not _is_number_non_bool(v):
            results.append(
                ValidationResult(
                    level="error",
                    message=(
                        f"{cfg_prefix}.{key} must be a number (not bool, string, list, or dict), "
                        f"in range {lo}..{hi}"
                    ),
                    section="code_analysis",
                    key=f"database.driver.config.{key}",
                    suggestion=f"Set {key} to a number from {lo} to {hi}",
                )
            )
        elif float(v) < lo or float(v) > hi:
            results.append(
                ValidationResult(
                    level="error",
                    message=(
                        f"{cfg_prefix}.{key} must be between {lo} and {hi} inclusive, got {v!r}"
                    ),
                    section="code_analysis",
                    key=f"database.driver.config.{key}",
                    suggestion=f"Use a value from {lo} to {hi}",
                )
            )

    if "write_retry_backoff_multiplier" in driver_config:
        v = driver_config["write_retry_backoff_multiplier"]
        if v is not None:
            key = "write_retry_backoff_multiplier"
            if not _is_number_non_bool(v):
                results.append(
                    ValidationResult(
                        level="error",
                        message=(
                            f"{cfg_prefix}.{key} must be a number (not bool, string, list, or dict), "
                            f"in range 1.0..10.0"
                        ),
                        section="code_analysis",
                        key=f"database.driver.config.{key}",
                        suggestion="Set write_retry_backoff_multiplier to a number from 1.0 to 10.0",
                    )
                )
            else:
                fv = float(v)
                if fv < 1.0 or fv > 10.0:
                    results.append(
                        ValidationResult(
                            level="error",
                            message=(
                                f"{cfg_prefix}.{key} must be between 1.0 and 10.0 inclusive, "
                                f"got {v!r}"
                            ),
                            section="code_analysis",
                            key=f"database.driver.config.{key}",
                            suggestion="Use a value from 1.0 to 10.0",
                        )
                    )

    for key, lo, hi in (
        ("lock_timeout_seconds", 0.0, 300.0),
        ("statement_timeout_seconds", 0.0, 3600.0),
    ):
        if key not in driver_config:
            continue
        v = driver_config[key]
        if v is None:
            continue
        if not _is_number_non_bool(v):
            results.append(
                ValidationResult(
                    level="error",
                    message=(
                        f"{cfg_prefix}.{key} must be a number (not bool, string, list, or dict), "
                        f"with 0 < value <= {hi}"
                    ),
                    section="code_analysis",
                    key=f"database.driver.config.{key}",
                    suggestion=f"Set {key} to a number greater than 0 and at most {hi}",
                )
            )
        else:
            fv = float(v)
            if fv <= lo or fv > hi:
                results.append(
                    ValidationResult(
                        level="error",
                        message=(
                            f"{cfg_prefix}.{key} must be greater than 0 and at most {hi}, "
                            f"got {v!r}"
                        ),
                        section="code_analysis",
                        key=f"database.driver.config.{key}",
                        suggestion=f"Use a value in (0, {hi}]",
                    )
                )


def validate_database_driver_section_impl(
    config_data: Dict[str, Any], results: List[ValidationResult]
) -> None:
    """Validate code_analysis.database.driver section."""
    code_analysis = config_data.get("code_analysis", {})
    if not code_analysis:
        return

    database = code_analysis.get("database", {})
    if not database:
        return

    driver = database.get("driver")
    if not driver:
        return

    if not isinstance(driver, dict):
        results.append(
            ValidationResult(
                level="error",
                message="code_analysis.database.driver must be a dictionary",
                section="code_analysis",
                key="database.driver",
                suggestion="Set database.driver to a dictionary with 'type' and 'config' keys",
            )
        )
        return

    driver_type = driver.get("type")
    if not driver_type:
        results.append(
            ValidationResult(
                level="error",
                message="code_analysis.database.driver.type is required",
                section="code_analysis",
                key="database.driver.type",
                suggestion="Add 'type' field to database.driver (e.g., 'sqlite_proxy', 'sqlite')",
            )
        )
    elif not isinstance(driver_type, str):
        results.append(
            ValidationResult(
                level="error",
                message=f"code_analysis.database.driver.type must be string, got {type(driver_type).__name__}",
                section="code_analysis",
                key="database.driver.type",
                suggestion="Set database.driver.type to a string value",
            )
        )
    else:
        valid_driver_types = ["sqlite", "sqlite_proxy", "postgres", "mysql"]
        if driver_type not in valid_driver_types:
            results.append(
                ValidationResult(
                    level="error",
                    message=f"code_analysis.database.driver.type '{driver_type}' is not supported. Valid types: {', '.join(valid_driver_types)}",
                    section="code_analysis",
                    key="database.driver.type",
                    suggestion=f"Use one of: {', '.join(valid_driver_types)}",
                )
            )

    driver_config = driver.get("config")
    if driver_config is None:
        results.append(
            ValidationResult(
                level="error",
                message="code_analysis.database.driver.config is required",
                section="code_analysis",
                key="database.driver.config",
                suggestion="Add 'config' field to database.driver with driver-specific configuration",
            )
        )
    elif not isinstance(driver_config, dict):
        results.append(
            ValidationResult(
                level="error",
                message=f"code_analysis.database.driver.config must be dictionary, got {type(driver_config).__name__}",
                section="code_analysis",
                key="database.driver.config",
                suggestion="Set database.driver.config to a dictionary",
            )
        )
    else:
        if isinstance(driver_type, str) and driver_type in (
            "sqlite",
            "sqlite_proxy",
        ):
            if "path" not in driver_config:
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.database.driver.config.path is required for sqlite/sqlite_proxy driver",
                        section="code_analysis",
                        key="database.driver.config.path",
                        suggestion="Add 'path' field to database.driver.config with database file path",
                    )
                )
            elif driver_config.get("path") and isinstance(
                driver_config.get("path"), str
            ):
                path_str = driver_config["path"]
                if not path_str.strip():
                    results.append(
                        ValidationResult(
                            level="error",
                            message="code_analysis.database.driver.config.path cannot be empty",
                            section="code_analysis",
                            key="database.driver.config.path",
                            suggestion="Set database.driver.config.path to a non-empty path string",
                        )
                    )

        if isinstance(driver_type, str) and driver_type == "postgres":
            dsn_val = driver_config.get("dsn")
            use_dsn = isinstance(dsn_val, str) and bool(str(dsn_val).strip())
            if not use_dsn:
                pw_inline = driver_config.get("password")
                if pw_inline is not None and str(pw_inline).strip():
                    results.append(
                        ValidationResult(
                            level="error",
                            message="code_analysis.database.driver.config.password must not be set; use password_env and a .env file",
                            section="code_analysis",
                            key="database.driver.config.password",
                            suggestion="Remove 'password' from config; set password_env (e.g. CODE_ANALYSIS_POSTGRES_PASSWORD) and put the secret in .env",
                        )
                    )
                for key, label in (
                    ("host", "host"),
                    ("user", "user"),
                    ("password_env", "password_env"),
                ):
                    v = driver_config.get(key)
                    if v is None or (isinstance(v, str) and not str(v).strip()):
                        results.append(
                            ValidationResult(
                                level="error",
                                message=f"code_analysis.database.driver.config.{key} is required for postgres driver (or use non-empty dsn)",
                                section="code_analysis",
                                key=f"database.driver.config.{key}",
                                suggestion=f"Set database.driver.config.{key} ({label})",
                            )
                        )
                dbn = driver_config.get("dbname") or driver_config.get("database")
                if dbn is None or not isinstance(dbn, str) or not str(dbn).strip():
                    results.append(
                        ValidationResult(
                            level="error",
                            message="code_analysis.database.driver.config.dbname (or database) is required for postgres driver",
                            section="code_analysis",
                            key="database.driver.config.dbname",
                            suggestion="Set dbname to the PostgreSQL database name",
                        )
                    )
                port_v = driver_config.get("port")
                if port_v is None:
                    results.append(
                        ValidationResult(
                            level="error",
                            message="code_analysis.database.driver.config.port is required for postgres driver",
                            section="code_analysis",
                            key="database.driver.config.port",
                            suggestion="Set port (e.g. 5432)",
                        )
                    )
                elif not isinstance(port_v, int):
                    results.append(
                        ValidationResult(
                            level="error",
                            message="code_analysis.database.driver.config.port must be an integer",
                            section="code_analysis",
                            key="database.driver.config.port",
                            suggestion="Set port to an integer (e.g. 5432)",
                        )
                    )

        if driver_type == "sqlite_proxy":
            worker_config = driver_config.get("worker_config")
            if worker_config and isinstance(worker_config, dict):
                command_timeout = worker_config.get("command_timeout")
                if command_timeout is not None:
                    if not isinstance(command_timeout, (int, float)):
                        results.append(
                            ValidationResult(
                                level="error",
                                message="code_analysis.database.driver.config.worker_config.command_timeout must be number",
                                section="code_analysis",
                                key="database.driver.config.worker_config.command_timeout",
                                suggestion="Set command_timeout to a number",
                            )
                        )
                    elif command_timeout <= 0:
                        results.append(
                            ValidationResult(
                                level="error",
                                message="code_analysis.database.driver.config.worker_config.command_timeout must be > 0",
                                section="code_analysis",
                                key="database.driver.config.worker_config.command_timeout",
                                suggestion="Set command_timeout to a positive value",
                            )
                        )

                poll_interval = worker_config.get("poll_interval")
                if poll_interval is not None:
                    if not isinstance(poll_interval, (int, float)):
                        results.append(
                            ValidationResult(
                                level="error",
                                message="code_analysis.database.driver.config.worker_config.poll_interval must be number",
                                section="code_analysis",
                                key="database.driver.config.worker_config.poll_interval",
                                suggestion="Set poll_interval to a number",
                            )
                        )
                    elif poll_interval <= 0:
                        results.append(
                            ValidationResult(
                                level="error",
                                message="code_analysis.database.driver.config.worker_config.poll_interval must be > 0",
                                section="code_analysis",
                                key="database.driver.config.worker_config.poll_interval",
                                suggestion="Set poll_interval to a positive value",
                            )
                        )

        if isinstance(driver_type, str) and driver_type in (
            "postgres",
            "sqlite",
            "sqlite_proxy",
        ):
            _validate_driver_retry_timeout_config(driver_config, results)

    rpc = database.get("rpc")
    if rpc is not None and isinstance(rpc, dict):
        shm_threshold = rpc.get("shm_threshold_bytes")
        if shm_threshold is not None:
            if not isinstance(shm_threshold, int):
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.database.rpc.shm_threshold_bytes must be integer",
                        section="code_analysis",
                        key="database.rpc.shm_threshold_bytes",
                        suggestion="Set shm_threshold_bytes to an integer (bytes)",
                    )
                )
            elif shm_threshold < 0:
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.database.rpc.shm_threshold_bytes must be >= 0",
                        section="code_analysis",
                        key="database.rpc.shm_threshold_bytes",
                        suggestion="Set shm_threshold_bytes to 0 or positive value",
                    )
                )
            elif shm_threshold > 104857600:  # 100 MB
                results.append(
                    ValidationResult(
                        level="warning",
                        message="code_analysis.database.rpc.shm_threshold_bytes > 100 MB may be excessive",
                        section="code_analysis",
                        key="database.rpc.shm_threshold_bytes",
                        suggestion="Consider lower threshold (e.g. 65536)",
                    )
                )
        shm_enabled = rpc.get("shm_enabled")
        if shm_enabled is not None and not isinstance(shm_enabled, bool):
            results.append(
                ValidationResult(
                    level="error",
                    message="code_analysis.database.rpc.shm_enabled must be boolean",
                    section="code_analysis",
                    key="database.rpc.shm_enabled",
                    suggestion="Set shm_enabled to true or false",
                )
            )
