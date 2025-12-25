"""
Configuration validator for code-analysis-server.

Validates configuration files for compatibility with mcp-proxy-adapter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import re
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
        self._validate_file_existence()
        self._validate_protocol_consistency()
        self._validate_uuid_format()

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
        if max_concurrent is not None and max_concurrent < 1:
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
        if retention is not None and retention < 0:
            self.validation_results.append(
                ValidationResult(
                    level="error",
                    message="queue_manager.completed_job_retention_seconds must be >= 0",
                    section="queue_manager",
                    key="completed_job_retention_seconds",
                    suggestion="Set completed_job_retention_seconds to 0 or higher",
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
            for field in ["cert", "key", "ca"]:
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
                for field in ["cert", "key", "ca"]:
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
