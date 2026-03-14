"""
Tests for driver config validation with real config files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json

from code_analysis.core.config_validator import CodeAnalysisConfigValidator
from tests.test_config_driver_helpers import create_dummy_ssl_certs_in_dir


class TestDriverConfigFileValidation:
    """Test driver config validation with real config files."""

    def test_validate_config_file_with_driver(self, tmp_path):
        """Test validation of config file with driver section."""
        config_file = tmp_path / "config.json"
        create_dummy_ssl_certs_in_dir(tmp_path)
        config = {
            "server": {
                "host": "localhost",
                "port": 15000,
                "protocol": "mtls",
                "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"},
            },
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite_proxy",
                        "config": {
                            "path": str(tmp_path / "test.db"),
                            "worker_config": {
                                "command_timeout": 30.0,
                                "poll_interval": 0.1,
                            },
                        },
                    }
                }
            },
        }

        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f)

        validator = CodeAnalysisConfigValidator(str(config_file))
        validator.load_config()
        validator.validate_config()
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is True

    def test_validate_config_file_invalid_driver(self, tmp_path):
        """Test validation of config file with invalid driver config."""
        config_file = tmp_path / "config.json"
        config = {
            "server": {
                "host": "localhost",
                "port": 15000,
                "protocol": "mtls",
                "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"},
            },
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "invalid",
                        "config": {},
                    }
                }
            },
        }

        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f)

        validator = CodeAnalysisConfigValidator(str(config_file))
        validator.load_config()
        validator.validate_config()
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is False
        errors = [r for r in validator.validation_results if r.level == "error"]
        assert len(errors) > 0

    def test_validate_file_method(self, tmp_path):
        """Test validate_file method."""
        config_file = tmp_path / "config.json"
        create_dummy_ssl_certs_in_dir(tmp_path)
        config = {
            "server": {
                "host": "localhost",
                "port": 15000,
                "protocol": "mtls",
                "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"},
            },
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite_proxy",
                        "config": {
                            "path": str(tmp_path / "test.db"),
                            "worker_config": {
                                "command_timeout": 30.0,
                                "poll_interval": 0.1,
                            },
                        },
                    }
                }
            },
        }

        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f)

        validator = CodeAnalysisConfigValidator()
        is_valid, error, config_data = validator.validate_file(str(config_file))

        assert is_valid is True
        assert error is None
        assert config_data is not None
        assert (
            config_data["code_analysis"]["database"]["driver"]["type"] == "sqlite_proxy"
        )

    def test_validate_file_invalid_json(self, tmp_path):
        """Test validate_file method with invalid JSON."""
        config_file = tmp_path / "config.json"
        with open(config_file, "w", encoding="utf-8") as f:
            f.write("{ invalid json }")

        validator = CodeAnalysisConfigValidator()
        is_valid, error, config_data = validator.validate_file(str(config_file))

        assert is_valid is False
        assert error is not None
        assert "Invalid JSON" in error or "JSON" in error
        assert config_data is None
