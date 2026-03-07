"""
Field value validation (port range, URL format, scan_interval, etc.).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, List

from .helpers import validate_port_range, validate_url_format
from .result import ValidationResult


def validate_field_values_impl(
    config_data: Dict[str, Any], results: List[ValidationResult]
) -> None:
    """Validate values of configuration fields."""
    server = config_data.get("server", {})
    if server:
        port = server.get("port")
        if port is not None and isinstance(port, int):
            if not validate_port_range(port):
                results.append(
                    ValidationResult(
                        level="error",
                        message=f"Server port {port} is out of valid range (1-65535)",
                        section="server",
                        key="port",
                        suggestion="Set port to a value between 1 and 65535",
                    )
                )

    registration = config_data.get("registration", {})
    if registration:
        register_url = registration.get("register_url")
        if register_url and isinstance(register_url, str):
            if not validate_url_format(register_url):
                results.append(
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
            if not validate_url_format(unregister_url):
                results.append(
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
                if not validate_url_format(heartbeat_url):
                    results.append(
                        ValidationResult(
                            level="error",
                            message=f"Invalid URL format in registration.heartbeat.url: {heartbeat_url}",
                            section="registration",
                            key="heartbeat.url",
                            suggestion="Use a valid URL format (e.g., https://host:port/path)",
                        )
                    )

    code_analysis = config_data.get("code_analysis", {})
    if code_analysis:
        port = code_analysis.get("port")
        if port is not None and isinstance(port, int):
            if not validate_port_range(port):
                results.append(
                    ValidationResult(
                        level="error",
                        message=f"Code analysis port {port} is out of valid range (1-65535)",
                        section="code_analysis",
                        key="port",
                        suggestion="Set port to a value between 1 and 65535",
                    )
                )

        chunker = code_analysis.get("chunker", {})
        if chunker and isinstance(chunker, dict):
            port = chunker.get("port")
            if port is not None and isinstance(port, int):
                if not validate_port_range(port):
                    results.append(
                        ValidationResult(
                            level="error",
                            message=f"Chunker port {port} is out of valid range (1-65535)",
                            section="code_analysis",
                            key="chunker.port",
                            suggestion="Set port to a value between 1 and 65535",
                        )
                    )

        embedding = code_analysis.get("embedding", {})
        if embedding and isinstance(embedding, dict):
            port = embedding.get("port")
            if port is not None and isinstance(port, int):
                if not validate_port_range(port):
                    results.append(
                        ValidationResult(
                            level="error",
                            message=f"Embedding port {port} is out of valid range (1-65535)",
                            section="code_analysis",
                            key="embedding.port",
                            suggestion="Set port to a value between 1 and 65535",
                        )
                    )

        file_watcher = code_analysis.get("file_watcher", {})
        if file_watcher and isinstance(file_watcher, dict):
            scan_interval = file_watcher.get("scan_interval")
            if (
                scan_interval is not None
                and isinstance(scan_interval, (int, float))
                and scan_interval < 0
            ):
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.file_watcher.scan_interval must be >= 0",
                        section="code_analysis",
                        key="file_watcher.scan_interval",
                        suggestion="Set scan_interval to 0 or higher",
                    )
                )
            max_scan_duration = file_watcher.get("max_scan_duration")
            if (
                max_scan_duration is not None
                and isinstance(max_scan_duration, (int, float))
                and max_scan_duration < 0
            ):
                results.append(
                    ValidationResult(
                        level="error",
                        message="code_analysis.file_watcher.max_scan_duration must be >= 0",
                        section="code_analysis",
                        key="file_watcher.max_scan_duration",
                        suggestion="Set max_scan_duration to 0 or higher",
                    )
                )
