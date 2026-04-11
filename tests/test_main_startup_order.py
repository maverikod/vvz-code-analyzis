"""
Startup order: shared DB/schema before workers; ASGI event skips if main pre-initialized.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class _MockApp:
    """Minimal app capturing Starlette-style @app.on_event('startup') handlers."""

    def __init__(self) -> None:
        self._startup_handlers: list = []

    def on_event(self, name: str):
        def decorator(fn):
            if name == "startup":
                self._startup_handlers.append(fn)
            return fn

        return decorator


@pytest.mark.asyncio
async def test_startup_event_skips_when_shared_db_already_set() -> None:
    """If main() already set shared DB, ASGI startup must not re-run driver/open/workers."""
    from code_analysis.main_app_events import register_startup_shutdown_events

    app = _MockApp()
    wm = MagicMock()

    with (
        patch(
            "code_analysis.main_app_events.is_shared_database_current_process",
            return_value=True,
        ) as mock_ready,
        patch("code_analysis.main_app_events.startup_database_driver") as mock_driver,
        patch(
            "code_analysis.main_app_events.open_database_from_config_impl"
        ) as mock_open,
        patch("code_analysis.main_app_events.startup_indexing_worker") as mock_idx,
    ):
        register_startup_shutdown_events(app, {}, wm)
        assert len(app._startup_handlers) == 1
        await app._startup_handlers[0]()

    mock_ready.assert_called()
    mock_driver.assert_not_called()
    mock_open.assert_not_called()
    mock_idx.assert_not_called()


def test_run_workers_skips_driver_when_shared_db_ready() -> None:
    """run_workers_directly should not call startup_database_driver if shared DB is set."""
    from code_analysis import main_workers_run

    with (
        patch.object(
            main_workers_run,
            "is_shared_database_current_process",
            return_value=True,
        ),
        patch.object(main_workers_run, "startup_database_driver") as mock_drv,
        patch.object(main_workers_run, "startup_indexing_worker"),
        patch.object(main_workers_run, "startup_vectorization_worker"),
        patch.object(main_workers_run, "startup_file_watcher_worker"),
    ):
        wm = MagicMock()
        main_workers_run.run_workers_directly_and_start_monitoring(wm)

    mock_drv.assert_not_called()
    wm.start_monitoring.assert_called_once()
