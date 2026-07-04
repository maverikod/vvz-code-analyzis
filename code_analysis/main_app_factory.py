"""
Create FastAPI app and register worker startup/shutdown events.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mcp_proxy_adapter.api.core.app_factory import AppFactory

from code_analysis.core.search_session.cleaner import register_search_session_cleanup
from code_analysis.core.search_session.http_routes import register_search_job_routes
from code_analysis.main_app_events import register_startup_shutdown_events
from code_analysis.main_server_presentation import resolve_server_presentation
from code_analysis.openapi_mcp_proxy_compat import (
    patch_app_openapi_for_mcp_proxy,
    prime_openapi_cache,
)


def create_app_with_events(
    app_config: dict[str, Any],
    config_path: Path,
    worker_manager: Any,
) -> Any:
    """Create FastAPI app, register startup/shutdown events, set app.state.worker_manager."""
    title, description, version = resolve_server_presentation(app_config)
    app_factory = AppFactory()
    app = app_factory.create_app(
        title=title,
        description=description,
        version=version,
        app_config=app_config,
        config_path=str(config_path),
    )

    register_startup_shutdown_events(app, app_config, worker_manager)
    app.state.worker_manager = worker_manager
    patch_app_openapi_for_mcp_proxy(app)
    from code_analysis.core.storage_paths import (
        load_raw_config,
        resolve_search_sessions_root,
    )

    config_data = load_raw_config(config_path)
    sessions_root = resolve_search_sessions_root(
        config_data=config_data,
        config_path=config_path,
    )
    register_search_job_routes(app, sessions_root=sessions_root)
    register_search_session_cleanup(
        app,
        sessions_root=sessions_root,
        config_path=config_path,
        app_config=app_config,
    )
    prime_openapi_cache(app)

    return app


def setup_main_logger_file_handler(app_config: dict[str, Any]) -> logging.Logger:
    """Configure main logger with file handler if not already configured. Returns logger."""
    main_logger = logging.getLogger(__name__)
    if not main_logger.handlers:
        from pathlib import Path

        from code_analysis.logging import (
            create_unified_formatter,
            install_unified_record_factory,
        )

        install_unified_record_factory()
        log_dir = Path(app_config.get("server", {}).get("log_dir", "./logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "mcp_server.log"

        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setLevel(logging.INFO)
        handler.setFormatter(create_unified_formatter())
        main_logger.addHandler(handler)
        main_logger.setLevel(logging.INFO)
    return main_logger
