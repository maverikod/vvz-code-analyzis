"""
Code Analysis Tool

A comprehensive Python code analysis tool that generates code maps,
detects issues, and provides detailed reports.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

__version__ = "1.0.0"
__author__ = "Vasiliy Zdanovskiy"
__email__ = "vasilyvz@gmail.com"

from .analyzer import CodeAnalyzer
from .code_mapper import CodeMapper
from .issue_detector import IssueDetector
from .reporter import CodeReporter

__all__ = [
    "CodeAnalyzer",
    "CodeMapper",
    "IssueDetector",
    "CodeReporter",
]
