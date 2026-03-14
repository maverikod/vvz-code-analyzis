"""
Field type validation for config sections (server, registration, queue_manager, code_analysis).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, List

from .field_types_code_analysis import validate_field_types_code_analysis_impl
from .helpers import validate_field_type
from .result import ValidationResult


def validate_field_types_impl(
    config_data: Dict[str, Any], results: List[ValidationResult]
) -> None:
    """Validate types of all configuration fields."""
    server = config_data.get("server", {})
    if server:
        validate_field_type(results, "server", "host", server.get("host"), str)
        validate_field_type(results, "server", "port", server.get("port"), int)
        validate_field_type(results, "server", "protocol", server.get("protocol"), str)
        validate_field_type(
            results, "server", "servername", server.get("servername"), str
        )
        validate_field_type(
            results,
            "server",
            "advertised_host",
            server.get("advertised_host"),
            str,
        )
        validate_field_type(results, "server", "debug", server.get("debug"), bool)
        validate_field_type(
            results, "server", "log_level", server.get("log_level"), str
        )
        validate_field_type(results, "server", "log_dir", server.get("log_dir"), str)

        ssl = server.get("ssl")
        if ssl and isinstance(ssl, dict):
            validate_field_type(
                results,
                "server",
                "ssl.cert",
                ssl.get("cert"),
                (str, type(None)),
            )
            validate_field_type(
                results,
                "server",
                "ssl.key",
                ssl.get("key"),
                (str, type(None)),
            )
            validate_field_type(
                results, "server", "ssl.ca", ssl.get("ca"), (str, type(None))
            )
            validate_field_type(
                results, "server", "ssl.crl", ssl.get("crl"), (str, type(None))
            )
            validate_field_type(
                results,
                "server",
                "ssl.dnscheck",
                ssl.get("dnscheck"),
                bool,
            )
            validate_field_type(
                results,
                "server",
                "ssl.check_hostname",
                ssl.get("check_hostname"),
                bool,
            )

    registration = config_data.get("registration", {})
    if registration:
        validate_field_type(
            results,
            "registration",
            "enabled",
            registration.get("enabled"),
            bool,
        )
        validate_field_type(
            results,
            "registration",
            "protocol",
            registration.get("protocol"),
            str,
        )
        validate_field_type(
            results,
            "registration",
            "register_url",
            registration.get("register_url"),
            str,
        )
        validate_field_type(
            results,
            "registration",
            "unregister_url",
            registration.get("unregister_url"),
            str,
        )
        validate_field_type(
            results,
            "registration",
            "heartbeat_interval",
            registration.get("heartbeat_interval"),
            int,
        )
        validate_field_type(
            results,
            "registration",
            "server_id",
            registration.get("server_id"),
            str,
        )
        validate_field_type(
            results,
            "registration",
            "server_name",
            registration.get("server_name"),
            str,
        )
        validate_field_type(
            results,
            "registration",
            "instance_uuid",
            registration.get("instance_uuid"),
            str,
        )
        validate_field_type(
            results,
            "registration",
            "auto_on_startup",
            registration.get("auto_on_startup"),
            bool,
        )
        validate_field_type(
            results,
            "registration",
            "auto_on_shutdown",
            registration.get("auto_on_shutdown"),
            bool,
        )

        reg_ssl = registration.get("ssl")
        if reg_ssl and isinstance(reg_ssl, dict):
            validate_field_type(
                results,
                "registration",
                "ssl.cert",
                reg_ssl.get("cert"),
                (str, type(None)),
            )
            validate_field_type(
                results,
                "registration",
                "ssl.key",
                reg_ssl.get("key"),
                (str, type(None)),
            )
            validate_field_type(
                results,
                "registration",
                "ssl.ca",
                reg_ssl.get("ca"),
                (str, type(None)),
            )
            validate_field_type(
                results,
                "registration",
                "ssl.crl",
                reg_ssl.get("crl"),
                (str, type(None)),
            )
            validate_field_type(
                results,
                "registration",
                "ssl.dnscheck",
                reg_ssl.get("dnscheck"),
                bool,
            )
            validate_field_type(
                results,
                "registration",
                "ssl.check_hostname",
                reg_ssl.get("check_hostname"),
                bool,
            )

    queue_manager = config_data.get("queue_manager", {})
    if queue_manager:
        validate_field_type(
            results,
            "queue_manager",
            "enabled",
            queue_manager.get("enabled"),
            bool,
        )
        validate_field_type(
            results,
            "queue_manager",
            "in_memory",
            queue_manager.get("in_memory"),
            bool,
        )
        validate_field_type(
            results,
            "queue_manager",
            "shutdown_timeout",
            queue_manager.get("shutdown_timeout"),
            (int, float),
        )
        validate_field_type(
            results,
            "queue_manager",
            "max_concurrent_jobs",
            queue_manager.get("max_concurrent_jobs"),
            int,
        )
        validate_field_type(
            results,
            "queue_manager",
            "max_queue_size",
            queue_manager.get("max_queue_size"),
            (int, type(None)),
        )
        validate_field_type(
            results,
            "queue_manager",
            "completed_job_retention_seconds",
            queue_manager.get("completed_job_retention_seconds"),
            int,
        )

    validate_field_types_code_analysis_impl(config_data, results)
