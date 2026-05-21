"""
Shared structure extraction for grep and preview (no DB, no vectorization).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.core.structure_extraction.extractor import (
    extract_structure,
    find_smallest_block_containing_line,
)
from code_analysis.core.structure_extraction.format_registry import (
    SUPPORTED_EXTENSIONS,
    is_supported_extension,
    should_scan_path,
)
from code_analysis.core.structure_extraction.match_mapper import (
    enrich_match_row,
    enrich_matches_for_file,
)
from code_analysis.core.structure_extraction.models import (
    StructureBlock,
    StructureDocument,
    StructureWarning,
)

__all__ = [
    "SUPPORTED_EXTENSIONS",
    "StructureBlock",
    "StructureDocument",
    "StructureWarning",
    "enrich_match_row",
    "enrich_matches_for_file",
    "extract_structure",
    "find_smallest_block_containing_line",
    "is_supported_extension",
    "should_scan_path",
]
