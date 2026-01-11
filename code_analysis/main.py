"""
Main entry point for code-analysis-server using mcp-proxy-adapter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
import sys
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
from code_analysis.commands.base_mcp_command import BaseMCPCommand

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
        default="config.json",
        help="Path to configuration file (default: config.json)",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Start the server (daemon mode). Without this flag the command prints startup info and exits.",
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
        import logging
        from pathlib import Path
        from code_analysis.core.db_worker_manager import get_db_worker_manager

        logger = logging.getLogger(__name__)
        logger.info("🚀 Server startup: initializing workers...")

        # DB worker is now started lazily by SQLiteDriverProxy.connect()
        # No automatic startup needed - worker will be started when database connection is requested

        # Start vectorization and file watcher workers
        await startup_vectorization_worker()
        await startup_file_watcher_worker()

        logger.info("✅ All workers started successfully")

        yield  # Server is running

        # Shutdown: cleanup workers
        logger.info("🛑 Server shutdown: stopping all workers...")
        try:
            shutdown_cfg = (
                app_config_lifespan.get("process_management")
                or app_config_lifespan.get("server_manager")
                or {}
            )
            shutdown_timeout = 30.0
            if isinstance(shutdown_cfg, dict):
                try:
                    val = shutdown_cfg.get("shutdown_grace_seconds")
                    if isinstance(val, (int, float)) and float(val) > 0:
                        shutdown_timeout = float(val)
                except Exception:
                    shutdown_timeout = 30.0

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
            # DB worker is now started lazily by SQLiteDriverProxy.connect()
            # No automatic startup needed - worker will be started when database connection is requested

            # Start vectorization and file watcher workers in background (non-blocking)
            import threading
            import asyncio

            def _start_non_db_workers_bg() -> None:
                """Start non-DB workers in background thread with error handling.

                Returns:
                    None
                """
                try:
                    logger.info("🚀 [BACKGROUND] Starting vectorization worker...")
                    asyncio.run(startup_vectorization_worker())
                    logger.info("✅ [BACKGROUND] Vectorization worker started")
                except Exception as e:
                    logger.error(
                        f"❌ [BACKGROUND] Failed to start vectorization worker: {e}",
                        exc_info=True,
                    )

                try:
                    logger.info("🚀 [BACKGROUND] Starting file watcher worker...")
                    asyncio.run(startup_file_watcher_worker())
                    logger.info("✅ [BACKGROUND] File watcher worker started")
                except Exception as e:
                    logger.error(
                        f"❌ [BACKGROUND] Failed to start file watcher worker: {e}",
                        exc_info=True,
                    )

            thread = threading.Thread(target=_start_non_db_workers_bg, daemon=True)
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
            shutdown_timeout = 30.0
            if isinstance(shutdown_cfg, dict):
                try:
                    val = shutdown_cfg.get("shutdown_grace_seconds")
                    if isinstance(val, (int, float)) and float(val) > 0:
                        shutdown_timeout = float(val)
                except Exception:
                    shutdown_timeout = 30.0

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

    # Start worker monitoring thread
    import logging

    monitoring_logger = logging.getLogger(__name__)
    try:
        worker_manager.start_monitoring(interval=30.0)
        monitoring_logger.info("✅ Worker monitoring started")
    except Exception as e:
        monitoring_logger.error(
            f"❌ Failed to start worker monitoring: {e}", exc_info=True
        )

    # Commands are automatically registered via hooks
    # Queue manager is automatically initialized if enabled in config
    # Registration happens automatically via AppFactory if auto_on_startup is enabled

    # Start vectorization worker on startup
    def startup_vectorization_worker() -> None:
        """Start universal vectorization worker in background process on server startup.

        Worker operates in universal mode - processes all projects from database.
        Worker works only with database - no filesystem access, no watch_dirs.
        Worker automatically discovers projects from database and processes them.

        Returns:
            None
        """
        import logging
        from pathlib import Path

        from code_analysis.core.config import ServerConfig
        from code_analysis.core.worker_manager import get_worker_manager

        logger = logging.getLogger(__name__)
        logger.info("🔍 startup_vectorization_worker called")

        try:
            # Get config from global config instance
            from mcp_proxy_adapter.config import get_config

            cfg = get_config()
            app_config = getattr(cfg, "config_data", {})
            if not app_config:
                # Fallback: try to load from config_path
                if hasattr(cfg, "config_path") and cfg.config_path:
                    import json

                    with open(cfg.config_path, "r", encoding="utf-8") as f:
                        app_config = json.load(f)

            logger.info(
                f"🔍 app_config loaded: {bool(app_config)}, keys: {list(app_config.keys()) if app_config else []}"
            )

            # Check if code_analysis config section exists
            code_analysis_config = app_config.get("code_analysis", {})
            logger.info(f"🔍 code_analysis_config found: {bool(code_analysis_config)}")
            if not code_analysis_config:
                logger.warning(
                    "⚠️  No code_analysis config found, skipping vectorization worker"
                )
                return

            # Check if SVO chunker is configured
            server_config = ServerConfig(**code_analysis_config)
            if not server_config.chunker:
                logger.warning(
                    "⚠️  No chunker config found, skipping vectorization worker"
                )
                return

            # Check if worker is enabled
            worker_config = server_config.worker
            if worker_config and isinstance(worker_config, dict):
                if not worker_config.get("enabled", True):
                    logger.info(
                        "ℹ️  Vectorization worker is disabled in config, skipping"
                    )
                    return

            # Resolve config_dir + state paths (do NOT place state under watched dirs)
            config_path = BaseMCPCommand._resolve_config_path()
            config_data = load_raw_config(config_path)
            storage = resolve_storage_paths(
                config_data=config_data, config_path=config_path
            )
            db_path = storage.db_path
            faiss_dir = storage.faiss_dir

            # Database auto-creation (only if database doesn't exist)
            db_path_obj = Path(db_path)
            if not db_path_obj.exists():
                logger.info(
                    f"Database file not found, creating new database at {db_path}"
                )
                try:
                    from code_analysis.core.database import CodeDatabase
                    from code_analysis.core.database.base import (
                        create_driver_config_for_worker,
                    )

                    # Ensure parent directory exists
                    db_path_obj.parent.mkdir(parents=True, exist_ok=True)

                    # Create database connection (will automatically create schema)
                    driver_config = create_driver_config_for_worker(
                        db_path=db_path_obj,
                        driver_type="sqlite_proxy",
                        backup_dir=storage.backup_dir,
                    )
                    init_database = CodeDatabase(driver_config=driver_config)
                    init_database.close()
                    logger.info(f"Created new database at {db_path}")
                except Exception as e:
                    logger.warning(
                        f"Failed to create database: {e}, continuing anyway",
                        exc_info=True,
                    )

            # Prepare SVO config
            svo_config = (
                server_config.model_dump()
                if hasattr(server_config, "model_dump")
                else server_config.dict()
            )

            # Get worker config parameters
            from code_analysis.core.constants import (
                DEFAULT_BATCH_SIZE,
                DEFAULT_POLL_INTERVAL,
            )

            vector_dim = server_config.vector_dim or 384
            batch_size = DEFAULT_BATCH_SIZE
            poll_interval = DEFAULT_POLL_INTERVAL
            worker_log_path = None  # default
            if worker_config and isinstance(worker_config, dict):
                batch_size = worker_config.get("batch_size", DEFAULT_BATCH_SIZE)
                poll_interval = worker_config.get(
                    "poll_interval", DEFAULT_POLL_INTERVAL
                )
                worker_log_path = worker_config.get("log_path")

            # Update log file path to universal name (no project_id in name)
            if worker_log_path:
                log_path_obj = Path(worker_log_path)
                worker_log_path = str(log_path_obj.parent / "vectorization_worker.log")
            else:
                # Default log path
                worker_log_path = str(
                    storage.config_dir / "logs" / "vectorization_worker.log"
                )

            # Start single universal worker using WorkerManager
            logger.info("🚀 Starting universal vectorization worker...")
            print("🚀 Starting universal vectorization worker...", flush=True)

            worker_manager = get_worker_manager()
            result = worker_manager.start_vectorization_worker(
                db_path=str(db_path),
                faiss_dir=str(faiss_dir),
                vector_dim=vector_dim,
                svo_config=svo_config,
                batch_size=batch_size,
                poll_interval=poll_interval,
                worker_log_path=worker_log_path,
            )

            if result.success:
                logger.info(
                    f"✅ Universal vectorization worker started: {result.message}"
                )
                print(f"✅ {result.message}", flush=True)
            else:
                logger.warning(
                    f"⚠️  Failed to start universal vectorization worker: {result.message}"
                )
                print(f"⚠️  {result.message}", flush=True)

        except Exception as e:
            print(
                f"❌ Failed to start vectorization worker: {e}",
                flush=True,
                file=sys.stderr,
            )
            logger.error(f"❌ Failed to start vectorization worker: {e}", exc_info=True)

    def startup_file_watcher_worker() -> None:
        """Start file watcher worker in background process on server startup.

        Returns:
            None
        """
        import logging
        from pathlib import Path

        from code_analysis.core.config import ServerConfig
        from code_analysis.core.worker_manager import get_worker_manager

        logger = logging.getLogger(__name__)
        logger.info("🔍 startup_file_watcher_worker called")

        try:
            # Get config from global config instance
            from mcp_proxy_adapter.config import get_config

            cfg = get_config()
            app_config = getattr(cfg, "config_data", {})
            if not app_config:
                # Fallback: try to load from config_path
                if hasattr(cfg, "config_path") and cfg.config_path:
                    import json

                    with open(cfg.config_path, "r", encoding="utf-8") as f:
                        app_config = json.load(f)

            logger.info(
                f"🔍 app_config loaded: {bool(app_config)}, keys: {list(app_config.keys()) if app_config else []}"
            )

            # Check if code_analysis config section exists
            code_analysis_config = app_config.get("code_analysis", {})
            logger.info(f"🔍 code_analysis_config found: {bool(code_analysis_config)}")
            if not code_analysis_config:
                logger.warning(
                    "⚠️  No code_analysis config found, skipping file watcher worker"
                )
                return

            # Check if file watcher is enabled
            server_config = ServerConfig(**code_analysis_config)
            file_watcher_config = server_config.file_watcher
            if not file_watcher_config or not isinstance(file_watcher_config, dict):
                logger.info(
                    "ℹ️  No file_watcher config found, skipping file watcher worker"
                )
                return

            if not file_watcher_config.get("enabled", True):
                logger.info("ℹ️  File watcher worker is disabled in config, skipping")
                return

            # Get watch_dirs from worker config (new format: list of dicts with 'id' and 'path')
            worker_config = server_config.worker
            watch_dirs_config: list[dict[str, str]] = []
            if worker_config and isinstance(worker_config, dict):
                watch_dirs_raw = worker_config.get("watch_dirs", [])
                # Validate format: must be list of dicts with 'id' and 'path'
                for wd in watch_dirs_raw:
                    if isinstance(wd, dict) and "id" in wd and "path" in wd:
                        watch_dirs_config.append(wd)
                    else:
                        logger.error(
                            f"Invalid watch_dir format: {wd}. "
                            "Expected: {{'id': 'uuid4', 'path': '/absolute/path'}}"
                        )

            if not watch_dirs_config:
                logger.warning(
                    "⚠️  No valid watch_dirs configured, skipping file watcher worker"
                )
                return

            # Resolve config_dir + state paths (do NOT place state under watched dirs)
            config_path = BaseMCPCommand._resolve_config_path()
            config_data = load_raw_config(config_path)
            storage = resolve_storage_paths(
                config_data=config_data, config_path=config_path
            )
            db_path = storage.db_path

            # Validate watch_dirs exist and normalize paths
            valid_watch_dirs: list[dict[str, str]] = []
            for watch_dir_config in watch_dirs_config:
                watch_dir_id = watch_dir_config["id"]
                watch_dir_path_str = watch_dir_config["path"]
                watch_dir_path = Path(watch_dir_path_str).resolve()
                if not watch_dir_path.exists():
                    logger.warning(
                        f"⚠️  Watch directory does not exist: {watch_dir_path}, skipping"
                    )
                    continue
                # Use normalized absolute path
                valid_watch_dirs.append({
                    "id": watch_dir_id,
                    "path": str(watch_dir_path),
                })

            if not valid_watch_dirs:
                logger.warning(
                    "⚠️  No valid watch directories found, skipping file watcher worker"
                )
                return

            scan_interval = file_watcher_config.get("scan_interval", 60)
            version_dir = file_watcher_config.get("version_dir", "data/versions")
            worker_log_path = file_watcher_config.get("log_path")
            ignore_patterns = file_watcher_config.get("ignore_patterns", [])

            # Use locks_dir from resolve_storage_paths (Step 4 of refactor plan)
            locks_dir = storage.locks_dir
            ensure_storage_dirs(storage)

            watch_dirs_count = len(valid_watch_dirs)
            print(
                f"🚀 Starting file watcher worker (single process) for {watch_dirs_count} watch directory(ies)",
                flush=True,
            )
            logger.info(
                f"🚀 Starting file watcher worker (single process) for {watch_dirs_count} watch directory(ies)"
            )
            logger.info(
                "ℹ️  Projects will be discovered automatically within each watch directory"
            )
            if worker_log_path:
                logger.info(f"📝 Worker log file: {worker_log_path}")

            # Start file watcher worker using WorkerManager
            worker_manager = get_worker_manager()
            result = worker_manager.start_file_watcher_worker(
                db_path=str(db_path),
                watch_dirs=valid_watch_dirs,
                locks_dir=str(locks_dir),
                scan_interval=scan_interval,
                version_dir=version_dir,
                worker_log_path=worker_log_path,
                ignore_patterns=ignore_patterns,
            )

            if result.success:
                logger.info(
                    f"✅ File watcher worker started: {result.message} for {watch_dirs_count} watch directory(ies)"
                )
                print(f"✅ {result.message}", flush=True)
            else:
                logger.warning(
                    f"⚠️  Failed to start file watcher worker: {result.message}"
                )
                print(f"⚠️  {result.message}", flush=True)

        except Exception as e:
            print(
                f"❌ Failed to start file watcher worker: {e}",
                flush=True,
                file=sys.stderr,
            )
            logger.error(f"❌ Failed to start file watcher worker: {e}", exc_info=True)

    # Setup logging for main module
    import logging

    main_logger = logging.getLogger(__name__)
    if not main_logger.handlers:
        # Configure logging if not already configured
        log_dir = Path(app_config.get("server", {}).get("log_dir", "./logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "mcp_server.log"

        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        main_logger.addHandler(handler)
        main_logger.setLevel(logging.INFO)

    # Prepare server configuration for ServerEngine
    server_config = {
        "host": server_host,
        "port": server_port,
        "log_level": "info",
        "reload": False,
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

    if not args.daemon:
        _print_startup_info(
            config_path=config_path,
            server_host=server_host,
            server_port=server_port,
            server_config=server_config,
            app_config=app_config,
        )
        return

    # Register shutdown handlers for worker cleanup (before server starts)
    import atexit
    import signal

    def cleanup_workers() -> None:
        """Cleanup all workers on server exit.

        Returns:
            None
        """
        try:
            main_logger.info("🛑 Server shutdown: stopping all workers")
            shutdown_cfg = (
                app_config.get("process_management")
                or app_config.get("server_manager")
                or {}
            )
            shutdown_timeout = 30.0
            if isinstance(shutdown_cfg, dict):
                try:
                    val = shutdown_cfg.get("shutdown_grace_seconds")
                    if isinstance(val, (int, float)) and float(val) > 0:
                        shutdown_timeout = float(val)
                except Exception:
                    shutdown_timeout = 30.0

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
        import os
        import signal as signal_module

        main_logger.info(f"Received signal {signum}, stopping all workers...")
        cleanup_workers()

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
        # DB worker is now started lazily by SQLiteDriverProxy.connect()
        # No automatic startup needed - worker will be started when database connection is requested

        # Start vectorization and file watcher workers synchronously
        # Workers are separate processes (multiprocessing.Process), so no need for async/await
        # This avoids asyncio.run() conflicts with Hypercorn's event loop
        worker_logger.info(
            "🔍 Starting non-DB workers (file_watcher, vectorization) synchronously"
        )

        # DB worker is started lazily by SQLiteDriverProxy.connect()
        # No need to check or start it here
        worker_logger.info(
            "🔍 DB worker will be started lazily when database connection is requested"
        )

        # Start non-DB workers synchronously (they are separate processes)
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

        worker_logger.info("✅ Non-DB workers startup completed")
        print(
            "✅ DB worker started, non-DB workers started",
            flush=True,
        )
    except Exception as e:
        worker_logger.error(f"❌ Failed to start workers: {e}", exc_info=True)
        print(f"❌ Failed to start workers: {e}", flush=True, file=sys.stderr)
        # Continue anyway - server can start without workers

    # Run server
    engine = ServerEngineFactory.get_engine("hypercorn")
    if not engine:
        print("❌ Hypercorn engine not available", file=sys.stderr)
        sys.exit(1)

    engine.run_server(app, server_config)


if __name__ == "__main__":
    main()
