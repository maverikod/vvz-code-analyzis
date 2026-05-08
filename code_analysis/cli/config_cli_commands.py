"""
Schema and validate commands for config CLI.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
import json
import sys
from pathlib import Path

from ..core.config_validator import CodeAnalysisConfigValidator
from ..core.env_loader import load_dotenv_near_config

from .config_cli_helpers import (
    _db_open_by_other_processes,
    _get_db_path_from_config,
    _stop_server,
)


def cmd_schema(args: argparse.Namespace) -> int:
    """
    Apply database schema (tables and indexes) to the configured database.

    Stops server/workers first if database is in use, then runs migration.
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

    from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver
    from code_analysis.core.database.schema_definition import get_schema_definition

    try:
        print("Connecting...", flush=True)
        driver = SQLiteDriver()
        driver.connect({"path": str(db_path)})
        print("Applying schema (compare, backup if needed, migrate)...", flush=True)
        schema_definition = get_schema_definition()
        db_path_obj = Path(str(db_path))
        if db_path_obj.parent.name == "data":
            backup_dir = str(db_path_obj.parent.parent / "backups")
        else:
            backup_dir = str(db_path_obj.parent / "backups")
        result = driver.sync_schema(schema_definition, backup_dir)
        driver.disconnect()
        n = len(result.get("changes_applied") or [])
        if result.get("backup_uuid"):
            print(f"Backup: {result['backup_uuid']}", flush=True)
        print(f"Schema applied. Changes: {n}", flush=True)
        return 0
    except Exception as e:
        print(f"Schema apply failed: {e}", file=sys.stderr)
        return 1


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate configuration file."""
    try:
        config_path = Path(args.file)
        if not config_path.exists():
            print(f"❌ Configuration file not found: {config_path}", file=sys.stderr)
            return 1

        load_dotenv_near_config(config_path)

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
        print(f"\n❌ Configuration is invalid: {summary['errors']} error(s)")
        return 1

    except Exception as e:
        print(f"❌ Failed to validate configuration: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1
