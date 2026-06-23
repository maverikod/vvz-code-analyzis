"""
analyze_tree command package.

One read-only command that analyzes a sub-tree of a watched project (one or more
directory roots) and returns one of several analysis "lenses" selected by ``mode``.
The shared core — enumerate real files, gate each on the checksum staleness policy,
build the relation graph with module→path resolution — is computed once; each mode
is a post-processor over that core.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from .command import AnalyzeTreeMCPCommand

__all__ = ["AnalyzeTreeMCPCommand"]
