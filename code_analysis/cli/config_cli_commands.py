"""
Schema and validate commands for config CLI.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
import json
import sys
from pathlib import Path

from ..core.config import get_driver_config
from ..core.config_errors import (
    format_validation_error_report,
    print_config_error,
)
from ..core.config_json import ConfigJSONDecodeError, load_config_json
from ..core.config_validator import CodeAnalysisConfigValidator
from ..core.env_loader import load_dotenv_near_config

from .config_cli_helpers import _stop_server


def cmd_schema(args: argparse.Namespace) -> int:
    """
    Apply database schema (tables and indexes) to the configured PostgreSQL database.

    Stops server/workers first unless ``--no-stop`` is given (best-effort; unlike
    the removed SQLite file-lock check, PostgreSQL connections do not block a
    concurrent schema sync the way an open SQLite file handle did).
    """
    config_path = Path(args.file)
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        return 1
    try:
        config = load_config_json(config_path)
        driver_config = get_driver_config(config)
        if not driver_config or driver_config.get("type") != "postgres":
            raise ValueError(
                "Config must contain code_analysis.database.driver with "
                "type='postgres' (SQLite support was removed)"
            )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not args.no_stop:
        if _stop_server(config_path):
            print("Server stopped.", flush=True)
        else:
            print(
                "Warning: could not stop server. If migration fails, run manually:\n"
                "  python -m code_analysis.cli.server_manager_cli --config config.json stop",
                file=sys.stderr,
            )

    from code_analysis.core.database_driver_pkg.drivers.postgres import (
        PostgreSQLDriver,
    )
    from code_analysis.core.database.schema_definition import get_schema_definition

    try:
        print("Connecting...", flush=True)
        driver = PostgreSQLDriver()
        driver.connect(driver_config.get("config", {}))
        print("Applying schema (compare, backup if needed, migrate)...", flush=True)
        schema_definition = get_schema_definition()
        ca = config.get("code_analysis", {}) or {}
        backup_dir = ((ca.get("database") or {}).get("backup_dir")) or str(
            (config_path.parent / "backups").resolve()
        )
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
        try:
            validator.load_config()
        except (ConfigJSONDecodeError, ValueError) as e:
            print_config_error(str(e))
            return 1

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

        print(
            "\n" + format_validation_error_report(results, config_path=config_path),
            file=sys.stderr,
        )
        return 1

    except ConfigJSONDecodeError as e:
        print_config_error(str(e))
        return 1
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Failed to validate configuration: {e}", file=sys.stderr)
        return 1
