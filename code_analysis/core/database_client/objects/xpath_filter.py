"""
XPath-like filter for AST/CST tree queries.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from dataclasses import dataclass
from typing import Optional

from code_analysis.cst_query import QueryParseError, parse_selector


@dataclass
class XPathFilter:
    """XPath-like filter for AST/CST tree queries.

    Uses CSTQuery engine for selector syntax. Supports additional filters
    for node type, name, qualname, and line range.

    Attributes:
        selector: CSTQuery selector string (e.g., "function[name='my_func']")
        node_type: Optional node type filter
        name: Optional node name filter
        qualname: Optional qualified name filter
        start_line: Optional start line filter
        end_line: Optional end line filter

    Examples:
        >>> filter = XPathFilter(selector="function[name='my_func']")
        >>> filter = XPathFilter(selector="class[name='MyClass']", node_type="class")
        >>> filter = XPathFilter(
        ...     selector="method[qualname='MyClass.my_method']",
        ...     start_line=10,
        ...     end_line=20
        ... )
    """

    selector: str
    node_type: Optional[str] = None
    name: Optional[str] = None
    qualname: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate selector after initialization."""
        if not self.selector:
            raise ValueError("selector cannot be empty")

        # Validate selector syntax by parsing it
        try:
            parse_selector(self.selector)
        except QueryParseError as e:
            raise ValueError(f"Invalid selector syntax: {e}") from e

    def to_dict(self) -> dict:
        """Convert filter to dictionary for serialization.

        Returns:
            Dictionary representation of filter
        """
        result = {"selector": self.selector}

        if self.node_type is not None:
            result["node_type"] = self.node_type
        if self.name is not None:
            result["name"] = self.name
        if self.qualname is not None:
            result["qualname"] = self.qualname
        if self.start_line is not None:
            result["start_line"] = self.start_line
        if self.end_line is not None:
            result["end_line"] = self.end_line

        return result

    @classmethod
    def from_dict(cls, data: dict) -> "XPathFilter":
        """Create filter from dictionary.

        Args:
            data: Dictionary with filter data

        Returns:
            XPathFilter instance
        """
        return cls(
            selector=data["selector"],
            node_type=data.get("node_type"),
            name=data.get("name"),
            qualname=data.get("qualname"),
            start_line=data.get("start_line"),
            end_line=data.get("end_line"),
        )

    def __str__(self) -> str:
        """String representation of filter."""
        parts = [f"selector='{self.selector}'"]
        if self.node_type:
            parts.append(f"node_type='{self.node_type}'")
        if self.name:
            parts.append(f"name='{self.name}'")
        if self.qualname:
            parts.append(f"qualname='{self.qualname}'")
        if self.start_line is not None:
            parts.append(f"start_line={self.start_line}")
        if self.end_line is not None:
            parts.append(f"end_line={self.end_line}")
        return f"XPathFilter({', '.join(parts)})"
