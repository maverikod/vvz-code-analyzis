"""
Schema synchronization module.

Compares database schema with expected schema and generates migration SQL.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .schema_sync_comparator import SchemaComparator
from .schema_sync_models import ColumnDef, IndexDef, SchemaDiff, TableDiff

__all__ = [
    "SchemaComparator",
    "ColumnDef",
    "IndexDef",
    "TableDiff",
    "SchemaDiff",
]
