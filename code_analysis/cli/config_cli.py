"""
CLI commands for configuration generation and validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import click
import sys
from pathlib import Path
from typing import Optional

from ..core.config_generator import CodeAnalysisConfigGenerator
from ..core.config_validator import CodeAnalysisConfigValidator


@click.group()
def config():
    """Configuration management commands."""
    pass


@config.command()
@click.option(
    "--protocol",
    type=click.Choice(["http", "https", "mtls"]),
    default="mtls",
    help="Server protocol (default: mtls)",
)
@click.option(
    "--out",
    default="config.json",
    help="Output config path (default: config.json)",
)
@click.option("--server-host", help="Server host (default: 127.0.0.1)")
@click.option("--server-port", type=int, help="Server port (default: 15000)")
@click.option("--server-cert-file", help="Server certificate file path")
@click.option("--server-key-file", help="Server key file path")
@click.option("--server-ca-cert-file", help="Server CA certificate file path")
@click.option("--server-log-dir", help="Log directory path (default: ./logs)")
@click.option(
    "--registration-host", help="Registration proxy host (default: localhost)"
)
@click.option(
    "--registration-port", type=int, help="Registration proxy port (default: 3005)"
)
@click.option(
    "--registration-protocol",
    type=click.Choice(["http", "https", "mtls"]),
    help="Registration protocol (default: mtls)",
)
@click.option("--registration-cert-file", help="Registration certificate file path")
@click.option("--registration-key-file", help="Registration key file path")
@click.option("--registration-ca-cert-file", help="Registration CA certificate file path")
@click.option(
    "--registration-server-id",
    help="Server ID for registration (default: code-analysis-server)",
)
@click.option(
    "--registration-server-name",
    help="Server name (default: Code Analysis Server)",
)
@click.option(
    "--instance-uuid",
    help="Server instance UUID (UUID4 format, auto-generated if not provided)",
)
@click.option(
    "--queue-enabled/--queue-disabled",
    default=True,
    help="Enable queue manager (default: True)",
)
@click.option(
    "--queue-in-memory/--queue-persistent",
    default=True,
    help="Use in-memory queue (default: True)",
)
@click.option(
    "--queue-max-concurrent",
    type=int,
    default=5,
    help="Maximum concurrent jobs (default: 5)",
)
@click.option(
    "--queue-retention-seconds",
    type=int,
    default=21600,
    help="Completed job retention in seconds (default: 21600 = 6 hours)",
)
def generate(
    protocol: str,
    out: str,
    server_host: Optional[str],
    server_port: Optional[int],
    server_cert_file: Optional[str],
    server_key_file: Optional[str],
    server_ca_cert_file: Optional[str],
    server_log_dir: Optional[str],
    registration_host: Optional[str],
    registration_port: Optional[int],
    registration_protocol: Optional[str],
    registration_cert_file: Optional[str],
    registration_key_file: Optional[str],
    registration_ca_cert_file: Optional[str],
    registration_server_id: Optional[str],
    registration_server_name: Optional[str],
    instance_uuid: Optional[str],
    queue_enabled: bool,
    queue_in_memory: bool,
    queue_max_concurrent: int,
    queue_retention_seconds: int,
) -> None:
    """Generate configuration file for code-analysis-server."""
    try:
        generator = CodeAnalysisConfigGenerator()
        config_path = generator.generate(
            protocol=protocol,
            out_path=out,
            server_host=server_host,
            server_port=server_port,
            server_cert_file=server_cert_file,
            server_key_file=server_key_file,
            server_ca_cert_file=server_ca_cert_file,
            server_log_dir=server_log_dir,
            registration_host=registration_host,
            registration_port=registration_port,
            registration_protocol=registration_protocol,
            registration_cert_file=registration_cert_file,
            registration_key_file=registration_key_file,
            registration_ca_cert_file=registration_ca_cert_file,
            registration_server_id=registration_server_id,
            registration_server_name=registration_server_name,
            instance_uuid=instance_uuid,
            queue_enabled=queue_enabled,
            queue_in_memory=queue_in_memory,
            queue_max_concurrent=queue_max_concurrent,
            queue_retention_seconds=queue_retention_seconds,
        )
        click.echo(f"✅ Configuration generated: {config_path}")
    except Exception as e:
        click.echo(f"❌ Error generating configuration: {e}", err=True)
        sys.exit(1)


@config.command()
@click.argument("config_file", type=click.Path(exists=True, path_type=Path))
def validate(config_file: Path) -> None:
    """Validate configuration file."""
    try:
        validator = CodeAnalysisConfigValidator()
        is_valid, error_message, config_data = validator.validate_file(str(config_file))

        if is_valid:
            summary = validator.get_validation_summary()
            warnings = [
                r for r in validator.validation_results if r.level == "warning"
            ]
            if warnings:
                click.echo("✅ Validation passed with warnings:")
                for warn in warnings:
                    section_info = (
                        f" ({warn.section}" + (f".{warn.key}" if warn.key else "") + ")"
                        if warn.section
                        else ""
                    )
                    click.echo(f"   ⚠️  {warn.message}{section_info}")
            else:
                click.echo("✅ Validation OK")
        else:
            click.echo("❌ Validation failed:")
            errors = [
                r for r in validator.validation_results if r.level == "error"
            ]
            for err in errors:
                section_info = (
                    f" ({err.section}" + (f".{err.key}" if err.key else "") + ")"
                    if err.section
                    else ""
                )
                click.echo(f"   - {err.message}{section_info}")
            warnings = [
                r for r in validator.validation_results if r.level == "warning"
            ]
            if warnings:
                click.echo("\n⚠️  Warnings:")
                for warn in warnings:
                    section_info = (
                        f" ({warn.section}" + (f".{warn.key}" if warn.key else "") + ")"
                        if warn.section
                        else ""
                    )
                    click.echo(f"   - {warn.message}{section_info}")
            sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error validating configuration: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    config()
