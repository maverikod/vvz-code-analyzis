"""
Tests for database driver configuration.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import subprocess
from pathlib import Path

import pytest

from code_analysis.core.config import get_driver_config
from code_analysis.core.config_validator import CodeAnalysisConfigValidator


def _create_dummy_ssl_certs_in_dir(dir_path: Path) -> None:
    """Create minimal valid PEM cert/key in dir_path for file-based validation tests.

    Generates a CA and a server cert signed by that CA so base validator
    (cert chain validation) passes.
    """
    try:
        # CA (self-signed)
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(dir_path / "ca.key"),
                "-out", str(dir_path / "ca.crt"),
                "-days", "1", "-nodes", "-subj", "/CN=TestCA",
            ],
            check=True,
            capture_output=True,
        )
        # Server key and CSR
        subprocess.run(
            [
                "openssl", "req", "-new", "-newkey", "rsa:2048",
                "-keyout", str(dir_path / "server.key"),
                "-out", str(dir_path / "server.csr"),
                "-nodes", "-subj", "/CN=localhost",
            ],
            check=True,
            capture_output=True,
        )
        # Sign server cert with CA
        subprocess.run(
            [
                "openssl", "x509", "-req", "-in", str(dir_path / "server.csr"),
                "-CA", str(dir_path / "ca.crt"),
                "-CAkey", str(dir_path / "ca.key"),
                "-CAcreateserial",
                "-out", str(dir_path / "server.crt"),
                "-days", "1",
            ],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        pytest.skip(f"openssl not available or failed: {e}")


class TestDriverConfigValidation:
    """Test driver configuration validation."""

    def test_valid_driver_config(self):
        """Test validation with valid driver config."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite_proxy",
                        "config": {
                            "path": "data/test.db",
                            "worker_config": {
                                "command_timeout": 30.0,
                                "poll_interval": 0.1,
                            },
                        },
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is True
        errors = [r for r in results if r.level == "error"]
        assert len(errors) == 0

    def test_missing_driver_type(self):
        """Test validation with missing driver type."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "config": {
                            "path": "data/test.db",
                        }
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is False
        errors = [r for r in results if r.level == "error"]
        assert len(errors) > 0
        assert any("database.driver.type" in r.key for r in errors)

    def test_missing_driver_config(self):
        """Test validation with missing driver config."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite_proxy",
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is False
        errors = [r for r in results if r.level == "error"]
        assert len(errors) > 0
        assert any("database.driver.config" in r.key for r in errors)

    def test_invalid_driver_type(self):
        """Test validation with invalid driver type."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "invalid_driver",
                        "config": {
                            "path": "data/test.db",
                        },
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is False
        errors = [r for r in results if r.level == "error"]
        assert len(errors) > 0
        assert any("database.driver.type" in r.key for r in errors)

    def test_missing_path_for_sqlite(self):
        """Test validation with missing path for sqlite driver."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite_proxy",
                        "config": {},
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is False
        errors = [r for r in results if r.level == "error"]
        assert len(errors) > 0
        assert any("database.driver.config.path" in r.key for r in errors)

    def test_invalid_worker_config_timeout(self):
        """Test validation with invalid worker_config command_timeout."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite_proxy",
                        "config": {
                            "path": "data/test.db",
                            "worker_config": {
                                "command_timeout": -1,
                                "poll_interval": 0.1,
                            },
                        },
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is False
        errors = [r for r in results if r.level == "error"]
        assert len(errors) > 0
        assert any("command_timeout" in r.key for r in errors)

    def test_invalid_worker_config_poll_interval(self):
        """Test validation with invalid worker_config poll_interval."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite_proxy",
                        "config": {
                            "path": "data/test.db",
                            "worker_config": {
                                "command_timeout": 30.0,
                                "poll_interval": -1,
                            },
                        },
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is False
        errors = [r for r in results if r.level == "error"]
        assert len(errors) > 0
        assert any("poll_interval" in r.key for r in errors)

    def test_valid_sqlite_driver(self):
        """Test validation with valid sqlite driver (not proxy)."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite",
                        "config": {
                            "path": "data/test.db",
                        },
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is True
        errors = [r for r in results if r.level == "error"]
        assert len(errors) == 0


class TestGetDriverConfig:
    """Test get_driver_config helper function."""

    def test_get_driver_config_from_database_section(self):
        """Test extracting driver config from code_analysis.database.driver."""
        config = {
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite_proxy",
                        "config": {
                            "path": "data/test.db",
                            "worker_config": {
                                "command_timeout": 30.0,
                                "poll_interval": 0.1,
                            },
                        },
                    }
                }
            }
        }

        driver_config = get_driver_config(config)

        assert driver_config is not None
        assert driver_config["type"] == "sqlite_proxy"
        assert driver_config["config"]["path"] == "data/test.db"
        assert "worker_config" in driver_config["config"]

    def test_get_driver_config_fallback_to_db_path(self):
        """Test fallback to db_path when database.driver is not present."""
        config = {
            "code_analysis": {
                "db_path": "data/test.db",
            }
        }

        driver_config = get_driver_config(config)

        assert driver_config is not None
        assert driver_config["type"] == "sqlite_proxy"
        assert "path" in driver_config["config"]

    def test_get_driver_config_no_config(self):
        """Test get_driver_config when no config is available."""
        config = {
            "code_analysis": {},
        }

        driver_config = get_driver_config(config)

        assert driver_config is None

    def test_get_driver_config_empty_code_analysis(self):
        """Test get_driver_config when code_analysis section is missing."""
        config = {}

        driver_config = get_driver_config(config)

        assert driver_config is None

    def test_get_driver_config_with_backup_dir(self):
        """Test driver config with backup_dir."""
        config = {
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite_proxy",
                        "config": {
                            "path": "data/test.db",
                            "backup_dir": "data/backups",
                        },
                    }
                }
            }
        }

        driver_config = get_driver_config(config)

        assert driver_config is not None
        assert driver_config["config"]["backup_dir"] == "data/backups"

    def test_get_driver_config_driver_type_missing(self):
        """Test get_driver_config when driver type is missing."""
        config = {
            "code_analysis": {
                "database": {
                    "driver": {
                        "config": {
                            "path": "data/test.db",
                        },
                    }
                }
            }
        }

        driver_config = get_driver_config(config)

        # Should return None when type is missing
        assert driver_config is None

    def test_get_driver_config_driver_config_missing(self):
        """Test get_driver_config when driver config is missing."""
        config = {
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite_proxy",
                    }
                }
            }
        }

        driver_config = get_driver_config(config)

        # Should return None when config is missing
        assert driver_config is None

    def test_get_driver_config_driver_not_dict(self):
        """Test get_driver_config when driver is not a dict."""
        config = {
            "code_analysis": {
                "database": {
                    "driver": "not_a_dict",
                }
            }
        }

        driver_config = get_driver_config(config)

        # Should return None when driver is not a dict
        assert driver_config is None

    def test_get_driver_config_database_not_dict(self):
        """Test get_driver_config when database is not a dict."""
        config = {
            "code_analysis": {
                "database": "not_a_dict",
            }
        }

        # When database is not a dict, the code should check isinstance(database, dict)
        # and return None gracefully
        driver_config = get_driver_config(config)

        # Should return None when database is not a dict
        assert driver_config is None

    def test_get_driver_config_with_postgres(self):
        """Test get_driver_config with postgres driver."""
        config = {
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "postgres",
                        "config": {
                            "host": "localhost",
                            "port": 5432,
                            "database": "test",
                        },
                    }
                }
            }
        }

        driver_config = get_driver_config(config)

        assert driver_config is not None
        assert driver_config["type"] == "postgres"
        assert driver_config["config"]["host"] == "localhost"

    def test_get_driver_config_with_mysql(self):
        """Test get_driver_config with mysql driver."""
        config = {
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "mysql",
                        "config": {
                            "host": "localhost",
                            "port": 3306,
                            "database": "test",
                        },
                    }
                }
            }
        }

        driver_config = get_driver_config(config)

        assert driver_config is not None
        assert driver_config["type"] == "mysql"
        assert driver_config["config"]["host"] == "localhost"


class TestDriverConfigFileValidation:
    """Test driver config validation with real config files."""

    def test_validate_config_file_with_driver(self, tmp_path):
        """Test validation of config file with driver section."""
        config_file = tmp_path / "config.json"
        _create_dummy_ssl_certs_in_dir(tmp_path)
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
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
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
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

    def test_driver_not_dict(self):
        """Test validation when driver is not a dictionary."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": "not_a_dict",
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is False
        errors = [r for r in results if r.level == "error"]
        assert len(errors) > 0
        assert any("database.driver must be a dictionary" in r.message for r in errors)

    def test_driver_type_not_string(self):
        """Test validation when driver type is not a string."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": 123,
                        "config": {
                            "path": "data/test.db",
                        },
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is False
        errors = [r for r in results if r.level == "error"]
        assert len(errors) > 0
        assert any("database.driver.type must be string" in r.message for r in errors)

    def test_driver_config_not_dict(self):
        """Test validation when driver config is not a dictionary."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite_proxy",
                        "config": "not_a_dict",
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is False
        errors = [r for r in results if r.level == "error"]
        assert len(errors) > 0
        assert any("database.driver.config must be dictionary" in r.message for r in errors)

    def test_empty_path_string(self):
        """Test validation with empty path string."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite_proxy",
                        "config": {
                            "path": "   ",
                        },
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is False
        errors = [r for r in results if r.level == "error"]
        assert len(errors) > 0
        assert any("path cannot be empty" in r.message for r in errors)

    def test_worker_config_command_timeout_not_number(self):
        """Test validation when command_timeout is not a number."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite_proxy",
                        "config": {
                            "path": "data/test.db",
                            "worker_config": {
                                "command_timeout": "not_a_number",
                                "poll_interval": 0.1,
                            },
                        },
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        # Skip field type validation to test specific driver validation
        # We'll test the driver-specific validation directly
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is False
        errors = [r for r in results if r.level == "error"]
        assert len(errors) > 0
        # Check for either driver-specific error or field type error
        assert any(
            "command_timeout must be number" in r.message
            or "command_timeout" in r.key
            for r in errors
        )

    def test_worker_config_poll_interval_not_number(self):
        """Test validation when poll_interval is not a number."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite_proxy",
                        "config": {
                            "path": "data/test.db",
                            "worker_config": {
                                "command_timeout": 30.0,
                                "poll_interval": "not_a_number",
                            },
                        },
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is False
        errors = [r for r in results if r.level == "error"]
        assert len(errors) > 0
        # Check for either driver-specific error or field type error
        assert any(
            "poll_interval must be number" in r.message
            or "poll_interval" in r.key
            for r in errors
        )

    def test_worker_config_command_timeout_zero(self):
        """Test validation when command_timeout is zero."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite_proxy",
                        "config": {
                            "path": "data/test.db",
                            "worker_config": {
                                "command_timeout": 0,
                                "poll_interval": 0.1,
                            },
                        },
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is False
        errors = [r for r in results if r.level == "error"]
        assert len(errors) > 0
        assert any("command_timeout must be > 0" in r.message for r in errors)

    def test_worker_config_poll_interval_zero(self):
        """Test validation when poll_interval is zero."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite_proxy",
                        "config": {
                            "path": "data/test.db",
                            "worker_config": {
                                "command_timeout": 30.0,
                                "poll_interval": 0,
                            },
                        },
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is False
        errors = [r for r in results if r.level == "error"]
        assert len(errors) > 0
        assert any("poll_interval must be > 0" in r.message for r in errors)

    def test_valid_postgres_driver(self):
        """Test validation with valid postgres driver."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "postgres",
                        "config": {
                            "host": "localhost",
                            "port": 5432,
                            "database": "test",
                        },
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is True
        errors = [r for r in results if r.level == "error"]
        assert len(errors) == 0

    def test_valid_mysql_driver(self):
        """Test validation with valid mysql driver."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "mysql",
                        "config": {
                            "host": "localhost",
                            "port": 3306,
                            "database": "test",
                        },
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is True
        errors = [r for r in results if r.level == "error"]
        assert len(errors) == 0

    def test_no_driver_section(self):
        """Test validation when driver section is missing (should pass)."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {},
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        # Missing driver section is not an error (optional)
        assert summary["is_valid"] is True

    def test_no_database_section(self):
        """Test validation when database section is missing (should pass)."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
            "queue_manager": {"enabled": True},
            "code_analysis": {},
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        # Missing database section is not an error (optional)
        assert summary["is_valid"] is True

    def test_validate_file_method(self, tmp_path):
        """Test validate_file method."""
        config_file = tmp_path / "config.json"
        _create_dummy_ssl_certs_in_dir(tmp_path)
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "mtls", "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}},
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
        assert config_data["code_analysis"]["database"]["driver"]["type"] == "sqlite_proxy"

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
