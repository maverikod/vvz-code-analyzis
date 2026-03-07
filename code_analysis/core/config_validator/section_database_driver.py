"""
Database driver section validation (code_analysis.database.driver, rpc).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, List

from .result import ValidationResult


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
