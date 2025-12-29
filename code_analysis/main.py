"""
Main entry point for code-analysis-server using mcp-proxy-adapter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# Apply registration patch before importing adapter
from .core.registration_patch import patch_registration_manager

patch_registration_manager()

from mcp_proxy_adapter.api.core.app_factory import AppFactory
from mcp_proxy_adapter.core.config.simple_config import SimpleConfig
from mcp_proxy_adapter.core.server_engine import ServerEngineFactory

from . import hooks  # noqa: F401


def _print_startup_info(
    *,
    config_path: Path,
    server_host: str,
    server_port: int,
    server_config: dict[str, Any],
    app_config: dict[str, Any],
) -> None:
    """Print server startup info without actually starting the server process."""
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
    """Main function to run code-analysis-server."""
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

    # Load full config including custom sections (like code_analysis)
    import json

    with open(config_path, "r", encoding="utf-8") as f:
        full_config = json.load(f)
        # Merge custom sections into app_config
        for key, value in full_config.items():
            if key not in app_config:
                app_config[key] = value

    # Validate configuration if starting in daemon mode
    if args.daemon:
        from code_analysis.core.config_validator import CodeAnalysisConfigValidator

        validator = CodeAnalysisConfigValidator()
        try:
            validation_results = validator.validate_config(full_config)
            summary = validator.get_validation_summary()

            if not summary["is_valid"]:
                # Log errors
                errors = [r for r in validation_results if r.level == "error"]
                warnings = [r for r in validation_results if r.level == "warning"]

                # Setup logging to write to stderr and log file
                import logging

                log_dir = Path(app_config.get("server", {}).get("log_dir", "./logs"))
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file = log_dir / "mcp_server.log"

                # Configure logging
                logging.basicConfig(
                    level=logging.ERROR,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[
                        logging.FileHandler(log_file, encoding="utf-8"),
                        logging.StreamHandler(sys.stderr),
                    ],
                )
                logger = logging.getLogger(__name__)

                logger.error("❌ Configuration validation failed:")
                for error in errors:
                    section_info = (
                        f" ({error.section}"
                        + (f".{error.key}" if error.key else "")
                        + ")"
                        if error.section
                        else ""
                    )
                    error_msg = f"   - {error.message}{section_info}"
                    if error.suggestion:
                        error_msg += f" - {error.suggestion}"
                    logger.error(error_msg)

                if warnings:
                    logger.warning("⚠️  Warnings:")
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
                        logger.warning(warning_msg)

                # Print to stderr as well
                print("❌ Configuration validation failed:", file=sys.stderr)
                for error in errors:
                    section_info = (
                        f" ({error.section}"
                        + (f".{error.key}" if error.key else "")
                        + ")"
                        if error.section
                        else ""
                    )
                    print(f"   - {error.message}{section_info}", file=sys.stderr)
                    if error.suggestion:
                        print(f"     Suggestion: {error.suggestion}", file=sys.stderr)

                print(
                    f"\n   Log file: {log_file}",
                    file=sys.stderr,
                )
                print(
                    "   Fix configuration errors and try again.",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Log warnings if any (but don't stop server)
            warnings = [r for r in validation_results if r.level == "warning"]
            if warnings:
                import logging

                log_dir = Path(app_config.get("server", {}).get("log_dir", "./logs"))
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file = log_dir / "mcp_server.log"

                logging.basicConfig(
                    level=logging.WARNING,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[
                        logging.FileHandler(log_file, encoding="utf-8"),
                    ],
                )
                logger = logging.getLogger(__name__)

                logger.warning("⚠️  Configuration validation warnings:")
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
                    logger.warning(warning_msg)

        except Exception as e:
            print(
                f"❌ Failed to validate configuration: {e}",
                file=sys.stderr,
            )
            import logging

            log_dir = Path(app_config.get("server", {}).get("log_dir", "./logs"))
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "mcp_server.log"

            logging.basicConfig(
                level=logging.ERROR,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                handlers=[
                    logging.FileHandler(log_file, encoding="utf-8"),
                    logging.StreamHandler(sys.stderr),
                ],
            )
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to validate configuration: {e}", exc_info=True)
            sys.exit(1)

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
    async def lifespan(app_instance):
        """Lifespan context manager for automatic worker startup and shutdown."""
        import multiprocessing
        import logging
        from pathlib import Path
        from code_analysis.core.db_worker_manager import get_db_worker_manager
        from code_analysis.core.config import ServerConfig

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
                server_config = ServerConfig(**code_analysis_config)
                root_dir = Path.cwd()
                db_path = root_dir / "data" / "code_analysis.db"

                log_dir = Path(app_config_lifespan.get("server", {}).get("log_dir", "./logs"))
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

    # Add lifespan context manager to app (FastAPI supports this via router)
    # Note: This wraps the existing lifespan if any, or adds new one
    if hasattr(app.router, "lifespan_context") and app.router.lifespan_context:
        # If app already has lifespan, we need to wrap it
        original_lifespan = app.router.lifespan_context
        @asynccontextmanager
        async def wrapped_lifespan(app_instance):
            async with original_lifespan(app_instance):
                async with lifespan(app_instance):
                    yield
        app.router.lifespan_context = wrapped_lifespan
    else:
        # No existing lifespan, just set ours
        app.router.lifespan_context = lifespan

    # Store worker manager in app state for shutdown
    app.state.worker_manager = worker_manager

    # Commands are automatically registered via hooks
    # Queue manager is automatically initialized if enabled in config
    # Registration happens automatically via AppFactory if auto_on_startup is enabled

    # Start vectorization worker on startup
    async def startup_vectorization_worker() -> None:
        """Start vectorization worker in background process on server startup."""
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

            # Get database path from config or use default
            root_dir = Path.cwd()
            db_path = root_dir / "data" / "code_analysis.db"

            # Get project ID (use first project or default)
            # Use proxy driver since we're in the main server process, not a worker
            try:
                logger.info(f"[STEP 1] Creating driver config for db_path={db_path}")
                from code_analysis.core.database import CodeDatabase
                from code_analysis.core.database.base import create_driver_config_for_worker

                driver_config = create_driver_config_for_worker(
                    db_path=db_path,
                    driver_type="sqlite_proxy",
                )
                logger.info(f"[STEP 2] Driver config created: type={driver_config.get('type')}")
                
                # Override timeout and poll_interval for proxy driver
                if driver_config.get("type") == "sqlite_proxy":
                    driver_config["config"]["worker_config"]["command_timeout"] = 60.0
                    driver_config["config"]["worker_config"]["poll_interval"] = 1.0
                    logger.info(f"[STEP 3] Proxy driver config updated: timeout=60.0, poll_interval=1.0")
                
                logger.info(f"[STEP 4] Creating CodeDatabase instance with driver_config")
                database = CodeDatabase(driver_config=driver_config)
                logger.info(f"[STEP 5] CodeDatabase created, executing query to get project_id")
                
                row = database._fetchone("SELECT id FROM projects ORDER BY created_at LIMIT 1")
                logger.info(f"[STEP 6] Query executed, result: {row}")
                
                project_id = row["id"] if row else None
                logger.info(f"[STEP 7] Extracted project_id: {project_id}")
                
                database.close()
                logger.info(f"[STEP 8] Database connection closed")

                if not project_id:
                    logger.warning(
                        "⚠️  No projects found in database, skipping vectorization worker"
                    )
                    return
            except Exception as e:
                logger.error(
                    f"⚠️  Failed to get project ID at step: {e}", exc_info=True
                )
                return

            # Get FAISS index path and vector dimension
            faiss_index_path = root_dir / "data" / "faiss_index"
            vector_dim = (
                server_config.vector_dim or 384
            )  # Default dimension, should match chunker model

            # Initialize FAISS manager and rebuild from database
            try:
                from code_analysis.core.svo_client_manager import SVOClientManager

                faiss_manager = FaissIndexManager(
                    index_path=str(faiss_index_path),
                    vector_dim=vector_dim,
                )

                # Initialize SVO client manager for rebuild (in case embeddings need to be regenerated)
                svo_client_manager = SVOClientManager(server_config)
                await svo_client_manager.initialize()

                # Rebuild FAISS index from database (vectors are stored in database)
                logger.info("🔄 Rebuilding FAISS index from database...")
                from code_analysis.core.database.base import create_driver_config_for_worker

                driver_config = create_driver_config_for_worker(db_path)
                database = CodeDatabase(driver_config=driver_config)
                try:
                    vectors_count = await faiss_manager.rebuild_from_database(
                        database, svo_client_manager
                    )
                    logger.info(
                        f"✅ FAISS index rebuilt: {vectors_count} vectors loaded from database"
                    )
                finally:
                    database.close()
                    await svo_client_manager.close()

            except Exception as e:
                logger.warning(f"⚠️  Failed to rebuild FAISS index: {e}", exc_info=True)
                # Continue anyway - index will be empty but worker can still start

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

            # Start worker in separate process
            print(
                f"🚀 Starting vectorization worker for project {project_id}", flush=True
            )
            logger.info(f"🚀 Starting vectorization worker for project {project_id}")
            if worker_log_path:
                logger.info(f"📝 Worker log file: {worker_log_path}")
            process = multiprocessing.Process(
                target=run_vectorization_worker,
                args=(
                    str(db_path),
                    project_id,
                    str(faiss_index_path),
                    vector_dim,
                ),
                kwargs={
                    "svo_config": svo_config,
                    "batch_size": batch_size,
                    "poll_interval": poll_interval,
                    "worker_log_path": worker_log_path,
                },
                daemon=True,  # Daemon process will be killed when parent exits
            )
            process.start()
            print(f"✅ Vectorization worker started with PID {process.pid}", flush=True)
            logger.info(f"✅ Vectorization worker started with PID {process.pid}")

            # Register worker in WorkerManager
            worker_manager.register_worker(
                "vectorization",
                {
                    "pid": process.pid,
                    "process": process,
                    "name": f"vectorization_{project_id}",
                },
            )

        except Exception as e:
            print(
                f"❌ Failed to start vectorization worker: {e}",
                flush=True,
                file=sys.stderr,
            )
            logger.error(f"❌ Failed to start vectorization worker: {e}", exc_info=True)

    # Start file watcher worker on startup
    async def startup_file_watcher_worker() -> None:
        """Start file watcher worker in background process on server startup."""
        import multiprocessing
        from pathlib import Path
        from code_analysis.core.file_watcher_pkg import run_file_watcher_worker
        from code_analysis.core.config import ServerConfig

        import logging

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
            watch_dirs = []
            if worker_config and isinstance(worker_config, dict):
                watch_dirs = worker_config.get("watch_dirs", [])

            if not watch_dirs:
                logger.warning(
                    "⚠️  No watch_dirs configured, skipping file watcher worker"
                )
                return

            # Get database path from config or use default
            root_dir = Path.cwd()
            db_path = root_dir / "data" / "code_analysis.db"

            # Get project ID (use first project or default)
            # Use proxy driver since we're in the main server process, not a worker
            try:
                logger.info(f"[STEP 1] Creating driver config for db_path={db_path}")
                from code_analysis.core.database import CodeDatabase
                from code_analysis.core.database.base import create_driver_config_for_worker

                driver_config = create_driver_config_for_worker(
                    db_path=db_path,
                    driver_type="sqlite_proxy",
                )
                logger.info(f"[STEP 2] Driver config created: type={driver_config.get('type')}")
                
                # Override timeout and poll_interval for proxy driver
                if driver_config.get("type") == "sqlite_proxy":
                    driver_config["config"]["worker_config"]["command_timeout"] = 60.0
                    driver_config["config"]["worker_config"]["poll_interval"] = 1.0
                    logger.info(f"[STEP 3] Proxy driver config updated: timeout=60.0, poll_interval=1.0")
                
                logger.info(f"[STEP 4] Creating CodeDatabase instance with driver_config")
                database = CodeDatabase(driver_config=driver_config)
                logger.info(f"[STEP 5] CodeDatabase created, executing query to get project_id")
                
                row = database._fetchone("SELECT id FROM projects ORDER BY created_at LIMIT 1")
                logger.info(f"[STEP 6] Query executed, result: {row}")
                
                project_id = row["id"] if row else None
                logger.info(f"[STEP 7] Extracted project_id: {project_id}")
                
                database.close()
                logger.info(f"[STEP 8] Database connection closed")

                if not project_id:
                    logger.warning(
                        "⚠️  No projects found in database, skipping file watcher worker"
                    )
                    return
            except Exception as e:
                logger.error(
                    f"⚠️  Failed to get project ID at step: {e}", exc_info=True
                )
                return

            # Get file watcher config parameters
            scan_interval = file_watcher_config.get("scan_interval", 60)
            lock_file_name = file_watcher_config.get(
                "lock_file_name", ".file_watcher.lock"
            )
            version_dir = file_watcher_config.get("version_dir", "data/versions")
            worker_log_path = file_watcher_config.get("log_path")
            ignore_patterns = file_watcher_config.get("ignore_patterns", [])

            # Get project root (use first watch_dir or None)
            project_root = None
            if watch_dirs:
                try:
                    project_root = str(Path(watch_dirs[0]).resolve())
                except Exception:
                    pass

            # Start worker in separate process
            print(
                f"🚀 Starting file watcher worker for project {project_id}", flush=True
            )
            logger.info(f"🚀 Starting file watcher worker for project {project_id}")
            if worker_log_path:
                logger.info(f"📝 Worker log file: {worker_log_path}")
            process = multiprocessing.Process(
                target=run_file_watcher_worker,
                args=(
                    str(db_path),
                    project_id,
                    watch_dirs,
                ),
                kwargs={
                    "scan_interval": scan_interval,
                    "lock_file_name": lock_file_name,
                    "version_dir": version_dir,
                    "worker_log_path": worker_log_path,
                    "project_root": project_root,
                    "ignore_patterns": ignore_patterns,
                },
                daemon=True,  # Daemon process will be killed when parent exits
            )
            process.start()
            print(f"✅ File watcher worker started with PID {process.pid}", flush=True)
            logger.info(f"✅ File watcher worker started with PID {process.pid}")

            # Register worker in WorkerManager
            worker_manager.register_worker(
                "file_watcher",
                {
                    "pid": process.pid,
                    "process": process,
                    "name": f"file_watcher_{project_id}",
                },
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
    # Note: Workers are started via lifespan context manager, cleanup is handled there too
    atexit.register(cleanup_workers)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Run server
    engine = ServerEngineFactory.get_engine("hypercorn")
    if not engine:
        print("❌ Hypercorn engine not available", file=sys.stderr)
        sys.exit(1)

    engine.run_server(app, server_config)


if __name__ == "__main__":
    main()
