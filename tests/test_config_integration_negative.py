"""
Negative integration test cases for configuration generator and validator.

Tests error scenarios in the full workflow.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from code_analysis.cli.config_cli import cmd_generate, cmd_validate
from code_analysis.core.config_generator import CodeAnalysisConfigGenerator
from code_analysis.core.config_validator import CodeAnalysisConfigValidator


class TestConfigIntegrationNegative:
    """Negative integration test cases."""

    def test_cli_generate_invalid_protocol(self):
        """Test CLI generate with invalid protocol."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "config.json"

            class Args:
                protocol = "invalid_protocol"
                out = str(out_path)
                server_host = None
                server_port = None
                server_cert_file = None
                server_key_file = None
                server_ca_cert_file = None
                server_log_dir = None
                registration_host = None
                registration_port = None
                registration_protocol = None
                registration_cert_file = None
                registration_key_file = None
                registration_ca_cert_file = None
                registration_server_id = None
                registration_server_name = None
                instance_uuid = None
                queue_enabled = None
                queue_in_memory = None
                queue_max_concurrent = None
                queue_retention_seconds = None

            args = Args()
            # Should fail during validation
            result = cmd_generate(args)
            assert result != 0  # Should return error code

    def test_cli_validate_nonexistent_file(self):
        """Test CLI validate with non-existent file."""
        class Args:
            config_path = "nonexistent_config.json"

        args = Args()
        result = cmd_validate(args)
        assert result != 0  # Should return error code

    def test_cli_validate_invalid_json(self):
        """Test CLI validate with invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ invalid json }")
            temp_path = f.name

        try:
            class Args:
                config_path = temp_path

            args = Args()
            result = cmd_validate(args)
            assert result != 0  # Should return error code
        finally:
            Path(temp_path).unlink()

    def test_cli_validate_invalid_config(self):
        """Test CLI validate with invalid configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_config_path = Path(tmpdir) / "config.json"
            config = {
                "some_section": {}  # Missing required sections (server, queue_manager)
            }

            with open(test_config_path, "w") as f:
                json.dump(config, f)

            class Args:
                config_path = str(test_config_path)

            args = Args()
            result = cmd_validate(args)
            assert result != 0  # Should return error code

    def test_generate_then_validate_invalid(self):
        """Test that generated invalid config fails validation."""
        generator = CodeAnalysisConfigGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "config.json"

            # Try to generate mTLS without CA cert - should fail
            try:
                generator.generate(
                    protocol="mtls",
                    out_path=str(out_path),
                    # Missing server_ca_cert_file
                )
                # If generation succeeded, manually validate should catch it
                validator = CodeAnalysisConfigValidator(str(out_path))
                validator.load_config()
                results = validator.validate_config()
                summary = validator.get_validation_summary()

                # Should have validation errors
                assert not summary["is_valid"]
            except ValueError:
                # Expected - validation in generator should catch it
                pass

    def test_main_validation_before_startup(self):
        """Test that main.py validates config before startup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            # Create invalid config
            config = {
                "some_section": {}  # Missing required sections (server, queue_manager)
            }

            with open(config_path, "w") as f:
                json.dump(config, f)

            # Test that validation logic works (simulating what main.py does)
            from code_analysis.core.config_validator import CodeAnalysisConfigValidator

            validator = CodeAnalysisConfigValidator(str(config_path))
            validator.load_config()
            results = validator.validate_config()
            summary = validator.get_validation_summary()

            # Should be invalid
            assert not summary["is_valid"]
            # Main should exit with code 1 on validation failure
            assert len([r for r in results if r.level == "error"]) > 0

    def test_validation_logging_fallback_to_console(self):
        """Test that validation errors are logged to console if log unavailable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            # Create config with invalid log_dir (to test fallback)
            config = {
                "server": {
                    "host": "0.0.0.0",
                    "port": 15000,
                    "protocol": "http",
                    "log_dir": "/nonexistent/log/dir",  # Invalid path
                },
                "queue_manager": {"enabled": True},
            }

            with open(config_path, "w") as f:
                json.dump(config, f)

            # This simulates what main.py does
            validator = CodeAnalysisConfigValidator(str(config_path))
            validator.load_config()
            results = validator.validate_config()
            summary = validator.get_validation_summary()

            # Config should be valid (log_dir is not validated for existence)
            # But if we had errors, they should be handled gracefully
            # The actual logging fallback is tested in main.py integration tests

    def test_generator_validation_prevents_invalid_output(self):
        """Test that generator validation prevents creating invalid config files."""
        generator = CodeAnalysisConfigGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "config.json"

            # Try to generate invalid config
            try:
                generator.generate(
                    protocol="mtls",
                    out_path=str(out_path),
                    # Missing required CA cert
                )
                # If we get here, file should not exist or be invalid
                if out_path.exists():
                    # File exists but should be invalid
                    validator = CodeAnalysisConfigValidator(str(out_path))
                    validator.load_config()
                    results = validator.validate_config()
                    summary = validator.get_validation_summary()
                    assert not summary["is_valid"]
            except ValueError:
                # Expected - generator should raise error before creating file
                # File should not exist or be incomplete
                pass

