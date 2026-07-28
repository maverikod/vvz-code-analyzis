"""
Core implementation of the realsrv-test live acceptance pipeline.

Modules:
    catalog                 — static classification data + generic param providers
    classifiers             — per-bucket classification/execution logic
    fixtures                — disposable-project fixture seeding
    fixtures_registration   — DB-registration wait / file-id resolution / branch seed
    lifecycle_common        — shared call/skip helpers for lifecycles
    lifecycle_*             — one ordered command lifecycle per module
    sweep                   — sweep engine (run_lifecycles / run_sweep / summary)
    teardown                — disposable-project teardown
    pipeline                — end-to-end orchestration used by the CLI
    watcher_config_load_check — standalone CLI regression check (not a suite)

The set of lifecycle runners that actually executes is owned by the
auto-discovered suite modules in ``realsrv_test.suites`` — never hardcoded
here.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations
