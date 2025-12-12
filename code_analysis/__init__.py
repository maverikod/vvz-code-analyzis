"""
Code Analysis Tool

A comprehensive Python code analysis tool that generates code maps,
detects issues, and provides detailed reports.

Can be used as a library or via CLI commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

__version__ = "1.0.0"
__author__ = "Vasiliy Zdanovskiy"
__email__ = "vasilyvz@gmail.com"

# Core functionality
from .core import (
    CodeAnalyzer,
    CodeDatabase,
    IssueDetector,
    UsageAnalyzer,
    ClassSplitter,
    SuperclassExtractor,
    ClassMerger,
    CodeReporter,
)

# High-level API
from .api import CodeAnalysisAPI

# Code mapper (legacy, for backward compatibility)
from .code_mapper import CodeMapper

__all__ = [
    # Core
    "CodeAnalyzer",
    "CodeDatabase",
    "IssueDetector",
    "UsageAnalyzer",
    "ClassSplitter",
    "SuperclassExtractor",
    "ClassMerger",
    "CodeReporter",
    # API
    "CodeAnalysisAPI",
    # Legacy
    "CodeMapper",
]
