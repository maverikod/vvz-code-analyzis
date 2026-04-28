"""
UUID identity migration (Block E): mapping tables, preflight, Phase 2 build;
PostgreSQL Phases 3–6 in :mod:`uuid_identity_postgres_data_migrate`;
SQLite Phases 3–6 in :mod:`uuid_identity_sqlite_data_migrate`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .uuid_identity_migration_common import (
    UuidMigrationError,
    UuidMigrationPreflightError,
    map_polymorphic_entity_id_to_new_uuid,
)
from .uuid_identity_migration import (
    run_uuid_migration_phase2_build_mappings,
    run_uuid_migration_preflight_phase1,
)
from .uuid_identity_postgres_data_migrate import (
    Phase345Report,
    run_uuid_migration_phase6_swap_postgres,
    run_uuid_migration_phases_3_to_5_postgres,
)
from .uuid_identity_sqlite_data_migrate import (
    run_uuid_migration_phase6_swap_sqlite,
    run_uuid_migration_phases_3_to_5_sqlite,
)

# Canonical short name — same callable as *_build_mappings.
run_uuid_migration_phase2 = run_uuid_migration_phase2_build_mappings

__all__ = [
    "Phase345Report",
    "UuidMigrationError",
    "UuidMigrationPreflightError",
    "map_polymorphic_entity_id_to_new_uuid",
    "run_uuid_migration_preflight_phase1",
    "run_uuid_migration_phase2_build_mappings",
    "run_uuid_migration_phase2",
    "run_uuid_migration_phase6_swap_postgres",
    "run_uuid_migration_phase6_swap_sqlite",
    "run_uuid_migration_phases_3_to_5_postgres",
    "run_uuid_migration_phases_3_to_5_sqlite",
]
