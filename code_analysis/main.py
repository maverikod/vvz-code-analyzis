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
from code_analysis.main_cleanup import (
    _flush_log_handlers,
    log_daemon_shutdown,
    register_cleanup_handlers,
)
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
    _log_quality_tools_selfcheck(log_dir)


def _log_quality_tools_selfcheck(log_dir: Path) -> None:
    """Boot self-check (A-IMG.5): probe the five quality tools via the server
    interpreter, record versions in the startup log, and log loudly on any miss.
    """
    boot_logger = logging.getLogger(__name__)
    try:
        from code_analysis.core.code_quality import quality_tool_report

        report = quality_tool_report()
        present = {t: v["version"] for t, v in report.items() if v["available"]}
        missing = sorted(t for t, v in report.items() if not v["available"])
        append_server_startup_log(
            log_dir,
            f"quality_tools: present={present} missing={missing or 'none'}",
        )
        if missing:
            boot_logger.error(
                "[QUALITY_TOOLS] MISSING from server interpreter: %s — "
                "comprehensive_analysis checks for these will hard-fail when requested",
                missing,
            )
        else:
            boot_logger.info("[QUALITY_TOOLS] all present: %s", present)
    except Exception as exc:  # self-check must never block startup
        append_server_startup_log(log_dir, f"quality_tools: self-check failed: {exc}")


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
        # Ignore SIGPIPE (the CPython default). This is a long-running daemon:
        # a write to a client/transport socket that the peer has closed must
        # raise a catchable BrokenPipeError on that connection, NOT kill the
        # whole server. SIG_DFL (terminate) is only correct for CLI tools in a
        # shell pipe — it previously let a slow command + client disconnect take
        # the server down via signal=PIPE (TZ-CA-VECTORIZATION-WORKER-OVERFLOW
        # log analysis).
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    except Exception:
        pass

    config_path, full_config = load_config_and_validate(args)

    heartbeat_stop = setup_daemon_logging(args, full_config, config_path)

    # Independent proxy-heartbeat watchdog: detects main-loop stalls (dumps
    # tracebacks) and posts a best-effort heartbeat while the loop is alive, so a
    # stray blocking call can no longer silently cause proxy deregistration.
    # Stopped via the shared heartbeat_stop Event on shutdown.
    try:
        from code_analysis.core.proxy_heartbeat_watchdog import (
            start_proxy_heartbeat_watchdog,
        )

        start_proxy_heartbeat_watchdog(full_config, config_path, heartbeat_stop)
    except Exception as _wd_exc:  # pragma: no cover - watchdog must never block boot
        logging.getLogger(__name__).warning(
            "Failed to start proxy heartbeat watchdog: %s", _wd_exc
        )

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

    cleanup_workers = register_cleanup_handlers(
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
    exit_code = 0
    try:
        engine.run_server(app, server_config)
        main_logger.info("Hypercorn run_server returned (server loop ended normally)")
    except SystemExit as e:
        # Our signal handler raises SystemExit(0) on a graceful stop.
        code = e.code
        exit_code = code if isinstance(code, int) else (0 if code is None else 1)
    except BaseException as e:  # noqa: BLE001 - daemon must always force a clean exit
        exit_code = 1
        append_server_startup_log(
            server_log_dir_from_config_data(app_config, config_path),
            f"hypercorn: run_server failed: {e}",
        )
        main_logger.error(
            "Hypercorn run_server raised: %s",
            e,
            exc_info=True,
        )
    finally:
        log_daemon_shutdown(main_logger, "main_server_loop_ended")
        main_logger.info("main() exiting after server loop")
        # The server loop has ended; finalize and hard-exit promptly.
        #
        # After Hypercorn returns, lingering non-daemon threads or
        # multiprocessing joins can block normal interpreter shutdown
        # (threading._shutdown()), so atexit handlers never run and the daemon
        # heartbeat keeps ticking. systemd then waits out TimeoutStopSec and
        # SIGKILLs the process, marking the unit failed (Result: timeout).
        #
        # Stop the heartbeat, run the idempotent worker cleanup, flush logs,
        # then os._exit() so stop/restart is fast and the unit ends cleanly.
        # exit_code is non-zero on an abnormal loop exit so Restart=on-failure
        # still applies.
        try:
            if heartbeat_stop is not None:
                heartbeat_stop.set()
        except Exception:
            pass
        try:
            cleanup_workers()
        except Exception:
            main_logger.error(
                "cleanup_workers() during shutdown failed", exc_info=True
            )
        _flush_log_handlers()
        os._exit(exit_code)


if __name__ == "__main__":
    main()
