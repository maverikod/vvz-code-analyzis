"""
Worker/pip command lifecycle for the live-server all-commands verifier.

``project_pip_install`` runs as a queued background job. The client's
``call_validated`` now auto-polls any queued job to a terminal state itself:
on success it returns the completed venv-bootstrap result directly (no
top-level ``job_id``/``status`` envelope to poll by hand any more), and on
failure it raises :class:`code_analysis_client.JobFailedError` instead of
returning a ``status: failed`` envelope. This lifecycle no longer needs its
own bespoke wait loop — a raised ``JobFailedError`` is classified via
``_verify_client_all_commands_classifiers.classify_job_failed_error`` (a
structured inner error, e.g. a pip/venv rejection, becomes an expected-error
outcome; anything else stays FAILED).
``project_pip_check`` / ``_list`` / ``_search`` / ``_show`` / ``_uninstall``
and ``run_project_module`` all need the venv the install step bootstraps, so
they only run when ``project_pip_install`` completed successfully.
``project_pip_uninstall`` runs last since it removes the package the other
commands just inspected.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Dict

from code_analysis_client import CodeAnalysisAsyncClient, JobFailedError

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status, truncate
from _verify_client_all_commands_classifiers import classify_job_failed_error
from _verify_client_all_commands_fixtures import FixtureContext
from _verify_client_all_commands_lifecycle_common import call_step

_PACKAGES = ["pip"]


async def run_worker_lifecycle(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Run start/stop worker, pause/resume, run_project_module, and pip commands.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        Mapping of every command name this lifecycle covers to its outcome.
    """
    outcomes: Dict[str, CommandOutcome] = {}
    project_id = fixtures.project_id

    outcomes["start_worker"] = await call_step(
        client,
        "start_worker",
        {"worker_type": "file_watcher", "project_id": project_id},
        ok_reason="file_watcher worker started for the disposable project",
    )
    outcomes["stop_worker"] = await call_step(
        client,
        "stop_worker",
        {"worker_type": "file_watcher"},
        ok_reason="file_watcher worker stopped",
    )

    await call_step(
        client,
        "set_project_processing_paused",
        {"project_id": project_id, "processing_paused": True},
    )
    outcomes["set_project_processing_paused"] = await call_step(
        client,
        "set_project_processing_paused",
        {"project_id": project_id, "processing_paused": False},
        ok_reason="processing paused then resumed for the disposable project",
    )

    # project_pip_install is a queued command; call_validated now auto-polls it
    # to completion and raises JobFailedError on failure instead of returning
    # a status envelope to poll by hand.
    try:
        install_resp = await client.call_validated(
            "project_pip_install", {"project_id": project_id, "packages": _PACKAGES}
        )
    except JobFailedError as exc:
        install_outcome = await classify_job_failed_error(
            client, "project_pip_install", exc
        )
        venv_ready = False
    except Exception as exc:  # noqa: BLE001 - one bad step must not abort the sweep
        install_outcome = CommandOutcome(
            "project_pip_install", Bucket.BUCKET_A, Status.FAILED, truncate(repr(exc))
        )
        venv_ready = False
    else:
        if install_resp.get("success") is True:
            install_outcome = CommandOutcome(
                "project_pip_install",
                Bucket.BUCKET_A,
                Status.EXECUTED_OK,
                "venv bootstrap job completed for the disposable project",
            )
            venv_ready = True
        else:
            install_outcome = CommandOutcome(
                "project_pip_install",
                Bucket.BUCKET_A,
                Status.EXPECTED_ERROR,
                truncate(str(install_resp.get("error"))),
            )
            venv_ready = False
    outcomes["project_pip_install"] = install_outcome

    if venv_ready:
        outcomes["run_project_module"] = await call_step(
            client,
            "run_project_module",
            {"project_id": project_id, "module": fixtures.module_name},
            ok_reason=f"ran python -m {fixtures.module_name} against the seeded fixture file",
        )
        outcomes["project_pip_check"] = await call_step(
            client,
            "project_pip_check",
            {"project_id": project_id, "packages": _PACKAGES},
        )
        outcomes["project_pip_list"] = await call_step(
            client, "project_pip_list", {"project_id": project_id}
        )
        outcomes["project_pip_search"] = await call_step(
            client, "project_pip_search", {"project_id": project_id, "query": "pip"}
        )
        outcomes["project_pip_show"] = await call_step(
            client,
            "project_pip_show",
            {"project_id": project_id, "packages": _PACKAGES},
        )
        outcomes["project_pip_uninstall"] = await call_step(
            client,
            "project_pip_uninstall",
            {"project_id": project_id, "packages": _PACKAGES},
            ok_reason="package uninstalled at lifecycle teardown",
        )
    else:
        # venv_ready is only True when install_outcome.status is EXECUTED_OK, so
        # by construction install_outcome.status is never EXECUTED_OK here.
        skip_status = install_outcome.status
        reason = (
            "skipped: project_pip_install did not complete successfully "
            "(no venv confirmed ready)"
        )
        for name in (
            "run_project_module",
            "project_pip_check",
            "project_pip_list",
            "project_pip_search",
            "project_pip_show",
            "project_pip_uninstall",
        ):
            outcomes[name] = CommandOutcome(name, Bucket.BUCKET_A, skip_status, reason)
    return outcomes
