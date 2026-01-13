"""
Configuration validator for code-analysis-server.

Validates configuration files for compatibility with mcp-proxy-adapter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import re
import urllib.parse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


class ValidationResult:
    """Validation result with level, message, and optional details."""

    def __init__(
        self,
        level: str,
        message: str,
        section: Optional[str] = None,
        key: Optional[str] = None,
        suggestion: Optional[str] = None,
    ):
        """
        Initialize validation result.

        Args:
            level: Result level (error, warning, info)
            message: Validation message
            section: Configuration section (optional)
            key: Configuration key (optional)
            suggestion: Suggestion for fixing (optional)
        """
        self.level = level
        self.message = message
        self.section = section
        self.key = key
        self.suggestion = suggestion


class CodeAnalysisConfigValidator:
    """Validate configuration for code-analysis-server."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration validator.

        Args:
            config_path: Path to configuration file (optional)
        """
        self.config_path = config_path
        self.config_data: Dict[str, Any] = {}
        self.validation_results: List[ValidationResult] = []

    def load_config(self, config_path: Optional[str] = None) -> None:
        """
        Load configuration from file.

        Args:
            config_path: Path to configuration file
        """
        if config_path:
            self.config_path = config_path

        if not self.config_path:
            raise ValueError("No configuration path provided")

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config_data = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")
        except Exception as e:
            raise RuntimeError(f"Error loading configuration: {e}")

    def validate_config(
        self, config_data: Optional[Dict[str, Any]] = None
    ) -> List[ValidationResult]:
        """
        Validate configuration data.

        Args:
            config_data: Configuration data to validate (optional)

        Returns:
            List of validation results
        """
        if config_data is not None:
            self.config_data = config_data

        if not self.config_data:
            raise ValueError("No configuration data to validate")

        self.validation_results = []

        # Run all validations
        self._validate_required_sections()
        self._validate_server_section()
        self._validate_registration_section()
        self._validate_queue_manager_section()
        self._validate_code_analysis_section()
        self._validate_database_driver_section()
        self._validate_file_existence()
        self._validate_protocol_consistency()
        self._validate_uuid_format()
        self._validate_field_types()
        self._validate_field_values()

        return self.validation_results

    def _validate_required_sections(self) -> None:
        """Validate that required sections exist."""
        required_sections = ["server", "queue_manager"]
        for section in required_sections:
            if section not in self.config_data:
                self.validation_results.append(
                    ValidationResult(
                        level="error",
                        message=f"Required section '{section}' is missing",
                        section=section,
                        suggestion=f"Add '{section}' section to configuration",
                    )
                )

    def _validate_server_section(self) -> None:
        """Validate server section."""
        server = self.config_data.get("server", {})
        if not server:
            return

        # Validate required fields
        required_fields = ["host", "port", "protocol"]
        for field in required_fields:
            if field not in server:
                self.validation_results.append(
                    ValidationResult(
                        level="error",
                        message=f"Required field 'server.{field}' is missing",
                        section="server",
                        key=field,
                        suggestion=f"Add '{field}' to server section",
                    )
                )

        # Validate protocol
        protocol = server.get("protocol")
        if protocol and protocol not in ("http", "https", "mtls"):
            self.validation_results.append(
                ValidationResult(
                    level="error",
                    message=f"Invalid protocol '{protocol}'. Must be http, https, or mtls",
                    section="server",
                    key="protocol",
                    suggestion="Use 'http', 'https', or 'mtls'",
                )
            )

        # Validate SSL configuration for https/mtls
        if protocol in ("https", "mtls"):
            ssl = server.get("ssl")
            if not ssl:
                self.validation_results.append(
                    ValidationResult(
                        level="error",
                        message=f"SSL configuration is required for protocol '{protocol}'",
                        section="server",
                        key="ssl",
                        suggestion="Add 'ssl' section with cert, key, and ca",
                    )
                )
            else:
                required_ssl_fields = ["cert", "key"]
                if protocol == "mtls":
                    required_ssl_fields.append("ca")
                for field in required_ssl_fields:
                    if field not in ssl or not ssl[field]:
                        self.validation_results.append(
                            ValidationResult(
                                level="error",
                                message=f"Required SSL field 'server.ssl.{field}' is missing or empty",
                                section="server",
                                key=f"ssl.{field}",
                                suggestion=f"Add '{field}' to server.ssl section",
                            )
                        )

    def _validate_registration_section(self) -> None:
        """Validate registration section."""
        registration = self.config_data.get("registration", {})
        if not registration:
            return

        enabled = registration.get("enabled", False)
        if not enabled:
            return

        # Validate required fields when enabled
        required_fields = [
            "protocol",
            "register_url",
            "unregister_url",
            "instance_uuid",
        ]
        for field in required_fields:
            if field not in registration or not registration[field]:
                self.validation_results.append(
                    ValidationResult(
                        level="error",
                        message=f"Required field 'registration.{field}' is missing or empty when registration is enabled",
                        section="registration",
                        key=field,
                        suggestion=f"Add '{field}' to registration section",
                    )
                )

        # Validate SSL for https/mtls
        protocol = registration.get("protocol")
        if protocol in ("https", "mtls"):
            ssl = registration.get("ssl")
            if not ssl:
                self.validation_results.append(
                    ValidationResult(
                        level="error",
                        message=f"SSL configuration is required for registration protocol '{protocol}'",
                        section="registration",
                        key="ssl",
                        suggestion="Add 'ssl' section with cert, key, and ca",
                    )
                )

    def _validate_queue_manager_section(self) -> None:
        """Validate queue manager section."""
        queue_manager = self.config_data.get("queue_manager", {})
        if not queue_manager:
            return

        enabled = queue_manager.get("enabled", True)
        if not enabled:
            return

        # Validate max_concurrent_jobs
        max_concurrent = queue_manager.get("max_concurrent_jobs")
        if max_concurrent is not None:
            if not isinstance(max_concurrent, int):
                self.validation_results.append(
                    ValidationResult(
                        level="error",
                        message=f"queue_manager.max_concurrent_jobs must be int, got {type(max_concurrent).__name__}",
                        section="queue_manager",
                        key="max_concurrent_jobs",
                        suggestion="Set max_concurrent_jobs to an integer value",
                    )
                )
            elif max_concurrent < 1:
                self.validation_results.append(
                    ValidationResult(
                        level="error",
                        message="queue_manager.max_concurrent_jobs must be at least 1",
                        section="queue_manager",
                        key="max_concurrent_jobs",
                        suggestion="Set max_concurrent_jobs to 1 or higher",
                    )
                )

        # Validate retention
        retention = queue_manager.get("completed_job_retention_seconds")
        if retention is not None:
            if not isinstance(retention, int):
                self.validation_results.append(
                    ValidationResult(
                        level="error",
                        message=f"queue_manager.completed_job_retention_seconds must be int, got {type(retention).__name__}",
                        section="queue_manager",
                        key="completed_job_retention_seconds",
                        suggestion="Set completed_job_retention_seconds to an integer value",
                    )
                )
            elif retention < 0:
                self.validation_results.append(
                    ValidationResult(
                        level="error",
                        message="queue_manager.completed_job_retention_seconds must be >= 0",
                        section="queue_manager",
                        key="completed_job_retention_seconds",
                        suggestion="Set completed_job_retention_seconds to 0 or higher",
                    )
                )

    def _validate_code_analysis_section(self) -> None:
        """Validate code_analysis section."""
        code_analysis = self.config_data.get("code_analysis", {})
        if not code_analysis:
            return

        # Validate worker section
        worker = code_analysis.get("worker")
        if worker and isinstance(worker, dict):
            # Validate poll_interval
            poll_interval = worker.get("poll_interval")
            if poll_interval is not None and poll_interval < 1:
                self.validation_results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.worker.poll_interval must be at least 1",
                        section="code_analysis",
                        key="worker.poll_interval",
                        suggestion="Set poll_interval to 1 or higher",
                    )
                )

            # Validate batch_size
            batch_size = worker.get("batch_size")
            if batch_size is not None and batch_size < 1:
                self.validation_results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.worker.batch_size must be at least 1",
                        section="code_analysis",
                        key="worker.batch_size",
                        suggestion="Set batch_size to 1 or higher",
                    )
                )

            # Validate circuit_breaker section
            circuit_breaker = worker.get("circuit_breaker")
            if circuit_breaker and isinstance(circuit_breaker, dict):
                failure_threshold = circuit_breaker.get("failure_threshold")
                if failure_threshold is not None and failure_threshold < 1:
                    self.validation_results.append(
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
                    self.validation_results.append(
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
                    self.validation_results.append(
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
                    self.validation_results.append(
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
                    self.validation_results.append(
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
                    self.validation_results.append(
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
                    self.validation_results.append(
                        ValidationResult(
                            level="error",
                            message="code_analysis.worker.circuit_breaker.backoff_multiplier must be >= 1",
                            section="code_analysis",
                            key="worker.circuit_breaker.backoff_multiplier",
                            suggestion="Set backoff_multiplier to 1 or higher",
                        )
                    )

            # Validate batch_processor section
            batch_processor = worker.get("batch_processor")
            if batch_processor and isinstance(batch_processor, dict):
                max_empty_iterations = batch_processor.get("max_empty_iterations")
                if max_empty_iterations is not None and max_empty_iterations < 1:
                    self.validation_results.append(
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
                    self.validation_results.append(
                        ValidationResult(
                            level="error",
                            message="code_analysis.worker.batch_processor.empty_delay must be >= 0",
                            section="code_analysis",
                            key="worker.batch_processor.empty_delay",
                            suggestion="Set empty_delay to 0 or higher",
                        )
                    )

    def _validate_database_driver_section(self) -> None:
        """Validate code_analysis.database.driver section."""
        code_analysis = self.config_data.get("code_analysis", {})
        if not code_analysis:
            return

        database = code_analysis.get("database", {})
        if not database:
            return

        driver = database.get("driver")
        if not driver:
            return

        # Validate driver is a dict
        if not isinstance(driver, dict):
            self.validation_results.append(
                ValidationResult(
                    level="error",
                    message="code_analysis.database.driver must be a dictionary",
                    section="code_analysis",
                    key="database.driver",
                    suggestion="Set database.driver to a dictionary with 'type' and 'config' keys",
                )
            )
            return

        # Validate required fields
        driver_type = driver.get("type")
        if not driver_type:
            self.validation_results.append(
                ValidationResult(
                    level="error",
                    message="code_analysis.database.driver.type is required",
                    section="code_analysis",
                    key="database.driver.type",
                    suggestion="Add 'type' field to database.driver (e.g., 'sqlite_proxy', 'sqlite')",
                )
            )
        elif not isinstance(driver_type, str):
            self.validation_results.append(
                ValidationResult(
                    level="error",
                    message=f"code_analysis.database.driver.type must be string, got {type(driver_type).__name__}",
                    section="code_analysis",
                    key="database.driver.type",
                    suggestion="Set database.driver.type to a string value",
                )
            )
        else:
            # Validate driver type is supported
            valid_driver_types = ["sqlite", "sqlite_proxy", "postgres", "mysql"]
            if driver_type not in valid_driver_types:
                self.validation_results.append(
                    ValidationResult(
                        level="error",
                        message=f"code_analysis.database.driver.type '{driver_type}' is not supported. Valid types: {', '.join(valid_driver_types)}",
                        section="code_analysis",
                        key="database.driver.type",
                        suggestion=f"Use one of: {', '.join(valid_driver_types)}",
                    )
                )

        # Validate config field
        driver_config = driver.get("config")
        if not driver_config:
            self.validation_results.append(
                ValidationResult(
                    level="error",
                    message="code_analysis.database.driver.config is required",
                    section="code_analysis",
                    key="database.driver.config",
                    suggestion="Add 'config' field to database.driver with driver-specific configuration",
                )
            )
        elif not isinstance(driver_config, dict):
            self.validation_results.append(
                ValidationResult(
                    level="error",
                    message=f"code_analysis.database.driver.config must be dictionary, got {type(driver_config).__name__}",
                    section="code_analysis",
                    key="database.driver.config",
                    suggestion="Set database.driver.config to a dictionary",
                )
            )
        else:
            # Validate driver-specific config requirements
            if driver_type in ("sqlite", "sqlite_proxy"):
                if "path" not in driver_config:
                    self.validation_results.append(
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
                    # Validate path format (should be a valid path string)
                    path_str = driver_config["path"]
                    if not path_str.strip():
                        self.validation_results.append(
                            ValidationResult(
                                level="error",
                                message="code_analysis.database.driver.config.path cannot be empty",
                                section="code_analysis",
                                key="database.driver.config.path",
                                suggestion="Set database.driver.config.path to a non-empty path string",
                            )
                        )

            # Validate worker_config for sqlite_proxy
            if driver_type == "sqlite_proxy":
                worker_config = driver_config.get("worker_config")
                if worker_config and isinstance(worker_config, dict):
                    command_timeout = worker_config.get("command_timeout")
                    if command_timeout is not None:
                        if not isinstance(command_timeout, (int, float)):
                            self.validation_results.append(
                                ValidationResult(
                                    level="error",
                                    message="code_analysis.database.driver.config.worker_config.command_timeout must be number",
                                    section="code_analysis",
                                    key="database.driver.config.worker_config.command_timeout",
                                    suggestion="Set command_timeout to a number",
                                )
                            )
                        elif command_timeout <= 0:
                            self.validation_results.append(
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
                            self.validation_results.append(
                                ValidationResult(
                                    level="error",
                                    message="code_analysis.database.driver.config.worker_config.poll_interval must be number",
                                    section="code_analysis",
                                    key="database.driver.config.worker_config.poll_interval",
                                    suggestion="Set poll_interval to a number",
                                )
                            )
                        elif poll_interval <= 0:
                            self.validation_results.append(
                                ValidationResult(
                                    level="error",
                                    message="code_analysis.database.driver.config.worker_config.poll_interval must be > 0",
                                    section="code_analysis",
                                    key="database.driver.config.worker_config.poll_interval",
                                    suggestion="Set poll_interval to a positive value",
                                )
                            )

    def _validate_file_existence(self) -> None:
        """Validate that referenced files exist."""
        if not self.config_path:
            return

        config_dir = Path(self.config_path).parent

        # Check server SSL files
        server = self.config_data.get("server", {})
        ssl = server.get("ssl")
        if ssl:
            for field in ["cert", "key", "ca", "crl"]:
                if field in ssl and ssl[field]:
                    file_path = Path(ssl[field])
                    if not file_path.is_absolute():
                        file_path = config_dir / file_path
                    if not file_path.exists():
                        self.validation_results.append(
                            ValidationResult(
                                level="error",
                                message=f"SSL file not found: {ssl[field]}",
                                section="server",
                                key=f"ssl.{field}",
                                suggestion=f"Ensure file exists at {file_path}",
                            )
                        )

        # Check registration SSL files
        registration = self.config_data.get("registration", {})
        if registration.get("enabled"):
            reg_ssl = registration.get("ssl")
            if reg_ssl:
                for field in ["cert", "key", "ca", "crl"]:
                    if field in reg_ssl and reg_ssl[field]:
                        file_path = Path(reg_ssl[field])
                        if not file_path.is_absolute():
                            file_path = config_dir / file_path
                        if not file_path.exists():
                            self.validation_results.append(
                                ValidationResult(
                                    level="error",
                                    message=f"Registration SSL file not found: {reg_ssl[field]}",
                                    section="registration",
                                    key=f"ssl.{field}",
                                    suggestion=f"Ensure file exists at {file_path}",
                                )
                            )

        # Check code_analysis SSL files (chunker and embedding)
        code_analysis = self.config_data.get("code_analysis", {})
        if code_analysis:
            # Check chunker SSL files
            chunker = code_analysis.get("chunker", {})
            if chunker:
                for field in ["cert_file", "key_file", "ca_cert_file", "crl_file"]:
                    if field in chunker and chunker[field]:
                        file_path = Path(chunker[field])
                        if not file_path.is_absolute():
                            file_path = config_dir / file_path
                        if not file_path.exists():
                            self.validation_results.append(
                                ValidationResult(
                                    level="error",
                                    message=f"Chunker SSL file not found: {chunker[field]}",
                                    section="code_analysis",
                                    key=f"chunker.{field}",
                                    suggestion=f"Ensure file exists at {file_path}",
                                )
                            )

            # Check embedding SSL files
            embedding = code_analysis.get("embedding", {})
            if embedding:
                for field in ["cert_file", "key_file", "ca_cert_file", "crl_file"]:
                    if field in embedding and embedding[field]:
                        file_path = Path(embedding[field])
                        if not file_path.is_absolute():
                            file_path = config_dir / file_path
                        if not file_path.exists():
                            self.validation_results.append(
                                ValidationResult(
                                    level="error",
                                    message=f"Embedding SSL file not found: {embedding[field]}",
                                    section="code_analysis",
                                    key=f"embedding.{field}",
                                    suggestion=f"Ensure file exists at {file_path}",
                                )
                            )

            # Check database driver config files
            database = code_analysis.get("database", {})
            if database:
                driver = database.get("driver", {})
                if driver and isinstance(driver, dict):
                    driver_config = driver.get("config", {})
                    if driver_config and isinstance(driver_config, dict):
                        # Check database path (for sqlite/sqlite_proxy)
                        db_path = driver_config.get("path")
                        if db_path and isinstance(db_path, str):
                            file_path = Path(db_path)
                            if not file_path.is_absolute():
                                file_path = config_dir / file_path
                            # Note: database file may not exist yet (will be created on first use)
                            # So we only check if parent directory exists
                            if (
                                file_path.parent.exists()
                                and not file_path.parent.is_dir()
                            ):
                                self.validation_results.append(
                                    ValidationResult(
                                        level="error",
                                        message=f"Database path parent is not a directory: {db_path}",
                                        section="code_analysis",
                                        key="database.driver.config.path",
                                        suggestion=f"Ensure parent directory exists and is a directory: {file_path.parent}",
                                    )
                                )
                            elif not file_path.parent.exists():
                                # This is a warning, not an error, as parent dir will be created
                                self.validation_results.append(
                                    ValidationResult(
                                        level="warning",
                                        message=f"Database path parent directory does not exist: {file_path.parent}",
                                        section="code_analysis",
                                        key="database.driver.config.path",
                                        suggestion=f"Parent directory will be created automatically: {file_path.parent}",
                                    )
                                )

    def _validate_protocol_consistency(self) -> None:
        """Validate protocol consistency across sections."""
        server_protocol = self.config_data.get("server", {}).get("protocol")
        registration = self.config_data.get("registration", {})
        if registration.get("enabled"):
            reg_protocol = registration.get("protocol")
            # Registration protocol should match server protocol for consistency
            if reg_protocol and server_protocol and reg_protocol != server_protocol:
                self.validation_results.append(
                    ValidationResult(
                        level="warning",
                        message=f"Registration protocol '{reg_protocol}' differs from server protocol '{server_protocol}'",
                        section="registration",
                        key="protocol",
                        suggestion="Consider using the same protocol for consistency",
                    )
                )

    def _validate_uuid_format(self) -> None:
        """Validate UUID format in configuration."""
        registration = self.config_data.get("registration", {})
        if registration.get("enabled"):
            instance_uuid = registration.get("instance_uuid")
            if instance_uuid and not self._is_valid_uuid4(str(instance_uuid)):
                self.validation_results.append(
                    ValidationResult(
                        level="error",
                        message=f"Invalid UUID format in registration.instance_uuid: {instance_uuid}",
                        section="registration",
                        key="instance_uuid",
                        suggestion="Use a valid UUID4 format (e.g., 550e8400-e29b-41d4-a716-446655440000)",
                    )
                )

    def _is_valid_uuid4(self, uuid_str: str) -> bool:
        """Check if string is a valid UUID4."""
        uuid_pattern = (
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        )
        return bool(re.match(uuid_pattern, uuid_str, re.IGNORECASE))

    def _validate_field_type(
        self, section: str, key: str, value: Any, expected_type: type | tuple[type, ...]
    ) -> bool:
        """
        Validate field type.

        Args:
            section: Configuration section name.
            key: Field key.
            value: Field value.
            expected_type: Expected type.

        Returns:
            True if type is valid, False otherwise.
        """
        if value is None:
            return True  # None is allowed for optional fields

        if not isinstance(value, expected_type):
            self.validation_results.append(
                ValidationResult(
                    level="error",
                    message=f"Field '{section}.{key}' must be {expected_type.__name__}, got {type(value).__name__}",
                    section=section,
                    key=key,
                    suggestion=f"Change '{section}.{key}' to {expected_type.__name__} type",
                )
            )
            return False
        return True

    def _validate_url_format(self, url: str) -> bool:
        """
        Validate URL format.

        Args:
            url: URL string to validate.

        Returns:
            True if URL is valid, False otherwise.
        """
        try:
            result = urllib.parse.urlparse(url)
            return bool(result.scheme and result.netloc)
        except Exception:
            return False

    def _validate_port_range(self, port: int) -> bool:
        """
        Validate port number range.

        Args:
            port: Port number.

        Returns:
            True if port is in valid range (1-65535), False otherwise.
        """
        return 1 <= port <= 65535

    def _validate_field_types(self) -> None:
        """Validate types of all configuration fields."""
        # Server section
        server = self.config_data.get("server", {})
        if server:
            self._validate_field_type("server", "host", server.get("host"), str)
            self._validate_field_type("server", "port", server.get("port"), int)
            self._validate_field_type("server", "protocol", server.get("protocol"), str)
            self._validate_field_type(
                "server", "servername", server.get("servername"), str
            )
            self._validate_field_type(
                "server", "advertised_host", server.get("advertised_host"), str
            )
            self._validate_field_type("server", "debug", server.get("debug"), bool)
            self._validate_field_type(
                "server", "log_level", server.get("log_level"), str
            )
            self._validate_field_type("server", "log_dir", server.get("log_dir"), str)

            # Server SSL
            ssl = server.get("ssl")
            if ssl and isinstance(ssl, dict):
                self._validate_field_type(
                    "server", "ssl.cert", ssl.get("cert"), (str, type(None))
                )
                self._validate_field_type(
                    "server", "ssl.key", ssl.get("key"), (str, type(None))
                )
                self._validate_field_type(
                    "server", "ssl.ca", ssl.get("ca"), (str, type(None))
                )
                self._validate_field_type(
                    "server", "ssl.crl", ssl.get("crl"), (str, type(None))
                )
                self._validate_field_type(
                    "server", "ssl.dnscheck", ssl.get("dnscheck"), bool
                )
                self._validate_field_type(
                    "server", "ssl.check_hostname", ssl.get("check_hostname"), bool
                )

        # Registration section
        registration = self.config_data.get("registration", {})
        if registration:
            self._validate_field_type(
                "registration", "enabled", registration.get("enabled"), bool
            )
            self._validate_field_type(
                "registration", "protocol", registration.get("protocol"), str
            )
            self._validate_field_type(
                "registration", "register_url", registration.get("register_url"), str
            )
            self._validate_field_type(
                "registration",
                "unregister_url",
                registration.get("unregister_url"),
                str,
            )
            self._validate_field_type(
                "registration",
                "heartbeat_interval",
                registration.get("heartbeat_interval"),
                int,
            )
            self._validate_field_type(
                "registration", "server_id", registration.get("server_id"), str
            )
            self._validate_field_type(
                "registration", "server_name", registration.get("server_name"), str
            )
            self._validate_field_type(
                "registration", "instance_uuid", registration.get("instance_uuid"), str
            )
            self._validate_field_type(
                "registration",
                "auto_on_startup",
                registration.get("auto_on_startup"),
                bool,
            )
            self._validate_field_type(
                "registration",
                "auto_on_shutdown",
                registration.get("auto_on_shutdown"),
                bool,
            )

            # Registration SSL
            reg_ssl = registration.get("ssl")
            if reg_ssl and isinstance(reg_ssl, dict):
                self._validate_field_type(
                    "registration", "ssl.cert", reg_ssl.get("cert"), (str, type(None))
                )
                self._validate_field_type(
                    "registration", "ssl.key", reg_ssl.get("key"), (str, type(None))
                )
                self._validate_field_type(
                    "registration", "ssl.ca", reg_ssl.get("ca"), (str, type(None))
                )
                self._validate_field_type(
                    "registration", "ssl.crl", reg_ssl.get("crl"), (str, type(None))
                )
                self._validate_field_type(
                    "registration", "ssl.dnscheck", reg_ssl.get("dnscheck"), bool
                )
                self._validate_field_type(
                    "registration",
                    "ssl.check_hostname",
                    reg_ssl.get("check_hostname"),
                    bool,
                )

        # Queue manager section
        queue_manager = self.config_data.get("queue_manager", {})
        if queue_manager:
            self._validate_field_type(
                "queue_manager", "enabled", queue_manager.get("enabled"), bool
            )
            self._validate_field_type(
                "queue_manager", "in_memory", queue_manager.get("in_memory"), bool
            )
            self._validate_field_type(
                "queue_manager",
                "shutdown_timeout",
                queue_manager.get("shutdown_timeout"),
                (int, float),
            )
            self._validate_field_type(
                "queue_manager",
                "max_concurrent_jobs",
                queue_manager.get("max_concurrent_jobs"),
                int,
            )
            self._validate_field_type(
                "queue_manager",
                "max_queue_size",
                queue_manager.get("max_queue_size"),
                (int, type(None)),
            )
            self._validate_field_type(
                "queue_manager",
                "completed_job_retention_seconds",
                queue_manager.get("completed_job_retention_seconds"),
                int,
            )

        # Code analysis section
        code_analysis = self.config_data.get("code_analysis", {})
        if code_analysis:
            self._validate_field_type(
                "code_analysis", "host", code_analysis.get("host"), str
            )
            self._validate_field_type(
                "code_analysis", "port", code_analysis.get("port"), int
            )
            self._validate_field_type(
                "code_analysis", "log", code_analysis.get("log"), str
            )
            self._validate_field_type(
                "code_analysis", "db_path", code_analysis.get("db_path"), str
            )
            self._validate_field_type(
                "code_analysis",
                "faiss_index_path",
                code_analysis.get("faiss_index_path"),
                str,
            )
            self._validate_field_type(
                "code_analysis", "vector_dim", code_analysis.get("vector_dim"), int
            )
            self._validate_field_type(
                "code_analysis",
                "min_chunk_length",
                code_analysis.get("min_chunk_length"),
                int,
            )
            self._validate_field_type(
                "code_analysis",
                "vectorization_retry_attempts",
                code_analysis.get("vectorization_retry_attempts"),
                int,
            )
            self._validate_field_type(
                "code_analysis",
                "vectorization_retry_delay",
                code_analysis.get("vectorization_retry_delay"),
                (int, float),
            )

            # Chunker section
            chunker = code_analysis.get("chunker", {})
            if chunker and isinstance(chunker, dict):
                self._validate_field_type(
                    "code_analysis", "chunker.enabled", chunker.get("enabled"), bool
                )
                self._validate_field_type(
                    "code_analysis", "chunker.url", chunker.get("url"), str
                )
                self._validate_field_type(
                    "code_analysis", "chunker.port", chunker.get("port"), int
                )
                self._validate_field_type(
                    "code_analysis", "chunker.protocol", chunker.get("protocol"), str
                )
                self._validate_field_type(
                    "code_analysis",
                    "chunker.cert_file",
                    chunker.get("cert_file"),
                    (str, type(None)),
                )
                self._validate_field_type(
                    "code_analysis",
                    "chunker.key_file",
                    chunker.get("key_file"),
                    (str, type(None)),
                )
                self._validate_field_type(
                    "code_analysis",
                    "chunker.ca_cert_file",
                    chunker.get("ca_cert_file"),
                    (str, type(None)),
                )
                self._validate_field_type(
                    "code_analysis",
                    "chunker.crl_file",
                    chunker.get("crl_file"),
                    (str, type(None)),
                )
                self._validate_field_type(
                    "code_analysis",
                    "chunker.retry_attempts",
                    chunker.get("retry_attempts"),
                    int,
                )
                self._validate_field_type(
                    "code_analysis",
                    "chunker.retry_delay",
                    chunker.get("retry_delay"),
                    (int, float),
                )
                self._validate_field_type(
                    "code_analysis",
                    "chunker.timeout",
                    chunker.get("timeout"),
                    (int, float, type(None)),
                )

            # Embedding section
            embedding = code_analysis.get("embedding", {})
            if embedding and isinstance(embedding, dict):
                self._validate_field_type(
                    "code_analysis", "embedding.enabled", embedding.get("enabled"), bool
                )
                self._validate_field_type(
                    "code_analysis", "embedding.host", embedding.get("host"), str
                )
                self._validate_field_type(
                    "code_analysis", "embedding.port", embedding.get("port"), int
                )
                self._validate_field_type(
                    "code_analysis",
                    "embedding.protocol",
                    embedding.get("protocol"),
                    str,
                )
                self._validate_field_type(
                    "code_analysis",
                    "embedding.cert_file",
                    embedding.get("cert_file"),
                    (str, type(None)),
                )
                self._validate_field_type(
                    "code_analysis",
                    "embedding.key_file",
                    embedding.get("key_file"),
                    (str, type(None)),
                )
                self._validate_field_type(
                    "code_analysis",
                    "embedding.ca_cert_file",
                    embedding.get("ca_cert_file"),
                    (str, type(None)),
                )
                self._validate_field_type(
                    "code_analysis",
                    "embedding.crl_file",
                    embedding.get("crl_file"),
                    (str, type(None)),
                )
                self._validate_field_type(
                    "code_analysis",
                    "embedding.retry_attempts",
                    embedding.get("retry_attempts"),
                    int,
                )
                self._validate_field_type(
                    "code_analysis",
                    "embedding.retry_delay",
                    embedding.get("retry_delay"),
                    (int, float),
                )
                self._validate_field_type(
                    "code_analysis",
                    "embedding.timeout",
                    embedding.get("timeout"),
                    (int, float, type(None)),
                )

            # Database driver section
            database = code_analysis.get("database", {})
            if database and isinstance(database, dict):
                driver = database.get("driver", {})
                if driver and isinstance(driver, dict):
                    self._validate_field_type(
                        "code_analysis", "database.driver.type", driver.get("type"), str
                    )
                    self._validate_field_type(
                        "code_analysis",
                        "database.driver.config",
                        driver.get("config"),
                        dict,
                    )

                    driver_config = driver.get("config", {})
                    if driver_config and isinstance(driver_config, dict):
                        self._validate_field_type(
                            "code_analysis",
                            "database.driver.config.path",
                            driver_config.get("path"),
                            (str, type(None)),
                        )
                        self._validate_field_type(
                            "code_analysis",
                            "database.driver.config.backup_dir",
                            driver_config.get("backup_dir"),
                            (str, type(None)),
                        )
                        self._validate_field_type(
                            "code_analysis",
                            "database.driver.config.worker_config",
                            driver_config.get("worker_config"),
                            (dict, type(None)),
                        )

                        worker_config = driver_config.get("worker_config", {})
                        if worker_config and isinstance(worker_config, dict):
                            self._validate_field_type(
                                "code_analysis",
                                "database.driver.config.worker_config.command_timeout",
                                worker_config.get("command_timeout"),
                                (int, float, type(None)),
                            )
                            self._validate_field_type(
                                "code_analysis",
                                "database.driver.config.worker_config.poll_interval",
                                worker_config.get("poll_interval"),
                                (int, float, type(None)),
                            )

    def _validate_field_values(self) -> None:
        """Validate values of configuration fields."""
        # Server section
        server = self.config_data.get("server", {})
        if server:
            port = server.get("port")
            if port is not None and isinstance(port, int):
                if not self._validate_port_range(port):
                    self.validation_results.append(
                        ValidationResult(
                            level="error",
                            message=f"Server port {port} is out of valid range (1-65535)",
                            section="server",
                            key="port",
                            suggestion="Set port to a value between 1 and 65535",
                        )
                    )

        # Registration section
        registration = self.config_data.get("registration", {})
        if registration:
            register_url = registration.get("register_url")
            if register_url and isinstance(register_url, str):
                if not self._validate_url_format(register_url):
                    self.validation_results.append(
                        ValidationResult(
                            level="error",
                            message=f"Invalid URL format in registration.register_url: {register_url}",
                            section="registration",
                            key="register_url",
                            suggestion="Use a valid URL format (e.g., https://host:port/path)",
                        )
                    )

            unregister_url = registration.get("unregister_url")
            if unregister_url and isinstance(unregister_url, str):
                if not self._validate_url_format(unregister_url):
                    self.validation_results.append(
                        ValidationResult(
                            level="error",
                            message=f"Invalid URL format in registration.unregister_url: {unregister_url}",
                            section="registration",
                            key="unregister_url",
                            suggestion="Use a valid URL format (e.g., https://host:port/path)",
                        )
                    )

            heartbeat = registration.get("heartbeat", {})
            if heartbeat and isinstance(heartbeat, dict):
                heartbeat_url = heartbeat.get("url")
                if heartbeat_url and isinstance(heartbeat_url, str):
                    if not self._validate_url_format(heartbeat_url):
                        self.validation_results.append(
                            ValidationResult(
                                level="error",
                                message=f"Invalid URL format in registration.heartbeat.url: {heartbeat_url}",
                                section="registration",
                                key="heartbeat.url",
                                suggestion="Use a valid URL format (e.g., https://host:port/path)",
                            )
                        )

        # Code analysis section
        code_analysis = self.config_data.get("code_analysis", {})
        if code_analysis:
            port = code_analysis.get("port")
            if port is not None and isinstance(port, int):
                if not self._validate_port_range(port):
                    self.validation_results.append(
                        ValidationResult(
                            level="error",
                            message=f"Code analysis port {port} is out of valid range (1-65535)",
                            section="code_analysis",
                            key="port",
                            suggestion="Set port to a value between 1 and 65535",
                        )
                    )

            # Chunker section
            chunker = code_analysis.get("chunker", {})
            if chunker and isinstance(chunker, dict):
                port = chunker.get("port")
                if port is not None and isinstance(port, int):
                    if not self._validate_port_range(port):
                        self.validation_results.append(
                            ValidationResult(
                                level="error",
                                message=f"Chunker port {port} is out of valid range (1-65535)",
                                section="code_analysis",
                                key="chunker.port",
                                suggestion="Set port to a value between 1 and 65535",
                            )
                        )

            # Embedding section
            embedding = code_analysis.get("embedding", {})
            if embedding and isinstance(embedding, dict):
                port = embedding.get("port")
                if port is not None and isinstance(port, int):
                    if not self._validate_port_range(port):
                        self.validation_results.append(
                            ValidationResult(
                                level="error",
                                message=f"Embedding port {port} is out of valid range (1-65535)",
                                section="code_analysis",
                                key="embedding.port",
                                suggestion="Set port to a value between 1 and 65535",
                            )
                        )

    def get_validation_summary(self) -> Dict[str, Any]:
        """
        Get a summary of validation results.

        Returns:
            Dictionary with validation summary
        """
        error_count = sum(1 for r in self.validation_results if r.level == "error")
        warning_count = sum(1 for r in self.validation_results if r.level == "warning")
        info_count = sum(1 for r in self.validation_results if r.level == "info")

        return {
            "total_issues": len(self.validation_results),
            "errors": error_count,
            "warnings": warning_count,
            "info": info_count,
            "is_valid": error_count == 0,
        }

    def validate_file(
        self, config_path: str
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Validate configuration file.

        Args:
            config_path: Path to configuration file

        Returns:
            Tuple of (is_valid, error_message, config_data)
        """
        try:
            self.load_config(config_path)
            self.validate_config()
            summary = self.get_validation_summary()

            if summary["is_valid"]:
                return True, None, self.config_data
            else:
                errors = [
                    r.message for r in self.validation_results if r.level == "error"
                ]
                return False, "; ".join(errors), None
        except Exception as e:
            return False, str(e), None
