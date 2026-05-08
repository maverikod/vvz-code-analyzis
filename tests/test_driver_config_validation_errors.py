"""
Tests for driver config validation error cases (in-memory config).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.core.config_validator import CodeAnalysisConfigValidator


class TestDriverConfigValidationErrors:
    """Test driver config validation error paths and edge cases."""

    def test_driver_not_dict(self):
        """Test validation when driver is not a dictionary."""
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
        assert any(
            "database.driver.config must be dictionary" in r.message for r in errors
        )

    def test_empty_path_string(self):
        """Test validation with empty path string."""
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
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is False
        errors = [r for r in results if r.level == "error"]
        assert len(errors) > 0
        assert any(
            "command_timeout must be number" in r.message or "command_timeout" in r.key
            for r in errors
        )

    def test_worker_config_poll_interval_not_number(self):
        """Test validation when poll_interval is not a number."""
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
        assert any(
            "poll_interval must be number" in r.message or "poll_interval" in r.key
            for r in errors
        )

    def test_worker_config_command_timeout_zero(self):
        """Test validation when command_timeout is zero."""
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
                        "type": "postgres",
                        "config": {
                            "host": "localhost",
                            "port": 5432,
                            "database": "test",
                            "user": "testuser",
                            "password_env": "TEST_PG_PASSWORD_FOR_VALIDATOR",
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
            "server": {
                "host": "localhost",
                "port": 15000,
                "protocol": "mtls",
                "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"},
            },
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "database": {},
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is True

    def test_no_database_section(self):
        """Test validation when database section is missing (should pass)."""
        config = {
            "server": {
                "host": "localhost",
                "port": 15000,
                "protocol": "mtls",
                "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"},
            },
            "queue_manager": {"enabled": True},
            "code_analysis": {},
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is True
