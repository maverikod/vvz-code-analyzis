"""
MTLS and protocol consistency validation (external servers, protocol, UUID).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, List

from .helpers import is_valid_uuid4
from .result import ValidationResult


def validate_external_servers_mtls_impl(
    config_data: Dict[str, Any], results: List[ValidationResult]
) -> None:
    """Require protocol 'mtls' for all external/server connection sections."""
    server = config_data.get("server", {})
    if server:
        protocol = server.get("protocol")
        if protocol and protocol != "mtls":
            results.append(
                ValidationResult(
                    level="error",
                    message=f"server.protocol must be 'mtls', got '{protocol}'",
                    section="server",
                    key="protocol",
                    suggestion="Set server.protocol to 'mtls'",
                )
            )

    registration = config_data.get("registration", {})
    if registration and "protocol" in registration:
        protocol = registration.get("protocol")
        if protocol and protocol != "mtls":
            results.append(
                ValidationResult(
                    level="error",
                    message=f"registration.protocol must be 'mtls', got '{protocol}'",
                    section="registration",
                    key="protocol",
                    suggestion="Set registration.protocol to 'mtls'",
                )
            )

    client = config_data.get("client", {})
    if client and "protocol" in client:
        protocol = client.get("protocol")
        if protocol and protocol != "mtls":
            results.append(
                ValidationResult(
                    level="error",
                    message=f"client.protocol must be 'mtls', got '{protocol}'",
                    section="client",
                    key="protocol",
                    suggestion="Set client.protocol to 'mtls'",
                )
            )

    server_validation = config_data.get("server_validation", {})
    if server_validation and "protocol" in server_validation:
        protocol = server_validation.get("protocol")
        if protocol and protocol != "mtls":
            results.append(
                ValidationResult(
                    level="error",
                    message=f"server_validation.protocol must be 'mtls', got '{protocol}'",
                    section="server_validation",
                    key="protocol",
                    suggestion="Set server_validation.protocol to 'mtls'",
                )
            )

    code_analysis = config_data.get("code_analysis", {})
    chunker = code_analysis.get("chunker", {}) if code_analysis else {}
    if chunker and "protocol" in chunker:
        protocol = chunker.get("protocol")
        if protocol and protocol != "mtls":
            results.append(
                ValidationResult(
                    level="error",
                    message=f"code_analysis.chunker.protocol must be 'mtls', got '{protocol}'",
                    section="code_analysis",
                    key="chunker.protocol",
                    suggestion="Set code_analysis.chunker.protocol to 'mtls'",
                )
            )

    embedding = code_analysis.get("embedding", {}) if code_analysis else {}
    if embedding and "protocol" in embedding:
        protocol = embedding.get("protocol")
        if protocol and protocol != "mtls":
            results.append(
                ValidationResult(
                    level="error",
                    message=f"code_analysis.embedding.protocol must be 'mtls', got '{protocol}'",
                    section="code_analysis",
                    key="embedding.protocol",
                    suggestion="Set code_analysis.embedding.protocol to 'mtls'",
                )
            )


def validate_protocol_consistency_impl(
    config_data: Dict[str, Any], results: List[ValidationResult]
) -> None:
    """Validate protocol consistency across sections."""
    server_protocol = config_data.get("server", {}).get("protocol")
    registration = config_data.get("registration", {})
    if registration.get("enabled"):
        reg_protocol = registration.get("protocol")
        if reg_protocol and server_protocol and reg_protocol != server_protocol:
            results.append(
                ValidationResult(
                    level="warning",
                    message=f"Registration protocol '{reg_protocol}' differs from server protocol '{server_protocol}'",
                    section="registration",
                    key="protocol",
                    suggestion="Consider using the same protocol for consistency",
                )
            )


def validate_uuid_format_impl(
    config_data: Dict[str, Any], results: List[ValidationResult]
) -> None:
    """Validate UUID format in configuration."""
    registration = config_data.get("registration", {})
    if registration.get("enabled"):
        instance_uuid = registration.get("instance_uuid")
        if instance_uuid and not is_valid_uuid4(str(instance_uuid)):
            results.append(
                ValidationResult(
                    level="error",
                    message=f"Invalid UUID format in registration.instance_uuid: {instance_uuid}",
                    section="registration",
                    key="instance_uuid",
                    suggestion="Use a valid UUID4 format (e.g., 550e8400-e29b-41d4-a716-446655440000)",
                )
            )
