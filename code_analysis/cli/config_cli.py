"""
CLI interface for configuration generator and validator.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from ..core.config_generator import CodeAnalysisConfigGenerator
from ..core.config_validator import CodeAnalysisConfigValidator


def _parse_bool(value: str) -> bool:
    """Parse boolean value from string."""
    if value.lower() in ("true", "1", "yes", "on"):
        return True
    if value.lower() in ("false", "0", "no", "off"):
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def _parse_optional_int(value: str) -> Optional[int]:
    """Parse optional integer value from string."""
    if not value or value.lower() == "none":
        return None
    return int(value)


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

        # Parse boolean arguments
        queue_enabled = _parse_bool(args.queue_enabled) if args.queue_enabled else True
        queue_in_memory = (
            _parse_bool(args.queue_in_memory) if args.queue_in_memory else True
        )

        # Parse optional integer arguments
        server_port = (
            _parse_optional_int(args.server_port) if args.server_port else None
        )
        registration_port = (
            _parse_optional_int(args.registration_port)
            if args.registration_port
            else None
        )
        queue_max_concurrent = (
            int(args.queue_max_concurrent) if args.queue_max_concurrent else 5
        )
        queue_retention_seconds = (
            int(args.queue_retention_seconds) if args.queue_retention_seconds else 21600
        )

        # Generate configuration
        config_path = generator.generate(
            protocol=args.protocol or "mtls",
            out_path=args.out or "config.json",
            # Server parameters
            server_host=args.server_host,
            server_port=server_port,
            server_cert_file=args.server_cert_file,
            server_key_file=args.server_key_file,
            server_ca_cert_file=args.server_ca_cert_file,
            server_log_dir=args.server_log_dir,
            # Registration parameters
            registration_host=args.registration_host,
            registration_port=registration_port,
            registration_protocol=args.registration_protocol,
            registration_cert_file=args.registration_cert_file,
            registration_key_file=args.registration_key_file,
            registration_ca_cert_file=args.registration_ca_cert_file,
            registration_server_id=args.registration_server_id,
            registration_server_name=args.registration_server_name,
            instance_uuid=args.instance_uuid,
            # Queue manager parameters
            queue_enabled=queue_enabled,
            queue_in_memory=queue_in_memory,
            queue_max_concurrent=queue_max_concurrent,
            queue_retention_seconds=queue_retention_seconds,
        )

        print(f"✅ Configuration generated: {config_path}")

        # Validate generated configuration
        print("🔍 Validating generated configuration...")
        validator = CodeAnalysisConfigValidator(config_path)
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
                print(f"\n⚠️  Validation completed with {summary['warnings']} warning(s)")
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
        config_path = Path(args.config_path)
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
    gen_parser = subparsers.add_parser("generate", help="Generate configuration file")
    gen_parser.add_argument(
        "--out",
        type=str,
        default="config.json",
        help="Output file path (default: config.json)",
    )
    gen_parser.add_argument(
        "--protocol",
        type=str,
        choices=["http", "https", "mtls"],
        default="mtls",
        help="Server protocol (default: mtls)",
    )

    # Server parameters
    gen_parser.add_argument("--server-host", type=str, help="Server host")
    gen_parser.add_argument(
        "--server-port", type=str, help="Server port (integer or 'none')"
    )
    gen_parser.add_argument("--server-cert-file", type=str, help="Server certificate file")
    gen_parser.add_argument("--server-key-file", type=str, help="Server key file")
    gen_parser.add_argument(
        "--server-ca-cert-file", type=str, help="Server CA certificate file"
    )
    gen_parser.add_argument("--server-log-dir", type=str, help="Server log directory")

    # Registration parameters
    gen_parser.add_argument(
        "--registration-host", type=str, help="Registration proxy host"
    )
    gen_parser.add_argument(
        "--registration-port",
        type=str,
        help="Registration proxy port (integer or 'none')",
    )
    gen_parser.add_argument(
        "--registration-protocol",
        type=str,
        choices=["http", "https", "mtls"],
        help="Registration protocol",
    )
    gen_parser.add_argument(
        "--registration-cert-file", type=str, help="Registration certificate file"
    )
    gen_parser.add_argument(
        "--registration-key-file", type=str, help="Registration key file"
    )
    gen_parser.add_argument(
        "--registration-ca-cert-file", type=str, help="Registration CA certificate file"
    )
    gen_parser.add_argument(
        "--registration-server-id", type=str, help="Server ID for registration"
    )
    gen_parser.add_argument(
        "--registration-server-name", type=str, help="Server name"
    )
    gen_parser.add_argument(
        "--instance-uuid", type=str, help="Server instance UUID (UUID4)"
    )

    # Queue manager parameters
    gen_parser.add_argument(
        "--queue-enabled",
        type=str,
        help="Enable queue manager (true/false, default: true)",
    )
    gen_parser.add_argument(
        "--queue-in-memory",
        type=str,
        help="Use in-memory queue (true/false, default: true)",
    )
    gen_parser.add_argument(
        "--queue-max-concurrent",
        type=int,
        help="Maximum concurrent jobs (default: 5)",
    )
    gen_parser.add_argument(
        "--queue-retention-seconds",
        type=int,
        help="Completed job retention in seconds (default: 21600)",
    )

    gen_parser.set_defaults(func=cmd_generate)

    # Validate command
    val_parser = subparsers.add_parser("validate", help="Validate configuration file")
    val_parser.add_argument(
        "config_path", type=str, help="Path to configuration file"
    )
    val_parser.set_defaults(func=cmd_validate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

