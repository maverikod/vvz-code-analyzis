"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP block processing system package.

This package provides modular components for the block-based 7D BVP processing system.
"""

from .bvp_block_processing_facade import BVPBlockProcessingSystem
from .bvp_block_processing_config import BVPBlockConfig

__all__ = ["BVPBlockProcessingSystem", "BVPBlockConfig"]
