"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP block processing facade.

This module provides a unified interface for the modular BVP block processing system.
"""

from .bvp_block_processing_system.bvp_block_processing_facade import (
    BVPBlockProcessingSystem,
)
from .bvp_block_processing_system.bvp_block_processing_config import BVPBlockConfig

__all__ = ["BVPBlockProcessingSystem", "BVPBlockConfig"]
