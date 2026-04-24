"""
Generate command for config CLI.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
import sys
import traceback
from typing import Any

from ..core.config_generator import CodeAnalysisConfigGenerator
from ..core.config_validator import CodeAnalysisConfigValidator

from .config_cli_helpers import _file_watcher_enabled, _indexing_worker_enabled


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

        config_path = generator.generate(
            protocol=args.protocol,
            with_proxy=args.with_proxy if hasattr(args, "with_proxy") else False,
            out_path=args.out,
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
            code_analysis_pg_host=(
                args.code_analysis_pg_host
                if hasattr(args, "code_analysis_pg_host")
                else None
            ),
            code_analysis_pg_port=(
                args.code_analysis_pg_port
                if hasattr(args, "code_analysis_pg_port")
                else None
            ),
            code_analysis_pg_dbname=(
                args.code_analysis_pg_dbname
                if hasattr(args, "code_analysis_pg_dbname")
                else None
            ),
            code_analysis_pg_user=(
                args.code_analysis_pg_user
                if hasattr(args, "code_analysis_pg_user")
                else None
            ),
            code_analysis_pg_password_env=(
                args.code_analysis_pg_password_env
                if hasattr(args, "code_analysis_pg_password_env")
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
            allow_line_commands_on_healthy_files=(
                True
                if getattr(args, "allow_line_commands_on_healthy_files", False)
                else None
            ),
        )

        print(f"✅ Configuration generated: {config_path}")

        print("🔍 Validating generated configuration...")
        validator = CodeAnalysisConfigValidator(str(config_path))
        validator.load_config()
        results = validator.validate_config()
        summary = validator.get_validation_summary()

        if summary["is_valid"]:
            print("✅ Configuration is valid")
            return 0
        print("⚠️  Configuration has validation issues:")
        for result in results:
            level_icon = "❌" if result.level == "error" else "⚠️"
            print(f"  {level_icon} {result.message}")
            if result.suggestion:
                print(f"     Suggestion: {result.suggestion}")
        if summary["errors"] > 0:
            print(f"\n❌ Validation failed: {summary['errors']} error(s)")
            return 1
        print(f"\n⚠️  Validation completed with {summary['warnings']} warning(s)")
        return 0

    except Exception as e:
        print(f"❌ Failed to generate configuration: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1
