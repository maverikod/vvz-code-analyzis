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

    def test_mysql_driver_rejected(self):
        """mysql was never a real driver (phantom type); type must be 'postgres'."""
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

        assert summary["is_valid"] is False
        errors = [r for r in results if r.level == "error"]
        assert len(errors) > 0
        assert any("database.driver.type" in (r.key or "") for r in errors)

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
