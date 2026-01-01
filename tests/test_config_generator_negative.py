"""
Negative test cases for configuration generator.

Tests all error scenarios and edge cases.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import tempfile
from pathlib import Path

import pytest

from code_analysis.core.config_generator import CodeAnalysisConfigGenerator


class TestConfigGeneratorNegative:
    """Negative test cases for configuration generator."""

    def test_generate_invalid_protocol(self):
        """Test generation with invalid protocol."""
        generator = CodeAnalysisConfigGenerator()

        # Protocol validation happens in validator, but generator should handle it
        # For now, generator accepts any string, validation happens after generation
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "config.json"
            # Generate with invalid protocol - should fail validation
            with pytest.raises(ValueError, match="invalid|protocol"):
                generator.generate(
                    protocol="invalid_protocol",
                    out_path=str(out_path),
                )

    def test_generate_mtls_without_ca_cert(self):
        """Test generation of mTLS config without CA certificate."""
        generator = CodeAnalysisConfigGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "config.json"
            # mTLS requires CA cert - should fail validation
            with pytest.raises(ValueError, match="CA certificate|invalid"):
                generator.generate(
                    protocol="mtls",
                    out_path=str(out_path),
                    # server_ca_cert_file not provided
                )

    def test_generate_invalid_uuid(self):
        """Test generation with invalid UUID format."""
        generator = CodeAnalysisConfigGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "config.json"
            # Invalid UUID format - should fail validation
            with pytest.raises(ValueError, match="UUID|invalid"):
                generator.generate(
                    protocol="http",
                    out_path=str(out_path),
                    instance_uuid="not-a-valid-uuid",
                )

    def test_generate_invalid_uuid_version(self):
        """Test generation with UUID that is not version 4."""
        import uuid

        generator = CodeAnalysisConfigGenerator()

        # Generate UUID v1 (not v4)
        uuid_v1 = str(uuid.uuid1())

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "config.json"
            # UUID v1 instead of v4 - should fail validation
            with pytest.raises(ValueError, match="UUID4|version"):
                generator.generate(
                    protocol="http",
                    out_path=str(out_path),
                    instance_uuid=uuid_v1,
                )

    def test_generate_with_nonexistent_cert_files(self):
        """Test generation with paths to non-existent certificate files."""
        generator = CodeAnalysisConfigGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "config.json"
            # Generate config with non-existent cert files
            # Should generate config, but validation should fail
            with pytest.raises(ValueError, match="not found|file"):
                generator.generate(
                    protocol="mtls",
                    out_path=str(out_path),
                    server_cert_file="nonexistent_cert.pem",
                    server_key_file="nonexistent_key.pem",
                    server_ca_cert_file="nonexistent_ca.pem",
                )

    def test_generate_invalid_output_path(self):
        """Test generation with invalid output path."""
        generator = CodeAnalysisConfigGenerator()

        # Try to write to non-existent directory
        invalid_path = "/nonexistent/directory/config.json"

        # Should fail when trying to create parent directory or write file
        with pytest.raises((OSError, PermissionError, ValueError)):
            generator.generate(
                protocol="http",
                out_path=invalid_path,
            )

    def test_generate_with_negative_queue_values(self):
        """Test generation with negative queue parameter values."""
        generator = CodeAnalysisConfigGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "config.json"
            # Generate with negative values - should fail validation
            with pytest.raises(ValueError, match="max_concurrent|retention"):
                generator.generate(
                    protocol="http",
                    out_path=str(out_path),
                    queue_max_concurrent=-1,  # Invalid
                    queue_retention_seconds=-100,  # Invalid
                )

    def test_generate_with_zero_queue_max_concurrent(self):
        """Test generation with zero queue_max_concurrent."""
        generator = CodeAnalysisConfigGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "config.json"
            # Zero max_concurrent - should fail validation (must be >= 1)
            with pytest.raises(ValueError, match="max_concurrent"):
                generator.generate(
                    protocol="http",
                    out_path=str(out_path),
                    queue_max_concurrent=0,  # Invalid: must be >= 1
                )

    def test_generate_creates_invalid_config_structure(self):
        """Test that generator creates config that fails validation."""
        generator = CodeAnalysisConfigGenerator()

        # This test verifies that validation catches issues
        # We'll generate a config that should be invalid
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "config.json"

            # Try to generate with parameters that create invalid config
            # For example, mTLS without CA cert
            try:
                generator.generate(
                    protocol="mtls",
                    out_path=str(out_path),
                    # Missing server_ca_cert_file
                )
                # If generation succeeds, validation should catch it
                pytest.fail("Generation should have failed validation")
            except ValueError as e:
                # Expected - validation should catch missing CA cert
                assert "CA" in str(e) or "invalid" in str(e).lower()

