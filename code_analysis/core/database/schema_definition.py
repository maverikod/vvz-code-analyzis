"""
Structured schema definition for code_analysis database.

Exposes SCHEMA_VERSION, MIGRATION_METHODS, and get_schema_definition() for
sync_schema and schema comparison. Extracted from base.py to keep file size under limit.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Callable, Dict

from .schema_definition_indexes import get_schema_indexes, get_schema_virtual_tables
from .schema_definition_tables_core import get_tables_core
from .schema_definition_tables_mid import get_tables_mid
from .schema_definition_tables_rest import get_tables_rest

# Schema version constant
SCHEMA_VERSION = (
    "1.5.0"  # file_tree_snapshots, file_tree_snapshot_roots, file_tree_snapshot_nodes
)

# Migration methods registry: version -> migration function
# Each migration function receives driver instance and performs version-specific migrations
MIGRATION_METHODS: Dict[str, Callable[[Any], None]] = {
    # Register migration methods here
    # Format: "version": lambda driver: driver._migration_method_name()
    # Note: Methods are defined in SQLiteDriver, registry is here for centralization
}


def get_schema_definition() -> Dict[str, Any]:
    """
    Return structured schema definition for synchronization.

    Used by SchemaComparator and by RPC client when initializing an empty database.
    Returns a dict with version, tables, indexes, virtual_tables, migration_methods.
    """
    return {
        "version": SCHEMA_VERSION,
        "tables": {
            **get_tables_core(),
            **get_tables_mid(),
            **get_tables_rest(),
        },
        "indexes": get_schema_indexes(),
        "virtual_tables": get_schema_virtual_tables(),
        "migration_methods": MIGRATION_METHODS,
    }
