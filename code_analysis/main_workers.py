"""
Worker startup functions for code-analysis-server. Extracted from main.py.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import sys
from pathlib import Path

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.core.storage_paths import (
    ensure_storage_dirs,
    load_raw_config,
    resolve_storage_paths,
)
from code_analysis.core.config import get_driver_config
from code_analysis.core.worker_manager import get_worker_manager
from code_analysis.core.worker_start_args import (
    resolve_file_watcher_worker_kwargs,
    resolve_indexing_worker_kwargs,
    resolve_vectorization_worker_kwargs,
)


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

        # PostgreSQL is the only supported driver and always runs in-process
        # (SQLite subprocess-driver architecture was removed).
        logger.info(
            "ℹ️  PostgreSQL driver runs in-process; skipping database driver subprocess"
        )
        print(
            "ℹ️  PostgreSQL: in-process database driver (no subprocess)",
            flush=True,
        )
        return

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

        config_path = BaseMCPCommand._resolve_config_path()
        plan = resolve_indexing_worker_kwargs(app_config, config_path)
        if not plan.ok:
            logger.info("ℹ️  Indexing worker not started: %s", plan.skip_reason)
            return

        worker_manager = get_worker_manager()
        result = worker_manager.start_indexing_worker(**plan.kwargs)
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

        config_path = BaseMCPCommand._resolve_config_path()

        # Resolve boot-parity start kwargs first (config filtering, chunker/
        # enabled checks) -- gates DB auto-creation below exactly like the
        # pre-refactor early-returns did.
        plan = resolve_vectorization_worker_kwargs(app_config, config_path)
        if not plan.ok:
            logger.warning(
                "⚠️  Vectorization worker not started: %s", plan.skip_reason
            )
            return

        # Resolve config_dir + state paths (do NOT place state under watched dirs)
        config_data = load_raw_config(config_path)
        storage = resolve_storage_paths(
            config_data=config_data, config_path=config_path
        )
        db_path = storage.db_path

        # Database auto-creation (only if database doesn't exist)
        db_path_obj = Path(db_path)
        if not db_path_obj.exists():
            logger.info(f"Database file not found, creating new database at {db_path}")
            try:
                from code_analysis.core.database_driver_pkg.drivers.postgres import (
                    PostgreSQLDriver,
                )
                from code_analysis.core.config import get_driver_config
                from code_analysis.core.database.schema_definition import (
                    get_schema_definition,
                )
                from code_analysis.core.exceptions import ConfigurationError

                db_path_obj.parent.mkdir(parents=True, exist_ok=True)

                driver_config = None
                try:
                    driver_config = get_driver_config(app_config)
                except Exception as e:
                    logger.debug(f"Could not get driver config from config: {e}")

                if not driver_config:
                    raise ConfigurationError(
                        "code_analysis.database.driver configuration is required "
                        "(PostgreSQL); SQLite support was removed.",
                        config_key="database.driver",
                    )
                if storage.backup_dir and "config" in driver_config:
                    driver_config["config"]["backup_dir"] = str(storage.backup_dir)

                schema_definition = get_schema_definition()
                backup_dir = str(storage.backup_dir) if storage.backup_dir else None
                driver_type = driver_config.get("type")
                if driver_type != "postgres":
                    raise ConfigurationError(
                        f"driver_type {driver_type!r} is not supported: SQLite "
                        "support was removed; PostgreSQL is required.",
                        config_key="database.driver.type",
                    )
                driver_cfg = driver_config.get("config", {})

                init_driver: PostgreSQLDriver = PostgreSQLDriver()
                init_driver.connect(driver_cfg)
                init_driver.sync_schema(schema_definition, backup_dir)
                init_driver.disconnect()
                logger.info(f"Created new database at {db_path}")
            except Exception as e:
                logger.warning(
                    f"Failed to create database: {e}, continuing anyway",
                    exc_info=True,
                )

        # Start single universal worker using WorkerManager, using the
        # already-resolved boot-parity kwargs (db_path/faiss_dir/config_path/
        # vector_dim/svo_config/batch_size/poll_interval/worker_log_path/
        # worker_logs_dir).
        logger.info("🚀 Starting universal vectorization worker...")
        print("🚀 Starting universal vectorization worker...", flush=True)

        worker_manager = get_worker_manager()
        result = worker_manager.start_vectorization_worker(**plan.kwargs)

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

        config_path = BaseMCPCommand._resolve_config_path()
        plan = resolve_file_watcher_worker_kwargs(app_config, config_path)
        if not plan.ok:
            logger.info(
                "ℹ️  File watcher worker not started: %s", plan.skip_reason
            )
            return False

        if not plan.kwargs["watch_dirs"]:
            logger.warning(
                "⚠️  No watch_dirs in config yet; starting file watcher anyway "
                "(will reload from config.json each scan cycle)"
            )

        config_data = load_raw_config(config_path)
        storage = resolve_storage_paths(
            config_data=config_data, config_path=config_path
        )
        ensure_storage_dirs(storage)

        watch_dirs_count = len(plan.kwargs["watch_dirs"])
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
        logger.info(f"📝 Worker log file: {plan.kwargs['worker_log_path']}")

        # Start file watcher worker using WorkerManager
        worker_manager = get_worker_manager()
        result = worker_manager.start_file_watcher_worker(**plan.kwargs)

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
