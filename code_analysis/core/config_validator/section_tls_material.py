"""
TLS material validation (cert/key pairing, CRL vs CA) for all cert sections.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from code_analysis.core.tls_material_validation import (
    iter_tls_material_blocks,
    validate_tls_material_block,
)

from .result import ValidationResult


def validate_tls_material_impl(
    config_data: Dict[str, Any],
    results: List[ValidationResult],
    config_path: Optional[str],
) -> None:
    """Validate cert/key pairing and CRL issuer for every TLS block in config."""
    config_dir = Path(config_path).parent if config_path else None

    for block in iter_tls_material_blocks(config_data):
        for level, message, key in validate_tls_material_block(block, config_dir):
            results.append(
                ValidationResult(
                    level=level,
                    message=message,
                    section=block.section,
                    key=key,
                    suggestion=(
                        "Provide matching cert and key paths, or ensure CRL is "
                        "signed by the configured CA or a system trust anchor"
                    ),
                )
            )
