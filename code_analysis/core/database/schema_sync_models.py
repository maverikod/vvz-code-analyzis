"""
Schema diff models for schema_sync.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class ColumnDef:
    """Column definition."""

    name: str
    type: str
    not_null: bool = False
    default: Optional[str] = None
    primary_key: bool = False
    autoincrement: bool = False


@dataclass
class IndexDef:
    """Index definition."""

    name: str
    table: str
    columns: List[str]
    unique: bool = False
    where_clause: Optional[str] = None


@dataclass
class TableDiff:
    """Table structure differences."""

    missing_columns: List[ColumnDef]
    extra_columns: List[str]  # column names
    type_changes: List[Tuple[str, str, str]]  # (col_name, old_type, new_type)
    constraint_changes: List[str]

    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(
            self.missing_columns
            or self.extra_columns
            or self.type_changes
            or self.constraint_changes
        )


@dataclass
class SchemaDiff:
    """Schema differences."""

    missing_tables: Set[str]
    extra_tables: Set[str]
    table_diffs: Dict[str, TableDiff]  # table_name -> TableDiff
    missing_indexes: List[IndexDef]
    extra_indexes: List[str]  # index names
    constraint_diffs: Dict[str, List[str]]  # table_name -> constraint changes
    missing_virtual_tables: Dict[
        str, Dict[str, Any]
    ]  # virtual table name -> definition
    changed_virtual_tables: Dict[
        str, Dict[str, Any]
    ]  # virtual table name -> new definition

    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(
            self.missing_tables
            or self.extra_tables
            or self.table_diffs
            or self.missing_indexes
            or self.extra_indexes
            or self.constraint_diffs
            or self.missing_virtual_tables
            or self.changed_virtual_tables
        )
