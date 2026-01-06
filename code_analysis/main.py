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
                    f"\n❌ Configuration validation failed: {summary['errors']} error(s), {summary['warnings']} warning(s)",
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

    # Override host/port from CLI if provided
    if args.host:
        simple_config.model.server.host = args.host
    if args.port:
        simple_config.model.server.port = args.port

    server_host = args.host or model.server.host
    server_port = args.port or model.server.port

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

        # Start DB worker first (required for other workers)
        try:
            from mcp_proxy_adapter.config import get_config

            cfg = get_config()
            app_config_lifespan = getattr(cfg, "config_data", {})
            if not app_config_lifespan:
                if hasattr(cfg, "config_path") and cfg.config_path:
                    import json

                    with open(cfg.config_path, "r", encoding="utf-8") as f:
                        app_config_lifespan = json.load(f)

            code_analysis_config = app_config_lifespan.get("code_analysis", {})
            if code_analysis_config:
                root_dir = Path.cwd()
                db_path = root_dir / "data" / "code_analysis.db"

                log_dir = Path(
                    app_config_lifespan.get("server", {}).get("log_dir", "./logs")
                )
                worker_log_path = str(log_dir / "db_worker.log")

                logger.info(f"🚀 Starting DB worker for database: {db_path}")
                db_worker_manager = get_db_worker_manager()
                worker_info = db_worker_manager.get_or_start_worker(
                    str(db_path),
                    worker_log_path,
                )
                logger.info(f"✅ DB worker started (PID: {worker_info['pid']})")
        except Exception as e:
            logger.error(f"❌ Failed to start DB worker: {e}", exc_info=True)

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
            # Start DB worker first
            from pathlib import Path
            from code_analysis.core.db_worker_manager import get_db_worker_manager

            from mcp_proxy_adapter.config import get_config

            cfg = get_config()
            app_config_lifespan = getattr(cfg, "config_data", {})
            if not app_config_lifespan:
                if hasattr(cfg, "config_path") and cfg.config_path:
                    import json

                    with open(cfg.config_path, "r", encoding="utf-8") as f:
                        app_config_lifespan = json.load(f)

            code_analysis_config = app_config_lifespan.get("code_analysis", {})
            if code_analysis_config:
                root_dir = Path.cwd()
                db_path = root_dir / "data" / "code_analysis.db"
                log_dir = Path(
                    app_config_lifespan.get("server", {}).get("log_dir", "./logs")
                )
                worker_log_path = str(log_dir / "db_worker.log")

                logger.info(f"🚀 Starting DB worker for database: {db_path}")
                db_worker_manager = get_db_worker_manager()
                worker_info = db_worker_manager.get_or_start_worker(
                    str(db_path),
                    worker_log_path,
                )
                logger.info(f"✅ DB worker started (PID: {worker_info['pid']})")

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
    async def startup_vectorization_worker() -> None:
        """Start vectorization worker in background process on server startup.

        Returns:
            None
        """
        import multiprocessing
        from pathlib import Path
        from code_analysis.core.vectorization_worker_pkg import run_vectorization_worker
        from code_analysis.core.config import ServerConfig
        from code_analysis.core.faiss_manager import FaissIndexManager

        import logging

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

            # Get watch_dirs from worker config - these are project directories
            watch_dirs = []
            if worker_config and isinstance(worker_config, dict):
                watch_dirs = worker_config.get("watch_dirs", [])

            if not watch_dirs:
                logger.warning(
                    "⚠️  No watch_dirs configured, skipping vectorization worker"
                )
                return

            # Get or create projects for each watch_dir
            # Use proxy driver since we're in the main server process, not a worker
            project_ids = []
            try:
                logger.info(f"[STEP 1] Creating driver config for db_path={db_path}")
                from code_analysis.core.database import CodeDatabase
                from code_analysis.core.database.base import (
                    create_driver_config_for_worker,
                )

                driver_config = create_driver_config_for_worker(
                    db_path=db_path,
                    driver_type="sqlite_proxy",
                )
                logger.info(
                    f"[STEP 2] Driver config created: type={driver_config.get('type')}"
                )

                # Override timeout and poll_interval for proxy driver
                if driver_config.get("type") == "sqlite_proxy":
                    driver_config["config"]["worker_config"]["command_timeout"] = 60.0
                    driver_config["config"]["worker_config"]["poll_interval"] = 1.0
                    logger.info(
                        "[STEP 3] Proxy driver config updated: timeout=60.0, poll_interval=1.0"
                    )

                logger.info(
                    "[STEP 4] Creating CodeDatabase instance with driver_config (with retry)"
                )
                # Retry logic: DB worker may need time to be ready
                import time

                max_retries = 5
                retry_delay = 2.0
                database = None
                for attempt in range(max_retries):
                    try:
                        database = CodeDatabase(driver_config=driver_config)
                        logger.info(
                            f"[STEP 5] CodeDatabase created on attempt {attempt + 1}, getting/creating projects for {len(watch_dirs)} directories"
                        )
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"⚠️  Failed to create CodeDatabase on attempt {attempt + 1}/{max_retries}: {e}, retrying in {retry_delay}s"
                            )
                            time.sleep(retry_delay)
                        else:
                            raise

                if not database:
                    raise RuntimeError(
                        "Failed to create CodeDatabase after all retries"
                    )

                # Get or create project for each watch_dir
                for watch_dir in watch_dirs:
                    watch_dir_path = Path(watch_dir).resolve()
                    if not watch_dir_path.exists():
                        logger.warning(
                            f"⚠️  Watch directory does not exist: {watch_dir_path}, skipping"
                        )
                        continue

                    project_id = database.get_or_create_project(
                        str(watch_dir_path), name=watch_dir_path.name
                    )
                    project_ids.append(project_id)
                    logger.info(f"[STEP 6] Project for {watch_dir_path}: {project_id}")

                database.close()
                logger.info("[STEP 7] Database connection closed")

                if not project_ids:
                    logger.warning(
                        "⚠️  No valid projects found or created, skipping vectorization worker"
                    )
                    return
            except Exception as e:
                logger.error(f"⚠️  Failed to get/create projects: {e}", exc_info=True)
                return

            # Dataset-scoped FAISS: rebuild index for each dataset (Step 2 of refactor plan)
            vector_dim = server_config.vector_dim or 384

            # Initialize SVO client manager for rebuild (in case embeddings need to be regenerated)
            try:
                from code_analysis.core.svo_client_manager import SVOClientManager
                from code_analysis.core.storage_paths import get_faiss_index_path
                from code_analysis.core.project_resolution import normalize_root_dir

                svo_client_manager = SVOClientManager(server_config)
                await svo_client_manager.initialize()

                # Rebuild FAISS index from database (vectors are stored in database)
                logger.info("🔄 Rebuilding FAISS indexes from database (dataset-scoped)...")
                from code_analysis.core.database.base import (
                    create_driver_config_for_worker,
                )

                driver_config = create_driver_config_for_worker(db_path)
                database = CodeDatabase(driver_config=driver_config)
                try:
                    total_vectors = 0
                    # For each project, rebuild FAISS index for each dataset
                    for project_id in project_ids:
                        # Get all datasets for this project
                        datasets = database.get_project_datasets(project_id)
                        if not datasets:
                            logger.warning(
                                f"⚠️  No datasets found for project {project_id}, skipping FAISS rebuild"
                            )
                            continue

                        for dataset in datasets:
                            dataset_id = dataset["id"]
                            dataset_root = dataset["root_path"]
                            logger.info(
                                f"🔄 Rebuilding FAISS index for project={project_id}, "
                                f"dataset={dataset_id} (root={dataset_root})"
                            )

                            # Get dataset-scoped FAISS index path
                            index_path = get_faiss_index_path(
                                storage.faiss_dir, project_id, dataset_id
                            )

                            # Initialize FAISS manager for this dataset
                            faiss_manager = FaissIndexManager(
                                index_path=str(index_path),
                                vector_dim=vector_dim,
                            )

                            # Rebuild index for this dataset
                            vectors_count = await faiss_manager.rebuild_from_database(
                                database,
                                svo_client_manager,
                                project_id=project_id,
                                dataset_id=dataset_id,
                            )
                            total_vectors += vectors_count
                            logger.info(
                                f"✅ FAISS index rebuilt for dataset {dataset_id}: "
                                f"{vectors_count} vectors loaded"
                            )
                            faiss_manager.close()

                    logger.info(
                        f"✅ All FAISS indexes rebuilt: {total_vectors} total vectors loaded"
                    )
                finally:
                    database.close()
                    await svo_client_manager.close()

            except Exception as e:
                logger.warning(f"⚠️  Failed to rebuild FAISS indexes: {e}", exc_info=True)
                # Continue anyway - indexes will be empty but worker can still start

            # Prepare SVO config
            svo_config = (
                server_config.model_dump()
                if hasattr(server_config, "model_dump")
                else server_config.dict()
            )

            # Get worker config parameters
            worker_config = server_config.worker
            batch_size = 10  # default
            poll_interval = 30  # default
            worker_log_path = None  # default
            if worker_config and isinstance(worker_config, dict):
                batch_size = worker_config.get("batch_size", 10)
                poll_interval = worker_config.get("poll_interval", 30)
                worker_log_path = worker_config.get("log_path")

            # Start worker process for each dataset (dataset-scoped vectorization)
            from code_analysis.core.storage_paths import get_faiss_index_path
            from code_analysis.core.vectorization_worker_pkg.runner import run_vectorization_worker

            started_processes = []
            for project_id in project_ids:
                # Get all datasets for this project
                driver_config = create_driver_config_for_worker(db_path)
                database = CodeDatabase(driver_config=driver_config)
                try:
                    datasets = database.get_project_datasets(project_id)
                    if not datasets:
                        logger.warning(
                            f"⚠️  No datasets found for project {project_id}, skipping vectorization worker"
                        )
                        continue

                    # Start worker for each dataset
                    for dataset in datasets:
                        dataset_id = dataset["id"]
                        dataset_root = dataset["root_path"]
                        
                        # Get dataset-scoped FAISS index path
                        index_path = get_faiss_index_path(
                            storage.faiss_dir, project_id, dataset_id
                        )

                        # Create unique log path for each dataset if base log path is provided
                        dataset_log_path = None
                        if worker_log_path:
                            log_path_obj = Path(worker_log_path)
                            dataset_log_path = str(
                                log_path_obj.parent
                                / f"{log_path_obj.stem}_{project_id[:8]}_{dataset_id[:8]}{log_path_obj.suffix}"
                            )

                        scope_desc = f"project={project_id}, dataset={dataset_id} (root={dataset_root})"
                        print(
                            f"🚀 Starting vectorization worker for {scope_desc}", flush=True
                        )
                        logger.info(f"🚀 Starting vectorization worker for {scope_desc}")
                        if dataset_log_path:
                            logger.info(f"📝 Worker log file: {dataset_log_path}")

                        process = multiprocessing.Process(
                            target=run_vectorization_worker,
                            args=(
                                str(db_path),
                                project_id,
                                str(index_path),
                                vector_dim,
                                dataset_id,  # Pass dataset_id for dataset-scoped processing
                            ),
                            kwargs={
                                "svo_config": svo_config,
                                "batch_size": batch_size,
                                "poll_interval": poll_interval,
                                "worker_log_path": dataset_log_path,
                            },
                            daemon=True,  # Daemon process will be killed when parent exits
                        )
                        process.start()
                        print(
                            f"✅ Vectorization worker started with PID {process.pid} for {scope_desc}",
                            flush=True,
                        )
                        logger.info(
                            f"✅ Vectorization worker started with PID {process.pid} for {scope_desc}"
                        )
                        started_processes.append(process)

                        # Write PID file next to log file (used by get_worker_status)
                        if dataset_log_path:
                            try:
                                pid_file_path = Path(dataset_log_path).with_suffix(".pid")
                                pid_file_path.write_text(str(process.pid))
                            except Exception:
                                logger.exception(
                                    f"Failed to write vectorization worker PID file for {scope_desc}"
                                )

                            # Create restart function for this worker (capture values, not references)
                            _db_path_val = str(db_path)
                            _project_id_val = project_id
                            _dataset_id_val = dataset_id
                            _faiss_index_path_val = str(index_path)
                            _vector_dim_val = vector_dim
                            _svo_config_val = svo_config
                            _batch_size_val = batch_size
                            _poll_interval_val = poll_interval
                            _dataset_log_path_val = dataset_log_path

                            def _restart_vectorization_worker() -> dict[str, Any]:
                                """Restart vectorization worker.

                                Returns:
                                    Worker registration data for WorkerManager.
                                """
                                new_process = multiprocessing.Process(
                                    target=run_vectorization_worker,
                                    args=(
                                        _db_path_val,
                                        _project_id_val,
                                        _faiss_index_path_val,
                                        _vector_dim_val,
                                        _dataset_id_val,  # Pass dataset_id
                                    ),
                                    kwargs={
                                        "svo_config": _svo_config_val,
                                        "batch_size": _batch_size_val,
                                        "poll_interval": _poll_interval_val,
                                        "worker_log_path": _dataset_log_path_val,
                                    },
                                    daemon=True,
                                )
                                new_process.start()
                                if _dataset_log_path_val:
                                    try:
                                        pid_file_path = Path(_dataset_log_path_val).with_suffix(
                                            ".pid"
                                        )
                                        pid_file_path.write_text(str(new_process.pid))
                                    except Exception:
                                        pass
                                return {
                                    "pid": new_process.pid,
                                    "process": new_process,
                                    "name": f"vectorization_{_project_id_val}_{_dataset_id_val[:8]}",
                                    "restart_func": _restart_vectorization_worker,
                                    "restart_args": (),
                                    "restart_kwargs": {},
                                }

                            # Register worker in WorkerManager with restart function
                            from code_analysis.core.worker_manager import get_worker_manager

                            worker_manager = get_worker_manager()
                            worker_name = f"vectorization_{project_id}_{dataset_id[:8]}"
                            logger.info(
                                f"📝 Registering vectorization worker in WorkerManager: "
                                f"PID={process.pid}, {scope_desc}"
                            )
                            worker_manager.register_worker(
                                "vectorization",
                                {
                                    "pid": process.pid,
                                    "process": process,
                                    "name": worker_name,
                                    "restart_func": _restart_vectorization_worker,
                                    "restart_args": (),
                                    "restart_kwargs": {},
                                },
                            )
                            logger.info(
                                f"✅ Vectorization worker registered in WorkerManager: "
                                f"PID={process.pid}, name={worker_name}"
                            )
                            started_processes.append((project_id, dataset_id, process))
                finally:
                    database.close()

            total_workers = len(started_processes)
            total_projects = len(project_ids)
            logger.info(
                f"✅ Started {total_workers} vectorization worker(s) for {total_projects} project(s)"
            )

        except Exception as e:
            print(
                f"❌ Failed to start vectorization worker: {e}",
                flush=True,
                file=sys.stderr,
            )
            logger.error(f"❌ Failed to start vectorization worker: {e}", exc_info=True)

    async def startup_file_watcher_worker() -> None:
        """Start file watcher worker in background process on server startup.

        Returns:
            None
        """
        import logging
        import multiprocessing
        from pathlib import Path

        from code_analysis.core.config import ServerConfig
        from code_analysis.core.file_watcher_pkg import run_file_watcher_worker

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

            # Get watch_dirs from worker config (same as vectorization worker)
            worker_config = server_config.worker
            watch_dirs: list[str] = []
            if worker_config and isinstance(worker_config, dict):
                watch_dirs = worker_config.get("watch_dirs", [])

            if not watch_dirs:
                logger.warning(
                    "⚠️  No watch_dirs configured, skipping file watcher worker"
                )
                return

            # Resolve config_dir + state paths (do NOT place state under watched dirs)
            config_path = BaseMCPCommand._resolve_config_path()
            config_data = load_raw_config(config_path)
            storage = resolve_storage_paths(
                config_data=config_data, config_path=config_path
            )
            db_path = storage.db_path

            # Get or create projects for each watch_dir
            project_watch_dirs: list[tuple[str, str]] = []
            try:
                logger.info(f"[STEP 1] Creating driver config for db_path={db_path}")
                from code_analysis.core.database import CodeDatabase
                from code_analysis.core.database.base import (
                    create_driver_config_for_worker,
                )

                driver_config = create_driver_config_for_worker(
                    db_path=db_path,
                    driver_type="sqlite_proxy",
                )
                logger.info(
                    f"[STEP 2] Driver config created: type={driver_config.get('type')}"
                )

                # Override timeout and poll_interval for proxy driver
                if driver_config.get("type") == "sqlite_proxy":
                    driver_config["config"]["worker_config"]["command_timeout"] = 60.0
                    driver_config["config"]["worker_config"]["poll_interval"] = 1.0
                    logger.info(
                        "[STEP 3] Proxy driver config updated: timeout=60.0, poll_interval=1.0"
                    )

                logger.info(
                    "[STEP 4] Creating CodeDatabase instance with driver_config (with retry)"
                )
                import time

                max_retries = 5
                retry_delay = 2.0
                database = None
                for attempt in range(max_retries):
                    try:
                        database = CodeDatabase(driver_config=driver_config)
                        logger.info(
                            f"[STEP 5] CodeDatabase created on attempt {attempt + 1}, getting/creating projects for {len(watch_dirs)} directories"
                        )
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"⚠️  Failed to create CodeDatabase on attempt {attempt + 1}/{max_retries}: {e}, retrying in {retry_delay}s"
                            )
                            time.sleep(retry_delay)
                        else:
                            raise

                if not database:
                    raise RuntimeError(
                        "Failed to create CodeDatabase after all retries"
                    )

                for watch_dir in watch_dirs:
                    watch_dir_path = Path(watch_dir).resolve()
                    if not watch_dir_path.exists():
                        logger.warning(
                            f"⚠️  Watch directory does not exist: {watch_dir_path}, skipping"
                        )
                        continue

                    project_id = database.get_or_create_project(
                        str(watch_dir_path), name=watch_dir_path.name
                    )
                    project_watch_dirs.append((project_id, str(watch_dir_path)))
                    logger.info(f"[STEP 6] Project for {watch_dir_path}: {project_id}")

                database.close()
                logger.info("[STEP 7] Database connection closed")

                if not project_watch_dirs:
                    logger.warning(
                        "⚠️  No valid projects found or created, skipping file watcher worker"
                    )
                    return
            except Exception as e:
                logger.error(f"⚠️  Failed to get/create projects: {e}", exc_info=True)
                return

            scan_interval = file_watcher_config.get("scan_interval", 60)
            version_dir = file_watcher_config.get("version_dir", "data/versions")
            worker_log_path = file_watcher_config.get("log_path")
            ignore_patterns = file_watcher_config.get("ignore_patterns", [])

            # Use locks_dir from resolve_storage_paths (Step 4 of refactor plan)
            locks_dir = storage.locks_dir
            ensure_storage_dirs(storage)

            projects_count = len(project_watch_dirs)
            print(
                f"🚀 Starting file watcher worker (single process) for {projects_count} project(s)",
                flush=True,
            )
            logger.info(
                f"🚀 Starting file watcher worker (single process) for {projects_count} project(s)"
            )
            if worker_log_path:
                logger.info(f"📝 Worker log file: {worker_log_path}")

            process = multiprocessing.Process(
                target=run_file_watcher_worker,
                args=(
                    str(db_path),
                    list(project_watch_dirs),
                ),
                kwargs={
                    "locks_dir": str(locks_dir),
                    "scan_interval": scan_interval,
                    "version_dir": version_dir,
                    "worker_log_path": worker_log_path,
                    "ignore_patterns": ignore_patterns,
                },
                daemon=True,
            )
            process.start()

            print(
                f"✅ File watcher worker started with PID {process.pid} for {projects_count} project(s)",
                flush=True,
            )
            logger.info(
                f"✅ File watcher worker started with PID {process.pid} for {projects_count} project(s)"
            )

            # Write PID file next to log file (used by get_worker_status)
            if worker_log_path:
                try:
                    pid_file_path = Path(worker_log_path).with_suffix(".pid")
                    pid_file_path.write_text(str(process.pid))
                except Exception:
                    logger.exception("Failed to write file watcher PID file")

            _db_path_fw_val = str(db_path)
            _project_watch_dirs_fw_val = list(project_watch_dirs)
            _scan_interval_fw_val = scan_interval
            _locks_dir_fw_val = str(locks_dir)
            _version_dir_fw_val = version_dir
            _worker_log_path_fw_val = worker_log_path
            _ignore_patterns_fw_val = ignore_patterns

            def _restart_file_watcher_worker() -> dict[str, Any]:
                """Restart file watcher worker.

                Returns:
                    Worker registration data for WorkerManager.
                """
                new_process = multiprocessing.Process(
                    target=run_file_watcher_worker,
                    args=(
                        _db_path_fw_val,
                        list(_project_watch_dirs_fw_val),
                    ),
                    kwargs={
                        "locks_dir": _locks_dir_fw_val,
                        "scan_interval": _scan_interval_fw_val,
                        "version_dir": _version_dir_fw_val,
                        "worker_log_path": _worker_log_path_fw_val,
                        "ignore_patterns": _ignore_patterns_fw_val,
                    },
                    daemon=True,
                )
                new_process.start()
                if _worker_log_path_fw_val:
                    try:
                        pid_file_path = Path(_worker_log_path_fw_val).with_suffix(
                            ".pid"
                        )
                        pid_file_path.write_text(str(new_process.pid))
                    except Exception:
                        pass
                return {
                    "pid": new_process.pid,
                    "process": new_process,
                    "name": "file_watcher_multi",
                    "restart_func": _restart_file_watcher_worker,
                    "restart_args": (),
                    "restart_kwargs": {},
                }

            from code_analysis.core.worker_manager import get_worker_manager

            worker_manager = get_worker_manager()
            logger.info(
                f"📝 Registering file_watcher worker in WorkerManager: PID={process.pid}, projects={projects_count}"
            )
            worker_manager.register_worker(
                "file_watcher",
                {
                    "pid": process.pid,
                    "process": process,
                    "name": "file_watcher_multi",
                    "restart_func": _restart_file_watcher_worker,
                    "restart_args": (),
                    "restart_kwargs": {},
                },
            )
            logger.info(
                f"✅ File watcher worker registered in WorkerManager: PID={process.pid}"
            )

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
        main_logger.info(f"Received signal {signum}, stopping all workers...")
        cleanup_workers()
        sys.exit(0)

    # Register handlers (before server starts, after app creation)
    atexit.register(cleanup_workers)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Start workers directly before server starts (startup events may not be called)
    # This ensures workers start regardless of FastAPI event system
    import asyncio
    import logging

    worker_logger = logging.getLogger(__name__)
    worker_logger.info("🚀 Starting workers directly before server start...")
    print("🚀 Starting workers directly before server start...", flush=True)

    try:
        # Start DB worker first
        from code_analysis.core.db_worker_manager import get_db_worker_manager

        # Resolve DB path from config using resolve_storage_paths
        storage = resolve_storage_paths(config_data=app_config, config_path=config_path)
        ensure_storage_dirs(storage)
        db_path = storage.db_path

        log_dir = Path(app_config.get("server", {}).get("log_dir", "./logs"))
        if not log_dir.is_absolute():
            log_dir = (storage.config_dir / log_dir).resolve()
        worker_log_path = str(log_dir / "db_worker.log")

        worker_logger.info(f"🚀 Starting DB worker for database: {db_path}")
        print(f"🚀 Starting DB worker for database: {db_path}", flush=True)
        db_worker_manager = get_db_worker_manager()
        worker_info = db_worker_manager.get_or_start_worker(
            str(db_path),
            worker_log_path,
        )
        worker_logger.info(f"✅ DB worker started (PID: {worker_info['pid']})")
        print(f"✅ DB worker started (PID: {worker_info['pid']})", flush=True)

        # Wait for DB worker to be ready before starting other workers
        # Note: get_or_start_worker already waits for socket file to exist,
        # but we add additional delay to ensure worker is fully initialized
        import time

        socket_path = worker_info.get("socket_path")
        worker_logger.info(f"🔍 DB worker socket_path: {socket_path}")
        if socket_path:
            worker_logger.info(
                f"⏳ Waiting for DB worker to initialize (socket: {socket_path})"
            )
            socket_file = Path(socket_path)
            # Wait for socket file to exist (with timeout)
            max_wait = 5.0  # Maximum wait time in seconds
            wait_interval = 0.1  # Check every 100ms
            waited = 0.0
            while not socket_file.exists() and waited < max_wait:
                time.sleep(wait_interval)
                waited += wait_interval

            if socket_file.exists():
                worker_logger.info(
                    f"✅ DB worker socket file exists after {waited:.1f}s"
                )
                # Additional wait to ensure worker is accepting connections
                time.sleep(1.0)  # Give worker time to start listening
                worker_logger.info(
                    "✅ DB worker socket exists, waiting additional 1s for initialization"
                )
            else:
                worker_logger.warning(
                    f"⚠️  DB worker socket not created after {waited:.1f}s, continuing anyway"
                )
        else:
            worker_logger.warning(
                "⚠️  No socket_path in worker_info, waiting 3s as fallback"
            )
            time.sleep(3.0)

        worker_logger.info(
            "✅ DB worker initialization wait completed, proceeding to start other workers"
        )

        # Start vectorization and file watcher workers in background
        # IMPORTANT: do not set/close the global event loop in the main thread
        # (Hypercorn will manage its own asyncio loop).
        async def _start_non_db_workers() -> None:
            """Start non-DB workers with error handling.

            Returns:
                None
            """
            worker_logger.info(
                "🔍 [MAIN] Entering _start_non_db_workers async function"
            )

            # Check DB worker status before starting
            worker_logger.info(
                "🔍 [MAIN] Checking DB worker status before starting other workers..."
            )
            try:
                from code_analysis.core.db_worker_manager import get_db_worker_manager

                db_worker_manager_check = get_db_worker_manager()
                worker_info_check = db_worker_manager_check.get_or_start_worker(
                    str(db_path),
                    str(log_dir / "db_worker.log"),
                )
                socket_path_check = worker_info_check.get("socket_path")
                worker_logger.info(
                    f"🔍 [MAIN] DB worker socket_path: {socket_path_check}"
                )
                if socket_path_check:
                    socket_file_check = Path(socket_path_check)
                    exists = socket_file_check.exists()
                    worker_logger.info(f"🔍 [MAIN] Socket file exists: {exists}")
                    if exists:
                        stat = socket_file_check.stat()
                        worker_logger.info(
                            f"🔍 [MAIN] Socket file size: {stat.st_size}, mode: {oct(stat.st_mode)}"
                        )
                    else:
                        worker_logger.warning(
                            "⚠️  [MAIN] Socket file does not exist, waiting longer..."
                        )
                        await asyncio.sleep(3.0)
                        exists_after_wait = socket_file_check.exists()
                        worker_logger.info(
                            f"🔍 [MAIN] Socket file exists after wait: {exists_after_wait}"
                        )
            except Exception as e:
                worker_logger.error(
                    f"❌ [MAIN] Failed to check DB worker: {e}", exc_info=True
                )

            # Additional wait in async context to ensure DB worker is fully ready
            import asyncio

            worker_logger.info("⏳ [MAIN] Waiting 2s before starting workers...")
            await asyncio.sleep(2.0)
            worker_logger.info(
                "✅ [MAIN] Wait completed, starting vectorization worker..."
            )

            try:
                worker_logger.info("🚀 [MAIN] Starting vectorization worker...")
                await startup_vectorization_worker()
                worker_logger.info(
                    "✅ [MAIN] Vectorization worker started successfully"
                )
            except Exception as e:
                worker_logger.error(
                    f"❌ [MAIN] Failed to start vectorization worker: {e}",
                    exc_info=True,
                )
                print(
                    f"❌ [MAIN] Failed to start vectorization worker: {e}",
                    flush=True,
                    file=sys.stderr,
                )

            try:
                worker_logger.info("🚀 [MAIN] Starting file watcher worker...")
                await startup_file_watcher_worker()
                worker_logger.info("✅ [MAIN] File watcher worker started successfully")
            except Exception as e:
                worker_logger.error(
                    f"❌ [MAIN] Failed to start file watcher worker: {e}",
                    exc_info=True,
                )
                print(
                    f"❌ [MAIN] Failed to start file watcher worker: {e}",
                    flush=True,
                    file=sys.stderr,
                )

            worker_logger.info("✅ [MAIN] _start_non_db_workers completed")

        import threading

        def _start_non_db_workers_thread() -> None:
            """Start non-DB workers in background thread.

            Returns:
                None
            """
            worker_logger.info("🔍 [THREAD] Entering _start_non_db_workers_thread")
            try:
                worker_logger.info(
                    "🔍 [THREAD] Calling asyncio.run(_start_non_db_workers)..."
                )
                asyncio.run(_start_non_db_workers())
                worker_logger.info("✅ [THREAD] asyncio.run completed successfully")
            except Exception as e:
                worker_logger.error(
                    f"❌ [THREAD] Failed to start non-DB workers: {e}",
                    exc_info=True,
                )
                print(
                    f"❌ [THREAD] Failed to start non-DB workers: {e}",
                    flush=True,
                    file=sys.stderr,
                )

        worker_logger.info("🔍 Creating background thread for non-DB workers...")
        thread = threading.Thread(target=_start_non_db_workers_thread, daemon=True)
        thread.start()
        worker_logger.info(f"✅ Background thread started: {thread.is_alive()}")

        worker_logger.info(
            "✅ DB worker started, non-DB workers starting in background thread"
        )
        print(
            "✅ DB worker started, non-DB workers starting in background thread",
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
