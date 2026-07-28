"""
End-to-end pipeline orchestration for the realsrv-test CLI.

One function, :func:`run_pipeline`, owns the whole run: client construction
(mTLS), health gate, fixture seeding, execution (full sweep or suite subset),
summary printing, and teardown.  The lifecycle runners are passed in by the
caller, collected from the auto-discovered suite modules in
``realsrv_test.suites`` — that discovery is the single source of execution
truth.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.sweep import (
    LifecycleRunner,
    print_summary,
    run_suite_subset,
    run_sweep,
)
from realsrv_test.core.fixtures import seed_fixtures
from realsrv_test.core.teardown import teardown_fixtures

# timeout=120.0 (client default is 60.0): read-only Bucket-A commands issued
# late in a run (project_pip_check / project_pip_list, right after the
# project_pip_install venv-bootstrap job) observed a bare httpx ReadTimeout('')
# under server load at the 60s default.  This timeout applies to every HTTP
# request the client makes, including queued-job status polling, so raising it
# is a plain headroom increase, not a behavior change for any command that was
# already completing in time.
_REQUEST_TIMEOUT_SECONDS = 120.0


async def run_pipeline(
    settings: Dict[str, Any],
    runners: Sequence[LifecycleRunner],
    *,
    full_sweep: bool,
    project_prefix: str = "verify_live",
    keep_project: bool = False,
) -> int:
    """Run the live acceptance pipeline and return the process exit code.

    Args:
        settings: Adapter settings dict (``host``/``port``/``protocol``/``ssl``).
        runners: Ordered lifecycle runners from the selected suites.
        full_sweep: True for the no-args full run (lifecycles + generic
            alphabetical sweep over every live command); False for a suite
            subset run (only the given runners execute).
        project_prefix: Prefix for the disposable project name.
        keep_project: If True, skip teardown for post-run debugging.

    Returns:
        0 if no outcome landed in ``Status.FAILED`` and teardown completed
        cleanly; 1 otherwise.  The initial mTLS health check and fixture setup
        are hard gates — both fail fast with a clear message.
    """
    async with CodeAnalysisAsyncClient.from_adapter_settings(
        settings, check_hostname=False, timeout=_REQUEST_TIMEOUT_SECONDS
    ) as client:
        try:
            await client.rpc.health()
        except Exception as exc:
            print(f"FAILED health-check: {exc!r}")
            return 1

        try:
            fixtures = await seed_fixtures(client, project_prefix)
        except Exception as exc:
            print(f"FAILED fixture setup: {exc!r}")
            return 1

        exit_code = 0
        try:
            if full_sweep:
                outcomes = await run_sweep(client, fixtures, runners)
            else:
                outcomes = await run_suite_subset(client, fixtures, runners)
            failed_count = print_summary(outcomes)
            if failed_count:
                exit_code = 1
        finally:
            teardown_ok = await teardown_fixtures(
                client, fixtures, keep_project=keep_project
            )
            if not teardown_ok:
                exit_code = 1

        return exit_code
