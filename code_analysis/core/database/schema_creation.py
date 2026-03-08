"""
Schema creation and migrations for CodeDatabase.
Facade: re-exports run_create_schema, run_migrate_to_uuid_projects, run_migrate_schema.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .schema_creation_create import run_create_schema
from .schema_creation_migrate import run_migrate_schema
from .schema_creation_uuid import run_migrate_to_uuid_projects

__all__ = [
    "run_create_schema",
    "run_migrate_to_uuid_projects",
    "run_migrate_schema",
]
