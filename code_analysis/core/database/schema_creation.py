"""
Schema creation and migrations for CodeDatabase.
Facade: re-exports run_create_schema, run_migrate_to_uuid_projects, run_migrate_schema,
and UUID identity migration runners (preflight, phase 2, phases 3–5, phase 6 swap).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .schema_creation_create import run_create_schema
from .schema_creation_migrate import (
    run_migrate_schema,
    run_uuid_migration_phase2,
    run_uuid_migration_phase6_swap_postgres,
    run_uuid_migration_phase6_swap_sqlite,
    run_uuid_migration_phases_3_to_5_postgres,
    run_uuid_migration_phases_3_to_5_sqlite,
)
from .schema_creation_uuid import run_migrate_to_uuid_projects
from .migrations import (
    run_uuid_migration_phase2_build_mappings,
    run_uuid_migration_preflight_phase1,
)

__all__ = [
    "run_create_schema",
    "run_migrate_to_uuid_projects",
    "run_migrate_schema",
    "run_uuid_migration_phase2",
    "run_uuid_migration_phase2_build_mappings",
    "run_uuid_migration_preflight_phase1",
    "run_uuid_migration_phase6_swap_postgres",
    "run_uuid_migration_phase6_swap_sqlite",
    "run_uuid_migration_phases_3_to_5_postgres",
    "run_uuid_migration_phases_3_to_5_sqlite",
]
