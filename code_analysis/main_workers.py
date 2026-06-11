"""
Worker startup functions for code-analysis-server. Extracted from main.py.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import sys
from pathlib import Path
from typing import Union

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.core.storage_paths import (
    apply_resolved_batch_output_dir,
    ensure_storage_dirs,
    load_raw_config,
    resolve_storage_paths,
)
from code_analysis.core.constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_DATABASE_DRIVER_LOG_FILENAME,
    DEFAULT_POLL_INTERVAL,
)
from code_analysis.core.config import ServerConfig, get_driver_config
from code_analysis.core.worker_manager import get_worker_manager


def startup_database_driver() -> None:
    """Start database driver process in background on server startup.

    Database driver must be started BEFORE other workers that depend on it.
    Driver configuration is loaded from code_analysis.database.driver section.

    Returns:
        None
    """
    logger = logging.getLogger(__name__)
    logger.info("🔍 startup_database_driver called")

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

        # Get driver config from code_analysis.database.driver
        driver_config = get_driver_config(app_config)
        if not driver_config:
            logger.warning(
                "⚠️  No database driver config found in code_analysis.database.driver, "
                "skipping database driver startup"
            )
            return

        driver_type = driver_config.get("type")
        logger.info(f"🔍 Driver config found: type={driver_type}")

        if driver_type == "postgres":
            logger.info(
                "ℹ️  PostgreSQL driver runs in-process; skipping database driver subprocess"
            )
            print(
                "ℹ️  PostgreSQL: in-process database driver (no subprocess)",
                flush=True,
            )
            return

        # Resolve storage paths for log file
        config_path = BaseMCPCommand._resolve_config_path()
        config_data = load_raw_config(config_path)
        storage = resolve_storage_paths(
            config_data=config_data, config_path=config_path
        )

        # Generate log path for driver
        log_path = str(storage.log_dir / DEFAULT_DATABASE_DRIVER_LOG_FILENAME)
        ensure_storage_dirs(storage)

        # SQLite: force same absolute DB path as storage (avoids cwd-dependent resolution).
        config_dict: dict = dict(driver_config.get("config", {}) or {})
        driver_config_resolved = {
            "type": driver_config.get("type"),
            "config": config_dict,
        }
        if driver_type in ("sqlite", "sqlite_proxy"):
            config_dict["path"] = str(storage.db_path.resolve())
        if "query_log_path" not in config_dict:
            config_dict["query_log_path"] = str(
                storage.log_dir / "database_queries.jsonl"
            )

        # Start database driver using WorkerManager
        logger.info("🚀 Starting database driver...")
        print("🚀 Starting database driver...", flush=True)

        worker_manager = get_worker_manager()
        result = worker_manager.start_database_driver(
            driver_config=driver_config_resolved,
            log_path=log_path,
        )

        if result.success:
            logger.info(f"✅ Database driver started: {result.message}")
            print(f"✅ {result.message}", flush=True)
        else:
            logger.warning(f"⚠️  Failed to start database driver: {result.message}")
            print(f"⚠️  {result.message}", flush=True)

    except Exception as e:
        print(
            f"❌ Failed to start database driver: {e}",
            flush=True,
            file=sys.stderr,
        )
        logger.error(f"❌ Failed to start database driver: {e}", exc_info=True)


# Start indexing worker on startup (before vectorization so indexer clears needs_chunking first)
def startup_indexing_worker() -> None:
    """Start indexing worker in background process on server startup.

    Worker processes files with needs_chunking=1 via driver index_file RPC.
    Must run before vectorization worker (startup order).

    Returns:
        None
    """
    logger = logging.getLogger(__name__)
    logger.info("🔍 startup_indexing_worker called")

    try:
        from mcp_proxy_adapter.config import get_config

        cfg = get_config()
        app_config = getattr(cfg, "config_data", {})
        if not app_config and getattr(cfg, "config_path", None):
            import json

            with open(cfg.config_path, "r", encoding="utf-8") as f:
                app_config = json.load(f)

        code_analysis_config = app_config.get("code_analysis", {}) or {}
        indexing_cfg = code_analysis_config.get("indexing_worker") or {}
        if isinstance(indexing_cfg, dict) and not indexing_cfg.get("enabled", True):
            logger.info("ℹ️  Indexing worker is disabled in config, skipping")
            return

        config_path = BaseMCPCommand._resolve_config_path()
        config_data = load_raw_config(config_path)
        storage = resolve_storage_paths(
            config_data=config_data, config_path=config_path
        )
        db_path = storage.db_path

        poll_interval = 30
        batch_size = 5
        worker_log_path = str(storage.log_dir / "indexing_worker.log")
        log_timing = False
        worker_cfg = code_analysis_config.get("worker") or {}
        if isinstance(worker_cfg, dict):
            log_timing = worker_cfg.get("log_all_operations_timing", False)
        if isinstance(indexing_cfg, dict):
            poll_interval = indexing_cfg.get("poll_interval", 30)
            batch_size = indexing_cfg.get("batch_size", 5)
            if indexing_cfg.get("log_path"):
                worker_log_path = indexing_cfg["log_path"]

        worker_logs_dir = str(Path(worker_log_path).resolve().parent)
        worker_manager = get_worker_manager()
        result = worker_manager.start_indexing_worker(
            db_path=str(db_path),
            config_path=str(config_path),
            poll_interval=int(poll_interval),
            batch_size=int(batch_size),
            worker_log_path=worker_log_path,
            worker_logs_dir=worker_logs_dir,
            log_timing=log_timing,
        )
        if result.success:
            logger.info(f"✅ Indexing worker started: {result.message}")
            print(f"✅ {result.message}", flush=True)
        else:
            logger.warning(f"⚠️  Failed to start indexing worker: {result.message}")
            print(f"⚠️  {result.message}", flush=True)
    except Exception as e:
        logger.error(f"❌ Failed to start indexing worker: {e}", exc_info=True)
        print(f"❌ Failed to start indexing worker: {e}", flush=True, file=sys.stderr)


# Start vectorization worker on startup
def startup_vectorization_worker() -> None:
    """Start universal vectorization worker in background process on server startup.

    Worker operates in universal mode - processes all projects from database.
    Worker works only with database - no filesystem access, no watch_dirs.
    Worker automatically discovers projects from database and processes them.

    Returns:
        None
    """
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

        # Check if code_analysis config section exists (fallback: load from config file)
        code_analysis_config = app_config.get("code_analysis", {}) if app_config else {}
        fallback_config_path = getattr(cfg, "config_path", None)
        if (
            not code_analysis_config
            and fallback_config_path
            and Path(fallback_config_path).exists()
        ):
            try:
                import json

                with open(fallback_config_path, "r", encoding="utf-8") as f:
                    app_config = json.load(f)
                code_analysis_config = app_config.get("code_analysis", {})
            except Exception as e:
                logger.debug(f"Could not load config from {fallback_config_path}: {e}")
        logger.info(f"🔍 code_analysis_config found: {bool(code_analysis_config)}")
        if not code_analysis_config:
            logger.warning(
                "⚠️  No code_analysis config found, skipping vectorization worker"
            )
            return

        # Filter out 'database' field - it's not part of ServerConfig model
        # ServerConfig has extra="forbid": only pass keys that exist on the model.
        config_path = BaseMCPCommand._resolve_config_path()
        _allowed = set(ServerConfig.model_fields.keys())
        server_config_dict = apply_resolved_batch_output_dir(
            {k: v for k, v in code_analysis_config.items() if k in _allowed},
            Path(config_path),
        )

        # Check if SVO chunker is configured
        server_config = ServerConfig(**server_config_dict)
        if not server_config.chunker:
            logger.warning("⚠️  No chunker config found, skipping vectorization worker")
            return

        # Check if worker is enabled
        worker_config = server_config.worker
        if worker_config and isinstance(worker_config, dict):
            if not worker_config.get("enabled", True):
                logger.info("ℹ️  Vectorization worker is disabled in config, skipping")
                return

        # Resolve config_dir + state paths (do NOT place state under watched dirs)
        config_data = load_raw_config(config_path)
        storage = resolve_storage_paths(
            config_data=config_data, config_path=config_path
        )
        db_path = storage.db_path
        faiss_dir = storage.faiss_dir

        # Database auto-creation (only if database doesn't exist)
        db_path_obj = Path(db_path)
        if not db_path_obj.exists():
            logger.info(f"Database file not found, creating new database at {db_path}")
            try:
                from code_analysis.core.database_driver_pkg.drivers.sqlite import (
                    SQLiteDriver,
                )
                from code_analysis.core.database_driver_pkg.drivers.postgres import (
                    PostgreSQLDriver,
                )
                from code_analysis.core.database.base import (
                    create_driver_config_for_worker,
                )
                from code_analysis.core.config import get_driver_config
                from code_analysis.core.database.schema_definition import (
                    get_schema_definition,
                )

                db_path_obj.parent.mkdir(parents=True, exist_ok=True)

                driver_config = None
                try:
                    driver_config = get_driver_config(app_config)
                except Exception as e:
                    logger.debug(f"Could not get driver config from config: {e}")

                if not driver_config:
                    driver_config = create_driver_config_for_worker(
                        db_path=db_path_obj,
                        driver_type="sqlite_proxy",
                        backup_dir=storage.backup_dir,
                    )
                else:
                    if "config" in driver_config and "path" in driver_config["config"]:
                        driver_config["config"]["path"] = str(db_path_obj)
                    if storage.backup_dir and "config" in driver_config:
                        driver_config["config"]["backup_dir"] = str(storage.backup_dir)

                schema_definition = get_schema_definition()
                backup_dir = str(storage.backup_dir) if storage.backup_dir else None
                driver_type = (
                    driver_config.get("type", "sqlite") if driver_config else "sqlite"
                )
                driver_cfg = (
                    driver_config.get("config", {"path": str(db_path_obj)})
                    if driver_config
                    else {"path": str(db_path_obj)}
                )

                init_driver: Union[PostgreSQLDriver, SQLiteDriver]
                if driver_type == "postgres":
                    init_driver = PostgreSQLDriver()
                else:
                    init_driver = SQLiteDriver()
                init_driver.connect(driver_cfg)
                init_driver.sync_schema(schema_definition, backup_dir)
                init_driver.disconnect()
                logger.info(f"Created new database at {db_path}")
            except Exception as e:
                logger.warning(
                    f"Failed to create database: {e}, continuing anyway",
                    exc_info=True,
                )

        # Prepare SVO config (absolute batch_output_dir for worker subprocess cwd)
        svo_config = apply_resolved_batch_output_dir(
            (
                server_config.model_dump()
                if hasattr(server_config, "model_dump")
                else server_config.dict()
            ),
            Path(config_path),
        )

        # Get worker config parameters
        vector_dim = server_config.vector_dim or 384
        batch_size = DEFAULT_BATCH_SIZE
        poll_interval = DEFAULT_POLL_INTERVAL
        worker_log_path = None  # default
        if worker_config and isinstance(worker_config, dict):
            batch_size = worker_config.get("batch_size", DEFAULT_BATCH_SIZE)
            poll_interval = worker_config.get("poll_interval", DEFAULT_POLL_INTERVAL)
            worker_log_path = worker_config.get("log_path")

        # Update log file path to universal name (no project_id in name)
        if worker_log_path:
            log_path_obj = Path(worker_log_path)
            worker_log_path = str(log_path_obj.parent / "vectorization_worker.log")
        else:
            # Default log path
            worker_log_path = str(storage.log_dir / "vectorization_worker.log")

        # Start single universal worker using WorkerManager
        # Use absolute logs dir for PID file so worker start is not blocked by cwd/stale PID
        worker_logs_dir = str(Path(worker_log_path).resolve().parent)
        logger.info("🚀 Starting universal vectorization worker...")
        print("🚀 Starting universal vectorization worker...", flush=True)

        worker_manager = get_worker_manager()
        result = worker_manager.start_vectorization_worker(
            db_path=str(db_path),
            faiss_dir=str(faiss_dir),
            config_path=str(config_path),
            vector_dim=vector_dim,
            svo_config=svo_config,
            batch_size=batch_size,
            poll_interval=poll_interval,
            worker_log_path=worker_log_path,
            worker_logs_dir=worker_logs_dir,
        )

        if result.success:
            logger.info(f"✅ Universal vectorization worker started: {result.message}")
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


def startup_file_watcher_worker() -> bool:
    """Start file watcher worker in background process on server startup.

    Returns:
        True if the worker process was started, False if skipped or failed.
    """
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
            return False

        # ServerConfig has extra="forbid": only pass keys that exist on the model.
        # Excludes e.g. "database" (used by driver), not by ServerConfig.
        _allowed = set(ServerConfig.model_fields.keys())
        server_config_dict = {
            k: v for k, v in code_analysis_config.items() if k in _allowed
        }

        # Check if file watcher is enabled
        server_config = ServerConfig(**server_config_dict)
        file_watcher_config = server_config.file_watcher
        if not file_watcher_config or not isinstance(file_watcher_config, dict):
            logger.info(
                "ℹ️  No file_watcher config found, skipping file watcher worker"
            )
            return False

        if not file_watcher_config.get("enabled", True):
            logger.info("ℹ️  File watcher worker is disabled in config, skipping")
            return False

        from code_analysis.main_workers_file_watcher import (
            build_file_watcher_watch_dir_entries,
            parse_worker_watch_dirs_raw,
        )

        watch_dirs_config = parse_worker_watch_dirs_raw(code_analysis_config)
        if not watch_dirs_config:
            logger.warning(
                "⚠️  No watch_dirs in config yet; starting file watcher anyway "
                "(will reload from config.json each scan cycle)"
            )

        # Resolve config_dir + state paths (do NOT place state under watched dirs)
        config_path = BaseMCPCommand._resolve_config_path()
        config_data = load_raw_config(config_path)
        storage = resolve_storage_paths(
            config_data=config_data, config_path=config_path
        )
        db_path = storage.db_path

        watch_dirs_for_worker = build_file_watcher_watch_dir_entries(watch_dirs_config)

        scan_interval = file_watcher_config.get("scan_interval", 60)
        version_dir = file_watcher_config.get("version_dir", "data/versions")
        worker_log_path = file_watcher_config.get("log_path")
        ignore_patterns = file_watcher_config.get("ignore_patterns", [])

        # Use locks_dir from resolve_storage_paths (Step 4 of refactor plan)
        locks_dir = storage.locks_dir
        ensure_storage_dirs(storage)

        watch_dirs_count = len(watch_dirs_for_worker)
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
        if not worker_log_path:
            worker_log_path = str(storage.log_dir / "file_watcher.log")
        worker_logs_dir = str(Path(worker_log_path).resolve().parent)
        if worker_log_path:
            logger.info(f"📝 Worker log file: {worker_log_path}")

        # Start file watcher worker using WorkerManager
        worker_manager = get_worker_manager()
        result = worker_manager.start_file_watcher_worker(
            db_path=str(db_path),
            watch_dirs=watch_dirs_for_worker,
            locks_dir=str(locks_dir),
            scan_interval=scan_interval,
            version_dir=version_dir,
            worker_log_path=worker_log_path,
            worker_logs_dir=worker_logs_dir,
            ignore_patterns=ignore_patterns,
            config_path=str(config_path),
        )

        if result.success:
            logger.info(
                f"✅ File watcher worker started: {result.message} for {watch_dirs_count} watch directory(ies)"
            )
            print(f"✅ {result.message}", flush=True)
            return True
        logger.warning(f"⚠️  Failed to start file watcher worker: {result.message}")
        print(f"⚠️  {result.message}", flush=True)
        return False

    except Exception as e:
        print(
            f"❌ Failed to start file watcher worker: {e}",
            flush=True,
            file=sys.stderr,
        )
        logger.error(f"❌ Failed to start file watcher worker: {e}", exc_info=True)
        return False
