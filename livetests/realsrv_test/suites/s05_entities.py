"""
Suite: entities — AST entity-lookup command lifecycle.

Exercises: get_code_entity_info, get_entity_dependencies, get_entity_dependents,
find_dependencies, find_usages, list_class_methods, get_function_info,
get_class_info, and related entity-graph commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import realsrv_test._bootstrap  # noqa: F401 — must run before any scripts/ import

from _verify_client_all_commands_lifecycle_entities import run_entity_lifecycle

SUITE_NAME = "entities"
LIFECYCLE_RUNNERS = (run_entity_lifecycle,)
