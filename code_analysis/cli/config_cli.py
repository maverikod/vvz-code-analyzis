"""
CLI interface for configuration generator and validator.

Based on mcp-proxy-adapter CLI with code_analysis specific extensions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.config_generator import CodeAnalysisConfigGenerator
from ..core.config_validator import CodeAnalysisConfigValidator
from ..core.database import CodeDatabase


def _indexing_worker_enabled(args: argparse.Namespace) -> Optional[bool]:
    """Resolve indexing worker enabled from CLI (None = do not override)."""
    if hasattr(args, "indexing_worker_disabled") and args.indexing_worker_disabled:
        return False
    if hasattr(args, "indexing_worker_enabled") and args.indexing_worker_enabled:
        return True
    return None


def _file_watcher_enabled(args: argparse.Namespace) -> Optional[bool]:
    """Resolve file watcher enabled from CLI (None = do not override)."""
    if hasattr(args, "file_watcher_disabled") and args.file_watcher_disabled:
        return False
    if hasattr(args, "file_watcher_enabled") and args.file_watcher_enabled:
        return True
    return None


def _get_db_path_from_config(config: Dict[str, Any]) -> Path:
    """Get database path from code_analysis config."""
    ca = config.get("code_analysis", {})
    path = ca.get("db_path") or (ca.get("database", {}) or {}).get("driver", {}).get("config", {}).get("path")
    if not path:
        raise ValueError(
            "Config must contain code_analysis.db_path or code_analysis.database.driver.config.path"
        )
    return Path(path).resolve()


def _db_open_by_other_processes(db_path: Path) -> bool:
    """Return True if the database file is open by other process(es)."""
    try:
        out = subprocess.run(
            ["lsof", str(db_path)],
            capture_output=True,
            timeout=5,
            text=True,
        )
        if out.returncode != 0:
            return False
        lines = [l for l in (out.stdout or "").strip().splitlines() if l]
        return len(lines) > 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _stop_server(config_path: Path) -> bool:
    """Stop code-analysis server and workers. Return True if stopped or already stopped."""
    try:
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "code_analysis.cli.server_manager_cli",
                "--config",
                str(config_path),
                "stop",
            ],
            capture_output=True,
            timeout=30,
            text=True,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False


def cmd_schema(args: argparse.Namespace) -> int:
    """
    Apply database schema (tables and indexes) to the configured database.

    Stops server/workers first if database is in use, then runs migration.
    Uses direct SQLite driver; no database worker required.
    """
    config_path = Path(args.file)
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        return 1
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        db_path = _get_db_path_from_config(config)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not args.no_stop and _db_open_by_other_processes(db_path):
        print("Database is in use. Stopping server and workers...", flush=True)
        if _stop_server(config_path):
            print("Server stopped.", flush=True)
        else:
            print(
                "Warning: could not stop server. If migration fails, run manually:\n"
                "  python -m code_analysis.cli.server_manager_cli --config config.json stop",
                file=sys.stderr,
            )

    os.environ["CODE_ANALYSIS_DB_DRIVER"] = "1"
    driver_config = {
        "type": "sqlite",
        "config": {"path": str(db_path)},
    }
    try:
        print("Connecting...", flush=True)
        db = CodeDatabase(driver_config)
        print("Applying schema (compare, backup if needed, migrate)...", flush=True)
        result = db.sync_schema()
        db.close()
        n = len(result.get("changes_applied") or [])
        if result.get("backup_uuid"):
            print(f"Backup: {result['backup_uuid']}", flush=True)
        print(f"Schema applied. Changes: {n}", flush=True)
        return 0
    except Exception as e:
        print(f"Schema apply failed: {e}", file=sys.stderr)
        return 1


def cmd_generate(args: argparse.Namespace) -> int:
    """
    Generate configuration file.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 on success, 1 on error).
    """
    try:
        generator = CodeAnalysisConfigGenerator()

        # Generate configuration
        config_path = generator.generate(
            protocol=args.protocol,
            with_proxy=args.with_proxy if hasattr(args, "with_proxy") else False,
            out_path=args.out,
            # Server parameters
            server_host=args.server_host,
            server_port=args.server_port,
            server_cert_file=args.server_cert_file,
            server_key_file=args.server_key_file,
            server_ca_cert_file=args.server_ca_cert_file,
            server_crl_file=args.server_crl_file,
            server_debug=args.server_debug if hasattr(args, "server_debug") else None,
            server_log_level=(
                args.server_log_level if hasattr(args, "server_log_level") else None
            ),
            server_log_dir=args.server_log_dir,
            # Registration parameters
            registration_host=args.registration_host,
            registration_port=args.registration_port,
            registration_protocol=args.registration_protocol,
            registration_cert_file=args.registration_cert_file,
            registration_key_file=args.registration_key_file,
            registration_ca_cert_file=args.registration_ca_cert_file,
            registration_crl_file=args.registration_crl_file,
            registration_server_id=args.registration_server_id,
            registration_server_name=args.registration_server_name,
            instance_uuid=args.instance_uuid,
            # Queue manager parameters
            queue_enabled=(
                args.queue_enabled if hasattr(args, "queue_enabled") else None
            ),
            queue_in_memory=(
                args.queue_in_memory if hasattr(args, "queue_in_memory") else None
            ),
            queue_max_concurrent=(
                args.queue_max_concurrent
                if hasattr(args, "queue_max_concurrent")
                else None
            ),
            queue_retention_seconds=(
                args.queue_retention_seconds
                if hasattr(args, "queue_retention_seconds")
                else None
            ),
            # Code analysis specific parameters
            code_analysis_db_path=(
                args.code_analysis_db_path
                if hasattr(args, "code_analysis_db_path")
                else None
            ),
            code_analysis_driver_type=(
                args.code_analysis_driver_type
                if hasattr(args, "code_analysis_driver_type")
                else None
            ),
            code_analysis_driver_path=(
                args.code_analysis_driver_path
                if hasattr(args, "code_analysis_driver_path")
                else None
            ),
            code_analysis_log=(
                args.code_analysis_log if hasattr(args, "code_analysis_log") else None
            ),
            code_analysis_faiss_index_path=(
                args.code_analysis_faiss_index_path
                if hasattr(args, "code_analysis_faiss_index_path")
                else None
            ),
            code_analysis_vector_dim=(
                args.code_analysis_vector_dim
                if hasattr(args, "code_analysis_vector_dim")
                else None
            ),
            code_analysis_min_chunk_length=(
                args.code_analysis_min_chunk_length
                if hasattr(args, "code_analysis_min_chunk_length")
                else None
            ),
            code_analysis_retry_attempts=(
                args.code_analysis_retry_attempts
                if hasattr(args, "code_analysis_retry_attempts")
                else None
            ),
            code_analysis_retry_delay=(
                args.code_analysis_retry_delay
                if hasattr(args, "code_analysis_retry_delay")
                else None
            ),
            indexing_worker_enabled=_indexing_worker_enabled(args),
            indexing_worker_poll_interval=(
                args.indexing_worker_poll_interval
                if hasattr(args, "indexing_worker_poll_interval")
                else None
            ),
            indexing_worker_batch_size=(
                args.indexing_worker_batch_size
                if hasattr(args, "indexing_worker_batch_size")
                else None
            ),
            indexing_worker_log_path=(
                args.indexing_worker_log_path
                if hasattr(args, "indexing_worker_log_path")
                else None
            ),
            file_watcher_enabled=_file_watcher_enabled(args),
            file_watcher_scan_interval=(
                args.file_watcher_scan_interval
                if hasattr(args, "file_watcher_scan_interval")
                else None
            ),
            file_watcher_log_path=(
                args.file_watcher_log_path
                if hasattr(args, "file_watcher_log_path")
                else None
            ),
            file_watcher_version_dir=(
                args.file_watcher_version_dir
                if hasattr(args, "file_watcher_version_dir")
                else None
            ),
        )

        print(f"✅ Configuration generated: {config_path}")

        # Validate generated configuration
        print("🔍 Validating generated configuration...")
        validator = CodeAnalysisConfigValidator(str(config_path))
        validator.load_config()
        results = validator.validate_config()
        summary = validator.get_validation_summary()

        if summary["is_valid"]:
            print("✅ Configuration is valid")
            return 0
        else:
            print("⚠️  Configuration has validation issues:")
            for result in results:
                level_icon = "❌" if result.level == "error" else "⚠️"
                print(f"  {level_icon} {result.message}")
                if result.suggestion:
                    print(f"     Suggestion: {result.suggestion}")

            # Return error if there are critical errors
            if summary["errors"] > 0:
                print(f"\n❌ Validation failed: {summary['errors']} error(s)")
                return 1
            else:
                print(
                    f"\n⚠️  Validation completed with {summary['warnings']} warning(s)"
                )
                return 0

    except Exception as e:
        print(f"❌ Failed to generate configuration: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def cmd_validate(args: argparse.Namespace) -> int:
    """
    Validate configuration file.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 on success, 1 on error).
    """
    try:
        config_path = Path(args.file)
        if not config_path.exists():
            print(f"❌ Configuration file not found: {config_path}", file=sys.stderr)
            return 1

        validator = CodeAnalysisConfigValidator(str(config_path))
        validator.load_config()
        results = validator.validate_config()
        summary = validator.get_validation_summary()

        print(f"📋 Validation results for: {config_path}")
        print(f"   Total issues: {summary['total_issues']}")
        print(f"   Errors: {summary['errors']}")
        print(f"   Warnings: {summary['warnings']}")
        print(f"   Info: {summary['info']}")

        if results:
            print("\n📝 Details:")
            for result in results:
                level_icon = "❌" if result.level == "error" else "⚠️"
                section_key = (
                    f"{result.section}.{result.key}" if result.key else result.section
                )
                print(f"  {level_icon} [{section_key}] {result.message}")
                if result.suggestion:
                    print(f"     💡 {result.suggestion}")

        if summary["is_valid"]:
            print("\n✅ Configuration is valid")
            return 0
        else:
            print(f"\n❌ Configuration is invalid: {summary['errors']} error(s)")
            return 1

    except Exception as e:
        print(f"❌ Failed to validate configuration: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def main(argv: Optional[list[str]] = None) -> int:
    """
    Main CLI entry point.

    Args:
        argv: Optional command line arguments (for testing).

    Returns:
        Exit code.
    """
    parser = argparse.ArgumentParser(
        description="Configuration generator and validator for code-analysis-server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    subparsers.required = True

    # Generate command
    gen_parser = subparsers.add_parser(
        "generate", help="Generate configuration file", aliases=["gen"]
    )
    gen_parser.add_argument(
        "--protocol",
        type=str,
        choices=["http", "https", "mtls"],
        required=True,
        help="Server/proxy protocol",
    )
    gen_parser.add_argument(
        "--out",
        type=str,
        default="config.json",
        help="Output config path (default: config.json)",
    )
    gen_parser.add_argument(
        "--with-proxy",
        action="store_true",
        help="Enable proxy registration",
    )

    # Server parameters
    gen_parser.add_argument(
        "--server-host", type=str, help="Server host (default: 0.0.0.0)"
    )
    gen_parser.add_argument(
        "--server-port", type=int, help="Server port (default: 8080)"
    )
    gen_parser.add_argument(
        "--server-cert-file", type=str, help="Server certificate file path"
    )
    gen_parser.add_argument("--server-key-file", type=str, help="Server key file path")
    gen_parser.add_argument(
        "--server-ca-cert-file",
        type=str,
        help="Server CA certificate file path (required for mTLS protocol)",
    )
    gen_parser.add_argument("--server-crl-file", type=str, help="Server CRL file path")
    gen_parser.add_argument(
        "--server-debug", action="store_true", help="Enable debug mode (default: False)"
    )
    gen_parser.add_argument(
        "--server-log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Log level (default: INFO)",
    )
    gen_parser.add_argument(
        "--server-log-dir",
        type=str,
        help="Log directory path (default: ./logs)",
    )

    # Registration parameters
    gen_parser.add_argument(
        "--registration-host",
        type=str,
        help="Registration proxy host (default: localhost)",
    )
    gen_parser.add_argument(
        "--registration-port",
        type=int,
        help="Registration proxy port (default: 3005)",
    )
    gen_parser.add_argument(
        "--registration-protocol",
        type=str,
        choices=["http", "https", "mtls"],
        help="Registration protocol",
    )
    gen_parser.add_argument(
        "--registration-cert-file",
        type=str,
        help="Registration certificate file path",
    )
    gen_parser.add_argument(
        "--registration-key-file",
        type=str,
        help="Registration key file path",
    )
    gen_parser.add_argument(
        "--registration-ca-cert-file",
        type=str,
        help="Registration CA certificate file path",
    )
    gen_parser.add_argument(
        "--registration-crl-file",
        type=str,
        help="Registration CRL file path",
    )
    gen_parser.add_argument(
        "--registration-server-id",
        type=str,
        help="Server ID for registration",
    )
    gen_parser.add_argument(
        "--registration-server-name",
        type=str,
        help="Server name for registration",
    )
    gen_parser.add_argument(
        "--instance-uuid",
        type=str,
        help="Server instance UUID (UUID4 format, auto-generated if not provided)",
    )

    # Queue manager parameters
    gen_parser.add_argument(
        "--queue-enabled",
        action="store_true",
        help="Enable queue manager (default: True)",
    )
    gen_parser.add_argument(
        "--queue-disabled",
        action="store_true",
        help="Disable queue manager",
    )
    gen_parser.add_argument(
        "--queue-in-memory",
        action="store_true",
        help="Use in-memory queue (default: True)",
    )
    gen_parser.add_argument(
        "--queue-persistent",
        action="store_true",
        help="Use persistent queue (not in-memory)",
    )
    gen_parser.add_argument(
        "--queue-max-concurrent",
        type=int,
        help="Maximum concurrent jobs (default: 10)",
    )
    gen_parser.add_argument(
        "--queue-retention-seconds",
        type=int,
        help="Completed job retention in seconds (default: 21600)",
    )

    # Code analysis specific parameters
    gen_parser.add_argument(
        "--code-analysis-db-path",
        type=str,
        help="Database path for code_analysis section (default: data/code_analysis.db)",
    )
    gen_parser.add_argument(
        "--code-analysis-driver-type",
        type=str,
        choices=["sqlite", "sqlite_proxy", "postgres", "mysql"],
        help="Database driver type (default: sqlite_proxy)",
    )
    gen_parser.add_argument(
        "--code-analysis-driver-path",
        type=str,
        help="Database path for driver config (default: same as --code-analysis-db-path)",
    )
    gen_parser.add_argument(
        "--code-analysis-log",
        type=str,
        help="Code analysis log file path (default: logs/code_analysis.log)",
    )
    gen_parser.add_argument(
        "--code-analysis-faiss-index-path",
        type=str,
        help="FAISS index file path (default: data/faiss_index.bin)",
    )
    gen_parser.add_argument(
        "--code-analysis-vector-dim",
        type=int,
        help="Vector dimension for embeddings (default: 384)",
    )
    gen_parser.add_argument(
        "--code-analysis-min-chunk-length",
        type=int,
        help="Minimum chunk length (default: 30)",
    )
    gen_parser.add_argument(
        "--code-analysis-retry-attempts",
        type=int,
        help="Vectorization retry attempts (default: 3)",
    )
    gen_parser.add_argument(
        "--code-analysis-retry-delay",
        type=float,
        help="Vectorization retry delay in seconds (default: 1.0)",
    )
    gen_parser.add_argument(
        "--indexing-worker-enabled",
        action="store_true",
        help="Enable indexing worker (default: True)",
    )
    gen_parser.add_argument(
        "--indexing-worker-disabled",
        action="store_true",
        help="Disable indexing worker",
    )
    gen_parser.add_argument(
        "--indexing-worker-poll-interval",
        type=int,
        help="Indexing worker poll interval in seconds (default: 30)",
    )
    gen_parser.add_argument(
        "--indexing-worker-batch-size",
        type=int,
        help="Indexing worker batch size (default: 5)",
    )
    gen_parser.add_argument(
        "--indexing-worker-log-path",
        type=str,
        help="Indexing worker log path (default: logs/indexing_worker.log)",
    )
    gen_parser.add_argument(
        "--file-watcher-enabled",
        action="store_true",
        help="Enable file watcher (default: True)",
    )
    gen_parser.add_argument(
        "--file-watcher-disabled",
        action="store_true",
        help="Disable file watcher",
    )
    gen_parser.add_argument(
        "--file-watcher-scan-interval",
        type=int,
        help="File watcher scan interval in seconds (default: 60)",
    )
    gen_parser.add_argument(
        "--file-watcher-log-path",
        type=str,
        help="File watcher log path (default: logs/file_watcher.log)",
    )
    gen_parser.add_argument(
        "--file-watcher-version-dir",
        type=str,
        help="File watcher version directory (default: data/versions)",
    )

    gen_parser.set_defaults(func=cmd_generate)

    # Validate command
    val_parser = subparsers.add_parser(
        "validate", help="Validate configuration file", aliases=["val"]
    )
    val_parser.add_argument(
        "--file",
        type=str,
        required=True,
        help="Path to configuration file",
    )
    val_parser.set_defaults(func=cmd_validate)

    # Schema command: apply database schema (tables and indexes)
    schema_parser = subparsers.add_parser(
        "schema",
        help="Apply database schema (create tables and indexes). Run once for new DB or after schema changes.",
    )
    schema_parser.add_argument(
        "--file",
        type=str,
        default="config.json",
        help="Path to config file (default: config.json)",
    )
    schema_parser.add_argument(
        "--no-stop",
        action="store_true",
        help="Do not stop server/workers when DB is in use (migration may fail with 'database is locked')",
    )
    schema_parser.set_defaults(func=cmd_schema)

    args = parser.parse_args(argv)

    # Handle queue flags
    if hasattr(args, "queue_enabled") and hasattr(args, "queue_disabled"):
        if args.queue_disabled:
            args.queue_enabled = False
        elif args.queue_enabled:
            args.queue_enabled = True
        else:
            args.queue_enabled = True  # default

    if hasattr(args, "queue_in_memory") and hasattr(args, "queue_persistent"):
        if args.queue_persistent:
            args.queue_in_memory = False
        elif args.queue_in_memory:
            args.queue_in_memory = True
        else:
            args.queue_in_memory = True  # default

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
