"""
Tests for database driver configuration.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json

from code_analysis.core.config import get_driver_config
from code_analysis.core.config_validator import CodeAnalysisConfigValidator


class TestDriverConfigValidation:
    """Test driver configuration validation."""

    def test_valid_driver_config(self):
        """Test validation with valid driver config."""
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "http"},
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
            "server": {"host": "localhost", "port": 15000, "protocol": "http"},
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
            "server": {"host": "localhost", "port": 15000, "protocol": "http"},
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
            "server": {"host": "localhost", "port": 15000, "protocol": "http"},
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
            "server": {"host": "localhost", "port": 15000, "protocol": "http"},
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
            "server": {"host": "localhost", "port": 15000, "protocol": "http"},
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
            "server": {"host": "localhost", "port": 15000, "protocol": "http"},
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
            "server": {"host": "localhost", "port": 15000, "protocol": "http"},
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


class TestDriverConfigFileValidation:
    """Test driver config validation with real config files."""

    def test_validate_config_file_with_driver(self, tmp_path):
        """Test validation of config file with driver section."""
        config_file = tmp_path / "config.json"
        config = {
            "server": {"host": "localhost", "port": 15000, "protocol": "http"},
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
            "server": {"host": "localhost", "port": 15000, "protocol": "http"},
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
