"""
Main entry point for code-analysis-server using mcp-proxy-adapter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
import sys
from pathlib import Path

from mcp_proxy_adapter.api.core.app_factory import AppFactory
from mcp_proxy_adapter.core.config.simple_config import SimpleConfig
from mcp_proxy_adapter.core.server_engine import ServerEngineFactory

# Import hooks to register commands
from . import hooks  # noqa: F401


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
        "--host",
        help="Server host (overrides config)",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Server port (overrides config)",
    )
    args = parser.parse_args()

    # Load configuration
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"❌ Configuration file not found: {config_path}", file=sys.stderr)
        print(f"   Generate one with: python -m code_analysis.cli.config_cli generate", file=sys.stderr)
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
    
    # Update global configuration instance used by adapter internals
    from mcp_proxy_adapter.config import get_config
    cfg = get_config()
    cfg.config_path = str(config_path)
    setattr(cfg, "model", model)
    cfg.config_data = app_config
    if hasattr(cfg, "feature_manager"):
        cfg.feature_manager.config_data = cfg.config_data

    # Create FastAPI app using AppFactory
    app_factory = AppFactory()
    app = app_factory.create_app(
        title="Code Analysis Server",
        description="Code analysis tool for Python projects. Provides code mapping, "
        "issue detection, usage analysis, semantic search, and refactoring capabilities.",
        version="1.0.0",
        app_config=app_config,
        config_path=str(config_path),
    )

    # Commands are automatically registered via hooks
    # Queue manager is automatically initialized if enabled in config
    
    # Start vectorization worker on startup
    # Note: on_event("startup") is deprecated, so we'll call this from lifespan
    async def startup_vectorization_worker():
        """Start vectorization worker in background process on server startup."""
        import multiprocessing
        import asyncio
        from pathlib import Path
        from code_analysis.core.vectorization_worker import run_vectorization_worker
        from code_analysis.core.config import ServerConfig
        from code_analysis.core.faiss_manager import FaissIndexManager
        
        import logging
        logger = logging.getLogger(__name__)
        print("🔍 startup_vectorization_worker called", flush=True)
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
            
            print(f"🔍 app_config loaded: {bool(app_config)}, keys: {list(app_config.keys()) if app_config else []}", flush=True)
            logger.info(f"🔍 app_config loaded: {bool(app_config)}, keys: {list(app_config.keys()) if app_config else []}")
            
            # Check if code_analysis config section exists
            code_analysis_config = app_config.get("code_analysis", {})
            print(f"🔍 code_analysis_config found: {bool(code_analysis_config)}", flush=True)
            logger.info(f"🔍 code_analysis_config found: {bool(code_analysis_config)}")
            if not code_analysis_config:
                print("⚠️  No code_analysis config found, skipping vectorization worker", flush=True)
                logger.warning("⚠️  No code_analysis config found, skipping vectorization worker")
                return
            
            # Check if SVO chunker is configured
            server_config = ServerConfig(**code_analysis_config)
            if not server_config.chunker:
                print("⚠️  No chunker config found, skipping vectorization worker", flush=True)
                logger.warning("⚠️  No chunker config found, skipping vectorization worker")
                return
            
            # Check if worker is enabled
            worker_config = server_config.worker
            if worker_config and isinstance(worker_config, dict):
                if not worker_config.get("enabled", True):
                    print("ℹ️  Vectorization worker is disabled in config, skipping", flush=True)
                    logger.info("ℹ️  Vectorization worker is disabled in config, skipping")
                    return
            
            # Get database path from config or use default
            root_dir = Path.cwd()
            db_path = root_dir / "data" / "code_analysis.db"
            
            # Get project ID (use first project or default)
            try:
                from code_analysis.core.database import CodeDatabase
                database = CodeDatabase(db_path)
                cursor = database.conn.cursor()
                cursor.execute("SELECT id FROM projects ORDER BY created_at LIMIT 1")
                row = cursor.fetchone()
                project_id = row[0] if row else None
                database.close()
                
                if not project_id:
                    logger.warning("⚠️  No projects found in database, skipping vectorization worker")
                    return
            except Exception as e:
                logger.warning(f"⚠️  Failed to get project ID: {e}, skipping vectorization worker")
                return
            
            # Get FAISS index path and vector dimension
            faiss_index_path = root_dir / "data" / "faiss_index"
            vector_dim = server_config.vector_dim or 384  # Default dimension, should match chunker model
            
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
                database = CodeDatabase(db_path)
                try:
                    vectors_count = await faiss_manager.rebuild_from_database(
                        database, svo_client_manager
                    )
                    logger.info(f"✅ FAISS index rebuilt: {vectors_count} vectors loaded from database")
                finally:
                    database.close()
                    await svo_client_manager.close()
                    
            except Exception as e:
                logger.warning(f"⚠️  Failed to rebuild FAISS index: {e}", exc_info=True)
                # Continue anyway - index will be empty but worker can still start
            
            # Prepare SVO config
            svo_config = server_config.model_dump() if hasattr(server_config, 'model_dump') else server_config.dict()
            
            # Start worker in separate process
            print(f"🚀 Starting vectorization worker for project {project_id}", flush=True)
            logger.info(f"🚀 Starting vectorization worker for project {project_id}")
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
                    "batch_size": 10,
                    "poll_interval": 30,  # Poll every 30 seconds
                },
                daemon=True,  # Daemon process will be killed when parent exits
            )
            process.start()
            print(f"✅ Vectorization worker started with PID {process.pid}", flush=True)
            logger.info(f"✅ Vectorization worker started with PID {process.pid}")
            
        except Exception as e:
            print(f"❌ Failed to start vectorization worker: {e}", flush=True, file=sys.stderr)
            logger.error(f"❌ Failed to start vectorization worker: {e}", exc_info=True)
    
    # Call startup function directly in background thread (on_event is deprecated)
    import threading
    import logging
    main_logger = logging.getLogger(__name__)
    
    def run_startup():
        import asyncio
        try:
            print("🔍 Background thread: calling startup_vectorization_worker", flush=True)
            main_logger.info("🔍 Background thread: calling startup_vectorization_worker")
            asyncio.run(startup_vectorization_worker())
        except Exception as e:
            print(f"❌ Failed to start vectorization worker: {e}", flush=True, file=sys.stderr)
            main_logger.error(f"Failed to start vectorization worker: {e}", exc_info=True)
    
    print("🔍 Starting background thread for vectorization worker", flush=True)
    main_logger.info("🔍 Starting background thread for vectorization worker")
    startup_thread = threading.Thread(target=run_startup, daemon=True)
    startup_thread.start()
    print(f"🔍 Background thread started: {startup_thread.is_alive()}", flush=True)
    main_logger.info(f"🔍 Background thread started: {startup_thread.is_alive()}")

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

    # Run server
    engine = ServerEngineFactory.get_engine("hypercorn")
    if not engine:
        print("❌ Hypercorn engine not available", file=sys.stderr)
        sys.exit(1)
    
    engine.run_server(app, server_config)


if __name__ == "__main__":
    main()
