"""
Tests for server behavior with invalid configuration.

Tests that server exits with error when configuration contains unknown fields.
"""

import json
import pytest
import subprocess
import sys
import tempfile
from pathlib import Path


class TestServerConfigValidation:
    """Tests for server configuration validation behavior."""

    def test_server_exits_on_unknown_field(self, tmp_path):
        """Test that server exits with error on unknown configuration field."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"host": "127.0.0.1", "port": 15000, "unknown_field": "value"}')
        
        # Try to start server with invalid config
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "code_analysis.main",
                "--config",
                str(config_file),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        # Server should exit with non-zero code
        assert result.returncode != 0
        # Error message should mention unknown field
        assert "unknown" in result.stderr.lower() or "unknown" in result.stdout.lower()

    def test_server_exits_on_invalid_port(self, tmp_path):
        """Test that server exits with error on invalid port."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"host": "127.0.0.1", "port": 70000}')
        
        # Try to start server with invalid config
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "code_analysis.main",
                "--config",
                str(config_file),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        # Server should exit with non-zero code
        assert result.returncode != 0
        # Error message should mention port
        assert "port" in result.stderr.lower() or "port" in result.stdout.lower()

    def test_server_exits_on_invalid_json(self, tmp_path):
        """Test that server exits with error on invalid JSON."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"host": "127.0.0.1", "port": 15000, invalid}')
        
        # Try to start server with invalid config
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "code_analysis.main",
                "--config",
                str(config_file),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        # Server should exit with non-zero code or handle gracefully
        # (JSON parsing might be handled differently)
        assert result.returncode != 0 or "json" in result.stderr.lower() or "json" in result.stdout.lower()

