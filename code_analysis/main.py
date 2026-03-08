"""
Main entry point for code-analysis-server using mcp-proxy-adapter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
import os
import sys
import types
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from mcp_proxy_adapter.api.core.app_factory import AppFactory  # noqa: E402
from mcp_proxy_adapter.core.config.simple_config import SimpleConfig  # noqa: E402
from mcp_proxy_adapter.core.server_engine import ServerEngineFactory  # noqa: E402

from code_analysis.core.storage_paths import (
    ensure_storage_dirs,
    load_raw_config,
    resolve_storage_paths,
)
from code_analysis.core.constants import (
    DEFAULT_SHUTDOWN_GRACE_TIMEOUT,
    DEFAULT_DATABASE_DRIVER_LOG_FILENAME,
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_WORKER_MONITOR_INTERVAL,
)
from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.main_workers import (
    startup_database_driver,
    startup_file_watcher_worker,
    startup_indexing_worker,
    startup_vectorization_worker,
)

from code_analysis import hooks  # noqa: F401,E402


def _print_startup_info(
    *,
    config_path: Path,
    server_host: str,
    server_port: int,
    server_config: dict[str, Any],
    app_config: dict[str, Any],
) -> None:
    """Print server startup info without actually starting the server process.

    Returns:
        None
    """
    print("ℹ️  code-analysis-server startup info (no --daemon):", flush=True)
    print(f"   Config: {config_path}", flush=True)
    print(f"   Host: {server_host}", flush=True)
    print(f"   Port: {server_port}", flush=True)
    ssl_keys = {"ssl_certfile", "ssl_keyfile", "ssl_ca_certs"}
    ssl_enabled = any(k in server_config and server_config.get(k) for k in ssl_keys)
    print(f"   mTLS/SSL: {'enabled' if ssl_enabled else 'disabled'}", flush=True)
    queue_cfg = app_config.get("queue") or {}
    if isinstance(queue_cfg, dict):
        print(
            f"   Queue: {'enabled' if queue_cfg.get('enabled', False) else 'disabled'}",
            flush=True,
        )
    print("   Engine: hypercorn (default)", flush=True)
    print(
        "   Start: python -m code_analysis.main --daemon --config <path>",
        flush=True,
    )


def main() -> None:
    """Main function to run code-analysis-server.

    Returns:
        None
    """
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
    parser.add_argument(
        "--host",
        help="Server host (overrides config)",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Server port (overrides config)",
    )
    args = parser.parse_args()

    # Initialize SettingsManager and set CLI overrides
    from code_analysis.core.settings_manager import get_settings

    settings = get_settings()
    cli_overrides = {}
    if args.host:
        cli_overrides["server_host"] = args.host
    if args.port:
        cli_overrides["server_port"] = args.port
    if cli_overrides:
        settings.set_cli_overrides(cli_overrides)

    import logging
    import signal

    logging.raiseExceptions = False
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except Exception:
        pass

    # Load configuration
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"❌ Configuration file not found: {config_path}", file=sys.stderr)
        print(
            "   Generate one with: python -m code_analysis.cli.config_cli generate",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load full config first (before SimpleConfig to validate early)
    import json

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            full_config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in configuration file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to read configuration file: {e}", file=sys.stderr)
        sys.exit(1)

    # Validate configuration BEFORE using it
    from code_analysis.core.config_validator import CodeAnalysisConfigValidator

    validator = CodeAnalysisConfigValidator(str(config_path))
    try:
        validator.load_config()
        validation_results = validator.validate_config()
        summary = validator.get_validation_summary()

        if not summary["is_valid"]:
            # Try to use log from config if available, otherwise use console
            errors = [r for r in validation_results if r.level == "error"]
            warnings = [r for r in validation_results if r.level == "warning"]

            # Try to get log directory from config
            log_dir = None
            log_file = None
            logger = None

            try:
                server_config = full_config.get("server", {})
                log_dir_str = server_config.get("log_dir", "./logs")
                log_dir = Path(log_dir_str)
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file = log_dir / "mcp_server.log"

                # Try to configure logging
                logging.basicConfig(
                    level=logging.ERROR,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[
                        logging.FileHandler(log_file, encoding="utf-8"),
                        logging.StreamHandler(sys.stderr),
                    ],
                    force=True,  # Override existing configuration
                )
                logger = logging.getLogger(__name__)
            except Exception:
                # If logging setup fails, we'll use console only
                log_dir = None
                log_file = None
                logger = None

            # Log errors
            error_header = "❌ Configuration validation failed:"
            if logger:
                logger.error(error_header)
            else:
                print(error_header, file=sys.stderr)

            for error in errors:
                section_info = (
                    f" ({error.section}" + (f".{error.key}" if error.key else "") + ")"
                    if error.section
                    else ""
                )
                error_msg = f"   - {error.message}{section_info}"
                if error.suggestion:
                    error_msg += f" - {error.suggestion}"

                if logger:
                    logger.error(error_msg)
                else:
                    print(error_msg, file=sys.stderr)

            if warnings:
                warning_header = "⚠️  Warnings:"
                if logger:
                    logger.warning(warning_header)
                else:
                    print(warning_header, file=sys.stderr)

                for warning in warnings:
                    section_info = (
                        f" ({warning.section}"
                        + (f".{warning.key}" if warning.key else "")
                        + ")"
                        if warning.section
                        else ""
                    )
                    warning_msg = f"   - {warning.message}{section_info}"
                    if warning.suggestion:
                        warning_msg += f" - {warning.suggestion}"

                    if logger:
                        logger.warning(warning_msg)
                    else:
                        print(warning_msg, file=sys.stderr)

            # Print summary
            if logger and log_file:
                print(
                    f"\n❌ Configuration validation failed. See log file: {log_file}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"\n❌ Configuration validation failed: "
                    f"{summary['errors']} error(s), {summary['warnings']} warning(s)",
                    file=sys.stderr,
                )

            # Exit with error code
            sys.exit(1)

    except Exception as e:
        # If validation itself fails, log to console
        print(f"❌ Failed to validate configuration: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # Optional: stop event for daemon heartbeat thread (set in finally on shutdown)
    heartbeat_stop = None

    # In daemon mode, set up file logging as early as possible so that
    # crash causes and tracebacks are visible in logs (stderr is redirected
    # to the same file by server_manager_cli when spawning).
    if args.daemon:
        try:
            log_dir = Path(full_config.get("server", {}).get("log_dir", "./logs"))
            if not log_dir.is_absolute():
                log_dir = (config_path.resolve().parent / log_dir).resolve()
            log_dir.mkdir(parents=True, exist_ok=True)
            daemon_log_file = log_dir / "mcp_server.log"
            root_logger = logging.getLogger()
            if not any(
                isinstance(h, logging.FileHandler)
                and getattr(h, "baseFilename", "") == str(daemon_log_file)
                for h in root_logger.handlers
            ):
                from code_analysis.logging import (
                    create_unified_formatter,
                    install_unified_record_factory,
                )

                install_unified_record_factory()
                file_handler = logging.FileHandler(daemon_log_file, encoding="utf-8")
                file_handler.setLevel(logging.INFO)
                file_handler.setFormatter(create_unified_formatter())
                root_logger.addHandler(file_handler)
                root_logger.setLevel(logging.INFO)

            # Log uncaught thread exceptions to file (Python 3.8+)
            import threading

            def _daemon_thread_excepthook(args: object) -> None:
                # args: exc_type, exc_value, exc_traceback, thread (named tuple)
                root_logger.error(
                    "Uncaught exception in thread %s: %s",
                    getattr(getattr(args, "thread", None), "name", None)
                    or getattr(getattr(args, "thread", None), "ident", None),
                    getattr(args, "exc_value", None),
                    exc_info=(
                        getattr(args, "exc_type", None),
                        getattr(args, "exc_value", None),
                        getattr(args, "exc_traceback", None),
                    ),
                )

            threading.excepthook = _daemon_thread_excepthook

            # On SIGSEGV/SIGABRT dump traceback to stderr (which is redirected to log by CLI)
            try:
                import faulthandler

                faulthandler.enable()
            except Exception:
                pass

            # Log uncaught main-thread exceptions to file so crash cause is visible
            _original_excepthook = sys.excepthook

            def _daemon_excepthook(
                exc_type: type[BaseException],
                exc_value: BaseException,
                exc_tb: types.TracebackType | None,
            ) -> None:
                root_logger.error(
                    "Uncaught exception in main thread (process will exit): %s",
                    exc_value,
                    exc_info=(exc_type, exc_value, exc_tb),
                )
                _original_excepthook(exc_type, exc_value, exc_tb)

            sys.excepthook = _daemon_excepthook

            # Periodic heartbeat so log shows last moment main process was alive
            heartbeat_stop = threading.Event()

            def _heartbeat_worker() -> None:
                log = logging.getLogger(__name__)
                while not heartbeat_stop.wait(timeout=60.0):
                    log.info("Main process heartbeat (pid=%s)", os.getpid())

            _hb_thread = threading.Thread(target=_heartbeat_worker, daemon=True)
            _hb_thread.start()

            root_logger.info(
                "Daemon main() entered, pid=%s (logging to %s)",
                os.getpid(),
                daemon_log_file,
            )
        except Exception:
            pass

    # Ensure state directories exist early (DB/FAISS/locks/queue).
    try:
        storage_paths = resolve_storage_paths(
            config_data=full_config,
            config_path=config_path.resolve(),
        )
        ensure_storage_dirs(storage_paths)
    except Exception as e:
        print(f"❌ Failed to prepare storage directories: {e}", file=sys.stderr)
        sys.exit(1)

    # Now load with SimpleConfig for application use
    try:
        simple_config = SimpleConfig(str(config_path))
        model = simple_config.load()
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}", file=sys.stderr)
        sys.exit(1)

    # Override host/port from CLI if provided (also set in SettingsManager above)
    if args.host:
        simple_config.model.server.host = args.host
    if args.port:
        simple_config.model.server.port = args.port

    # Use SettingsManager for host/port (CLI > ENV > Constants)
    server_host = settings.get("server_host") or args.host or model.server.host
    server_port = settings.get("server_port") or args.port or model.server.port

    # Merge SimpleConfig sections back into raw config (preserve custom sections)
    app_config = simple_config.to_dict()

    # Merge custom sections into app_config
    for key, value in full_config.items():
        if key not in app_config:
            app_config[key] = value

    # Configuration validation is now done earlier, before using configuration

    # Update global configuration instance used by adapter internals
    from mcp_proxy_adapter.config import get_config

    cfg = get_config()
    cfg.config_path = str(config_path)
    setattr(cfg, "model", model)
    cfg.config_data = app_config
    if hasattr(cfg, "feature_manager"):
        cfg.feature_manager.config_data = cfg.config_data

    # Initialize worker manager
    from code_analysis.core.worker_manager import get_worker_manager

    worker_manager = get_worker_manager()

    # Create lifespan context manager for automatic worker startup
    @asynccontextmanager
    async def lifespan(app_instance: Any) -> AsyncIterator[None]:
        """
        Lifespan context manager for automatic worker startup and shutdown.

        Args:
            app_instance: FastAPI application instance.

        Returns:
            None
        """
        import asyncio
        import logging

        logger = logging.getLogger(__name__)
        logger.info("🚀 Server startup: initializing workers...")

        # Startup sequence: database driver → other workers
        # Database driver must start FIRST because other workers depend on it
        # Functions are synchronous but run in executor to avoid blocking

        # Start database driver first
        await asyncio.to_thread(startup_database_driver)

        # Indexing worker before vectorization (indexer clears needs_chunking first)
        await asyncio.to_thread(startup_indexing_worker)
        await asyncio.to_thread(startup_vectorization_worker)
        await asyncio.to_thread(startup_file_watcher_worker)

        logger.info("✅ All workers started successfully")

        yield  # Server is running

        # Shutdown: cleanup workers
        logger.info("🛑 Server shutdown: stopping all workers...")
        try:
            shutdown_cfg = (
                app_config.get("process_management")
                or app_config.get("server_manager")
                or {}
            )
            shutdown_timeout = DEFAULT_SHUTDOWN_GRACE_TIMEOUT
            if isinstance(shutdown_cfg, dict):
                try:
                    val = shutdown_cfg.get("shutdown_grace_seconds")
                    if isinstance(val, (int, float)) and float(val) > 0:
                        shutdown_timeout = float(val)
                except Exception:
                    shutdown_timeout = DEFAULT_SHUTDOWN_GRACE_TIMEOUT

            shutdown_result = worker_manager.stop_all_workers(timeout=shutdown_timeout)
            if shutdown_result.get("total_failed", 0) > 0:
                logger.warning(
                    f"⚠️  Some workers failed to stop: {shutdown_result.get('message')}"
                )
            else:
                logger.info(f"✅ All workers stopped: {shutdown_result.get('message')}")
        except Exception as e:
            logger.error(f"❌ Error stopping workers: {e}", exc_info=True)

    # Create FastAPI app using AppFactory
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

    # Add startup/shutdown events to start/stop workers
    # Note: FastAPI lifespan must be passed at app creation, but AppFactory doesn't support it
    # So we use startup/shutdown events (deprecated but still works) as fallback
    @app.on_event("startup")  # type: ignore[misc]
    async def start_workers_on_startup() -> None:
        """Start workers on server startup using startup event.

        Returns:
            None
        """
        import logging

        logger = logging.getLogger(__name__)
        print(
            "🚀 [STARTUP EVENT] Server startup: initializing workers via startup event...",
            flush=True,
        )
        logger.info(
            "🚀 [STARTUP EVENT] Server startup: initializing workers via startup event..."
        )

        # IMPORTANT:
        # Startup events run BEFORE the server begins accepting connections.
        # We must NOT block here, otherwise the server won't bind the port and
        # proxy registration/health checks will fail.
        try:
            # Startup sequence: database driver → other workers
            # Start workers in background (non-blocking)
            import threading

            def _start_workers_bg() -> None:
                """Start all workers in background thread with error handling.

                Startup sequence: database driver → vectorization → file_watcher

                Returns:
                    None
                """
                try:
                    logger.info("🚀 [BACKGROUND] Starting database driver...")
                    startup_database_driver()
                    logger.info("✅ [BACKGROUND] Database driver started")
                except Exception as e:
                    logger.error(
                        f"❌ [BACKGROUND] Failed to start database driver: {e}",
                        exc_info=True,
                    )

                try:
                    logger.info("🚀 [BACKGROUND] Starting indexing worker...")
                    startup_indexing_worker()
                    logger.info("✅ [BACKGROUND] Indexing worker started")
                except Exception as e:
                    logger.error(
                        f"❌ [BACKGROUND] Failed to start indexing worker: {e}",
                        exc_info=True,
                    )

                try:
                    logger.info("🚀 [BACKGROUND] Starting vectorization worker...")
                    startup_vectorization_worker()
                    logger.info("✅ [BACKGROUND] Vectorization worker started")
                except Exception as e:
                    logger.error(
                        f"❌ [BACKGROUND] Failed to start vectorization worker: {e}",
                        exc_info=True,
                    )

                try:
                    logger.info("🚀 [BACKGROUND] Starting file watcher worker...")
                    startup_file_watcher_worker()
                    logger.info("✅ [BACKGROUND] File watcher worker started")
                except Exception as e:
                    logger.error(
                        f"❌ [BACKGROUND] Failed to start file watcher worker: {e}",
                        exc_info=True,
                    )

            thread = threading.Thread(target=_start_workers_bg, daemon=True)
            thread.start()

            print(
                "✅ [STARTUP EVENT] Workers startup scheduled in background",
                flush=True,
            )
            logger.info("✅ [STARTUP EVENT] Workers startup scheduled in background")
        except Exception as e:
            print(
                f"❌ [STARTUP EVENT] Failed to start workers: {e}",
                flush=True,
                file=sys.stderr,
            )
            logger.error(
                f"❌ [STARTUP EVENT] Failed to start workers: {e}", exc_info=True
            )

    @app.on_event("shutdown")  # type: ignore[misc]
    async def stop_workers_on_shutdown() -> None:
        """Stop workers on server shutdown.

        Returns:
            None
        """
        import logging

        logger = logging.getLogger(__name__)
        print(
            "🛑 [SHUTDOWN EVENT] Server shutdown: stopping workers via shutdown event...",
            flush=True,
        )
        logger.info(
            "🛑 [SHUTDOWN EVENT] Server shutdown: stopping workers via shutdown event..."
        )

        try:
            shutdown_cfg = (
                app_config.get("process_management")
                or app_config.get("server_manager")
                or {}
            )
            shutdown_timeout = DEFAULT_SHUTDOWN_GRACE_TIMEOUT
            if isinstance(shutdown_cfg, dict):
                try:
                    val = shutdown_cfg.get("shutdown_grace_seconds")
                    if isinstance(val, (int, float)) and float(val) > 0:
                        shutdown_timeout = float(val)
                except Exception:
                    shutdown_timeout = DEFAULT_SHUTDOWN_GRACE_TIMEOUT

            shutdown_result = worker_manager.stop_all_workers(timeout=shutdown_timeout)
            if shutdown_result.get("total_failed", 0) > 0:
                logger.warning(
                    f"⚠️  Some workers failed to stop: {shutdown_result.get('message')}"
                )
            else:
                logger.info(f"✅ All workers stopped: {shutdown_result.get('message')}")
        except Exception as e:
            logger.error(f"❌ Error stopping workers: {e}", exc_info=True)

    # Store worker manager in app state for shutdown
    app.state.worker_manager = worker_manager

    # Worker monitoring is started only in daemon mode, AFTER workers are started,
    # so the registry is populated before the monitor runs (avoids empty registry).

    # Commands are automatically registered via hooks
    # Queue manager is automatically initialized if enabled in config
    # Registration happens automatically via AppFactory if auto_on_startup is enabled
    # Worker startup functions are in main_workers module

    import logging

    main_logger = logging.getLogger(__name__)
    if not main_logger.handlers:
        # Configure logging if not already configured (unified format with importance)
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

    # Prepare server configuration for ServerEngine
    # Single process required: WorkerManager registry lives in this process;
    # get_worker_status reads from it. hypercorn.asyncio.serve() is single-process.
    server_config = {
        "host": server_host,
        "port": server_port,
        "log_level": "info",
        "reload": False,
        "workers": 1,
    }

    # Add SSL configuration if using mTLS
    from mcp_proxy_adapter.core.app_factory.ssl_config import build_server_ssl_config

    try:
        ssl_engine_config = build_server_ssl_config(app_config)
        if ssl_engine_config:
            server_config.update(ssl_engine_config)
    except ValueError as e:
        print(f"❌ SSL configuration invalid: {e}", file=sys.stderr)
        sys.exit(1)

    if not args.daemon and not args.foreground:
        _print_startup_info(
            config_path=config_path,
            server_host=server_host,
            server_port=server_port,
            server_config=server_config,
            app_config=app_config,
        )
        return

    # In foreground mode, enable faulthandler so segfault/abort dump to stderr (terminal)
    if args.foreground:
        try:
            import faulthandler

            faulthandler.enable()
        except Exception:
            pass

    # Register shutdown handlers for worker cleanup (before server starts)
    import atexit
    import signal
    import threading

    cleanup_lock = threading.Lock()
    cleanup_started = False

    def cleanup_workers() -> None:
        """Cleanup all workers on server exit.

        Returns:
            None
        """
        nonlocal cleanup_started
        with cleanup_lock:
            if cleanup_started:
                main_logger.info(
                    "cleanup_workers() already executed for this shutdown; skipping duplicate invocation"
                )
                return
            cleanup_started = True
        try:
            main_logger.info(
                "cleanup_workers() invoked (shutdown path); stopping workers"
            )
            main_logger.info("🛑 Server shutdown: stopping all workers")
            shutdown_cfg = (
                app_config.get("process_management")
                or app_config.get("server_manager")
                or {}
            )
            shutdown_timeout = DEFAULT_SHUTDOWN_GRACE_TIMEOUT
            if isinstance(shutdown_cfg, dict):
                try:
                    val = shutdown_cfg.get("shutdown_grace_seconds")
                    if isinstance(val, (int, float)) and float(val) > 0:
                        shutdown_timeout = float(val)
                except Exception:
                    shutdown_timeout = DEFAULT_SHUTDOWN_GRACE_TIMEOUT

            shutdown_result = worker_manager.stop_all_workers(timeout=shutdown_timeout)
            if shutdown_result.get("total_failed", 0) > 0:
                main_logger.warning(
                    f"⚠️  Some workers failed to stop: {shutdown_result.get('message')}"
                )
            else:
                main_logger.info(
                    f"✅ All workers stopped: {shutdown_result.get('message')}"
                )
        except Exception as e:
            main_logger.error(f"❌ Error stopping workers: {e}", exc_info=True)

    def signal_handler(signum: int, frame: object) -> None:
        """Handle shutdown signals.

        Args:
            signum: Signal number.
            frame: Signal frame (unused).

        Returns:
            None
        """
        main_logger.info(
            "Received signal %s, stopping all workers then exiting",
            signum,
        )
        cleanup_workers()
        main_logger.info("Signal handler: calling sys.exit(0) after cleanup")
        # If process doesn't exit gracefully, it will be killed by external process manager
        # (e.g., systemd, supervisor, or server_manager_cli with _kill_process_group)
        # This handler ensures workers are stopped before exit
        sys.exit(0)

    # Register handlers (before server starts, after app creation)
    atexit.register(cleanup_workers)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Start workers directly before server starts (startup events may not be called)
    # This ensures workers start regardless of FastAPI event system
    import logging

    worker_logger = logging.getLogger(__name__)
    worker_logger.info("🚀 Starting workers directly before server start...")
    print("🚀 Starting workers directly before server start...", flush=True)

    try:
        # Startup sequence: database driver → other workers
        # Database driver must start FIRST because other workers depend on it
        # Workers are separate processes (multiprocessing.Process), so no need for async/await
        # Startup functions are synchronous and called directly (not via asyncio.run())

        # Step 1: Start database driver (MUST be first)
        try:
            worker_logger.info("🚀 Starting database driver...")
            startup_database_driver()
            worker_logger.info("✅ Database driver started successfully")
        except Exception as e:
            worker_logger.error(
                f"❌ Failed to start database driver: {e}",
                exc_info=True,
            )
            print(
                f"❌ Failed to start database driver: {e}",
                flush=True,
                file=sys.stderr,
            )
            # Continue anyway - other workers may still work if driver is already running

        # Step 2: Start other workers (indexing, vectorization, file_watcher)
        worker_logger.info(
            "🔍 Starting other workers (indexing, vectorization, file_watcher) synchronously"
        )

        try:
            worker_logger.info("🚀 Starting indexing worker...")
            startup_indexing_worker()
            worker_logger.info("✅ Indexing worker started successfully")
        except Exception as e:
            worker_logger.error(
                f"❌ Failed to start indexing worker: {e}",
                exc_info=True,
            )
            print(
                f"❌ Failed to start indexing worker: {e}",
                flush=True,
                file=sys.stderr,
            )

        try:
            worker_logger.info("🚀 Starting vectorization worker...")
            startup_vectorization_worker()
            worker_logger.info("✅ Vectorization worker started successfully")
        except Exception as e:
            worker_logger.error(
                f"❌ Failed to start vectorization worker: {e}",
                exc_info=True,
            )
            print(
                f"❌ Failed to start vectorization worker: {e}",
                flush=True,
                file=sys.stderr,
            )

        try:
            worker_logger.info("🚀 Starting file watcher worker...")
            startup_file_watcher_worker()
            worker_logger.info("✅ File watcher worker started successfully")
        except Exception as e:
            worker_logger.error(
                f"❌ Failed to start file watcher worker: {e}",
                exc_info=True,
            )
            print(
                f"❌ Failed to start file watcher worker: {e}",
                flush=True,
                file=sys.stderr,
            )

        worker_logger.info("✅ All workers startup completed")
        print(
            "✅ Database driver and all workers started",
            flush=True,
        )
    except Exception as e:
        worker_logger.error(f"❌ Failed to start workers: {e}", exc_info=True)
        print(f"❌ Failed to start workers: {e}", flush=True, file=sys.stderr)
        # Continue anyway - server can start without workers

    # Start worker monitoring only after workers are started, so the registry
    # is populated in this process before the monitor runs (get_worker_status
    # reads from the same registry).
    try:
        worker_manager.start_monitoring(interval=DEFAULT_WORKER_MONITOR_INTERVAL)
        worker_logger.info("✅ Worker monitoring started (after workers)")
    except Exception as e:
        worker_logger.error(f"❌ Failed to start worker monitoring: {e}", exc_info=True)

    # Run server (single process: hypercorn.asyncio.serve, so registry stays in this process)
    engine = ServerEngineFactory.get_engine("hypercorn")
    if not engine:
        print("❌ Hypercorn engine not available", file=sys.stderr)
        sys.exit(1)

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
        main_logger.error(
            "Hypercorn run_server raised: %s",
            e,
            exc_info=True,
        )
        raise
    finally:
        if heartbeat_stop is not None:
            heartbeat_stop.set()
        main_logger.info("main() exiting after server loop")


if __name__ == "__main__":
    main()
