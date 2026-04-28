"""
Public façade for Phase 1 preflight + Phase 2 mapping build (step 09).

Destructive swaps and Phases 3–6 remain in later milestones.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from .uuid_identity_migration_common import (
    Phase2Report,
    PreflightReport,
    detect_backend_kind,
    make_mapping_lookup_closure,
    map_polymorphic_entity_id_to_new_uuid,
    run_uuid_migration_phase2_build_mappings,
    run_uuid_migration_preflight_phase1,
)

run_uuid_migration_phase2 = run_uuid_migration_phase2_build_mappings

__all__ = [
    "Phase2Report",
    "PreflightReport",
    "detect_backend_kind",
    "make_mapping_lookup_closure",
    "map_polymorphic_entity_id_to_new_uuid",
    "run_uuid_migration_phase2",
    "run_uuid_migration_phase2_build_mappings",
    "run_uuid_migration_preflight_phase1",
]
