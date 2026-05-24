"""
Search session configuration section validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

from code_analysis.core.config_validator.result import ValidationResult
from code_analysis.core.search_session.policy import (
    load_session_ttl_policy,
    validate_session_ttl_policy,
)


def validate_search_session_section_impl(
    config_data: dict[str, Any],
    validation_results: list[ValidationResult],
) -> None:
    """Validate ``code_analysis.search_session`` TTL and block size settings."""
    code_analysis = config_data.get("code_analysis") or {}
    search_session = code_analysis.get("search_session")
    if search_session is None:
        validation_results.append(
            ValidationResult(
                level="info",
                message=(
                    "code_analysis.search_session is absent; code defaults apply "
                    "for ttl_seconds and max_block_size_bytes"
                ),
                section="code_analysis",
                key="search_session",
                suggestion="Add search_session section or rely on built-in defaults",
            )
        )
        return

    try:
        policy = load_session_ttl_policy(config_data)
        validate_session_ttl_policy(policy)
    except (TypeError, ValueError) as exc:
        validation_results.append(
            ValidationResult(
                level="error",
                message=str(exc),
                section="code_analysis",
                key="search_session",
                suggestion=(
                    "Set ttl_seconds and max_block_size_bytes to positive integers "
                    "within configured policy bounds"
                ),
            )
        )
