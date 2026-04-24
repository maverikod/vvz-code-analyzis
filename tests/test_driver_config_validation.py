"""
Tests for driver configuration validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.core.config_validator import CodeAnalysisConfigValidator


class TestDriverConfigValidation:
    """Test driver configuration validation."""

    def test_valid_driver_config(self):
        """Test validation with valid driver config."""
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

    def test_valid_postgres_driver_config(self):
        """Test validation with postgres driver (dbname, user, password_env)."""
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
                            "host": "127.0.0.1",
                            "port": 5432,
                            "dbname": "code_analysis",
                            "user": "postgres",
                            "password_env": "CODE_ANALYSIS_POSTGRES_PASSWORD",
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

    def test_postgres_rejects_inline_password(self):
        """Inline password in config must be rejected for postgres."""
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
                            "host": "127.0.0.1",
                            "port": 5432,
                            "dbname": "code_analysis",
                            "user": "postgres",
                            "password_env": "CODE_ANALYSIS_POSTGRES_PASSWORD",
                            "password": "secret",
                        },
                    }
                }
            },
        }

        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        summary = validator.get_validation_summary()

        assert summary["is_valid"] is False
        assert any("password must not be set" in r.message for r in results)

    def test_valid_sqlite_driver(self):
        """Test validation with valid sqlite driver (not proxy)."""
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
