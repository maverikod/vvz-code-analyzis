"""
Main entry point for code-analysis-server using mcp-proxy-adapter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from code_analysis.mcp_adapter_bootstrap import install_mcp_adapter_log_dir

install_mcp_adapter_log_dir()

from mcp_proxy_adapter.core.server_engine import ServerEngineFactory

from code_analysis.core.constants import DEFAULT_CONFIG_FILENAME
from code_analysis.core.settings_manager import get_settings
from code_analysis.main_app_factory import (
    create_app_with_events,
    setup_main_logger_file_handler,
)
from code_analysis.main_cleanup import log_daemon_shutdown, register_cleanup_handlers
from code_analysis.main_config import (
    apply_global_config,
    ensure_storage_and_load_app_config,
    load_config_and_validate,
)
from code_analysis.main_daemon_logging import setup_daemon_logging
from code_analysis.main_server_config import build_server_config
from code_analysis.main_startup_info import print_startup_info
from code_analysis.main_queue_init import init_queue_manager_before_workers
from code_analysis.main_workers_run import run_workers_directly_and_start_monitoring
from code_analysis.core.dependency_compat import assert_queue_dependencies_compatible

from code_analysis.core.server_log_dir import (
    append_server_startup_log,
    log_path_diagnostics,
    server_log_dir_from_config_data,
)

from code_analysis import hooks  # noqa: F401
from code_analysis.commands.base_mcp_command import (
    BaseMCPCommand,
    _get_socket_path_from_db_path,
)
from code_analysis.commands.base_mcp_command_open_db import (
    open_database_from_config_impl,
)
from code_analysis.core.shared_database import set_shared_database
from code_analysis.core.worker_manager import get_worker_manager


def _log_startup_diagnostics(
    *,
    config_path: Path,
    full_config: dict,
    app_config: dict,
    server_host: str,
    server_port: int,
    server_config: dict,
) -> None:
    """Write production troubleshooting lines to ``server_startup.log``."""
    log_dir = server_log_dir_from_config_data(app_config, config_path)
    append_server_startup_log(
        log_dir, f"startup: pid={os.getpid()} config={config_path}"
    )
    server = (
        app_config.get("server") if isinstance(app_config.get("server"), dict) else {}
    )
    advertised = server.get("advertised_host")
    append_server_startup_log(
        log_dir,
        f"startup: bind={server_host}:{server_port} advertised_host={advertised}",
    )
    ssl = server.get("ssl") if isinstance(server.get("ssl"), dict) else {}
    log_path_diagnostics(
        log_dir,
        "ssl",
        {
            "cert": str(ssl.get("cert") or ""),
            "key": str(ssl.get("key") or ""),
            "ca": str(ssl.get("ca") or ""),
        },
    )
    reg = (
        app_config.get("registration")
        if isinstance(app_config.get("registration"), dict)
        else {}
    )
    append_server_startup_log(
        log_dir,
        f"registration: enabled={reg.get('enabled')} server_id={reg.get('server_id')} "
        f"register_url={reg.get('register_url')}",
    )
    reg_ssl = reg.get("ssl") if isinstance(reg.get("ssl"), dict) else {}
    log_path_diagnostics(
        log_dir,
        "registration_ssl",
        {
            "cert": str(reg_ssl.get("cert") or ""),
            "key": str(reg_ssl.get("key") or ""),
            "ca": str(reg_ssl.get("ca") or ""),
        },
    )
    ssl_keys = ("ssl_certfile", "ssl_keyfile", "ssl_ca_certs")
    ssl_enabled = any(server_config.get(k) for k in ssl_keys)
    append_server_startup_log(
        log_dir,
        f"hypercorn: mTLS/SSL={'enabled' if ssl_enabled else 'disabled'}",
    )


def main() -> None:
    """Main function to run code-analysis-server."""
    parser = argparse.ArgumentParser(description="Code Analysis Server")
    parser.add_argument(
        "--config",
        type=str,
        default=DEFAULT_CONFIG_FILENAME,
        help=f"Path to configuration file (default: {DEFAULT_CONFIG_FILENAME})",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Start the server (daemon mode). Without this flag the command prints startup info and exits.",
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run server in foreground (no daemon). Use for debugging; faulthandler dumps to stderr on crash.",
    )
    parser.add_argument("--host", help="Server host (overrides config)")
    parser.add_argument("--port", type=int, help="Server port (overrides config)")
    args = parser.parse_args()

    settings = get_settings()
    cli_overrides = {}
    if args.host:
        cli_overrides["server_host"] = args.host
    if args.port:
        cli_overrides["server_port"] = args.port
    if cli_overrides:
        settings.set_cli_overrides(cli_overrides)

    import signal

    logging.raiseExceptions = False
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except Exception:
        pass

    config_path, full_config = load_config_and_validate(args)

    heartbeat_stop = setup_daemon_logging(args, full_config, config_path)

    app_config, simple_config, server_host, server_port = (
        ensure_storage_and_load_app_config(config_path, full_config, args)
    )
    queue_enabled = bool(
        (full_config.get("queue_manager") or {}).get("enabled", True)
        if isinstance(full_config, dict)
        else True
    )
    assert_queue_dependencies_compatible(queue_enabled=queue_enabled)
    apply_global_config(config_path, simple_config, app_config)

    worker_manager = get_worker_manager()

    # queuemgr subprocess must start before create_app workers and indexing/
    # vectorization children (Python 3.14 multiprocessing bootstrap safety).
    init_queue_manager_before_workers(full_config)

    app = create_app_with_events(app_config, config_path, worker_manager)
    main_logger = setup_main_logger_file_handler(app_config)

    server_config = build_server_config(
        server_host,
        server_port,
        app_config,
        config_path=config_path,
    )
    _log_startup_diagnostics(
        config_path=config_path,
        full_config=full_config,
        app_config=app_config,
        server_host=server_host,
        server_port=server_port,
        server_config=server_config,
    )

    if not args.daemon and not args.foreground:
        print_startup_info(
            config_path=config_path,
            server_host=server_host,
            server_port=server_port,
            server_config=server_config,
            app_config=app_config,
        )
        return

    if args.foreground:
        try:
            import faulthandler

            faulthandler.enable()
        except Exception:
            pass

    register_cleanup_handlers(
        worker_manager,
        app_config,
        main_logger,
        heartbeat_stop=heartbeat_stop,
    )

    run_workers_directly_and_start_monitoring(worker_manager)

    # Best-effort DB before Hypercorn; startup handlers retry if this fails (degraded).
    try:
        db = open_database_from_config_impl(
            BaseMCPCommand._resolve_config_path,
            _get_socket_path_from_db_path,
            auto_analyze=False,
        )
        set_shared_database(db)
        main_logger.info("Shared database connection set (main)")
    except Exception as e:
        main_logger.warning(
            "Shared database not available before server start (%s); "
            "process continues — DB open will be retried from startup handlers.",
            e,
            exc_info=True,
        )

    engine = ServerEngineFactory.get_engine("hypercorn")
    if not engine:
        append_server_startup_log(
            server_log_dir_from_config_data(app_config, config_path),
            "hypercorn: engine not available",
        )
        print("❌ Hypercorn engine not available", file=sys.stderr)
        sys.exit(1)

    append_server_startup_log(
        server_log_dir_from_config_data(app_config, config_path),
        f"hypercorn: starting on {server_host}:{server_port}",
    )

    main_logger.info(
        "Starting Hypercorn server on %s:%s (pid=%s)",
        server_host,
        server_port,
        os.getpid(),
    )
    try:
        engine.run_server(app, server_config)
        main_logger.info("Hypercorn run_server returned (server loop ended normally)")
    except Exception as e:
        append_server_startup_log(
            server_log_dir_from_config_data(app_config, config_path),
            f"hypercorn: run_server failed: {e}",
        )
        main_logger.error(
            "Hypercorn run_server raised: %s",
            e,
            exc_info=True,
        )
        raise
    finally:
        log_daemon_shutdown(main_logger, "main_server_loop_ended")
        main_logger.info("main() exiting after server loop")


if __name__ == "__main__":
    main()
