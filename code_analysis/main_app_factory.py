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

from code_analysis.main_app_events import register_startup_shutdown_events


def create_app_with_events(
    app_config: dict[str, Any],
    config_path: Path,
    worker_manager: Any,
) -> Any:
    """Create FastAPI app, register startup/shutdown events, set app.state.worker_manager."""
    app_factory = AppFactory()
    app = app_factory.create_app(
        title="Code Analysis Server",
        description=(
            "Code analysis tool for Python projects. Provides code mapping, issue detection, "
            "usage analysis, semantic search, and refactoring capabilities.\n\n"
            "### Correct command invocation\n"
            "**Via MCP Proxy (Cursor tool)**:\n"
            "- List servers: `mcp_MCP-Proxy-2_list_servers(filter_enabled=None)`\n"
            "- Call command (IMPORTANT: use `server_id` + `copy_number`, NOT `server_key`):\n"
            '  `mcp_MCP-Proxy-2_call_server(server_id="code-analysis-server", copy_number=1, '
            'command="get_database_status", params={"root_dir": "/abs/path"})`\n'
            "- Long-running commands (e.g. `update_indexes`) are queued (`use_queue=True`). "
            "Check them with `queue_get_job_status` / `queue_get_job_logs` using returned `job_id`.\n\n"
            "**Without MCP Proxy (direct)**:\n"
            "- Inspect API schema: `GET https://<host>:<port>/openapi.json` (mTLS)\n"
            "- Call commands using endpoints described in that OpenAPI schema.\n\n"
            "See also: `docs/MCP_PROXY_USAGE_GUIDE.md`"
        ),
        version="1.0.0",
        app_config=app_config,
        config_path=str(config_path),
    )

    register_startup_shutdown_events(app, app_config, worker_manager)
    app.state.worker_manager = worker_manager

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
