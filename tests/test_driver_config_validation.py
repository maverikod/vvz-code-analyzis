"""
Tests for driver configuration validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.core.config_validator import CodeAnalysisConfigValidator
from code_analysis.core.docs_indexing_defaults import default_docs_indexing_dict


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

    def test_pgvector_with_sqlite_class_driver_errors(self) -> None:
        """vector_search_backend=pgvector is invalid for sqlite / sqlite_proxy (FAISS only)."""
        config = {
            "server": {
                "host": "localhost",
                "port": 15000,
                "protocol": "mtls",
                "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"},
            },
            "queue_manager": {"enabled": True},
            "code_analysis": {
                "vector_search_backend": "pgvector",
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
                },
            },
        }
        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        assert validator.get_validation_summary()["is_valid"] is False
        assert any(
            r.level == "error" and r.key == "vector_search_backend" for r in results
        )

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
        assert any("database.driver.type" in (r.key or "") for r in errors)

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
        assert any("database.driver.config" in (r.key or "") for r in errors)

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
        assert any("database.driver.type" in (r.key or "") for r in errors)

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
        assert any("database.driver.config.path" in (r.key or "") for r in errors)

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
        assert any("command_timeout" in (r.key or "") for r in errors)

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
        assert any("poll_interval" in (r.key or "") for r in errors)

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


def _config_with_docs_indexing(docs_indexing: dict) -> dict:
    return {
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
            },
            "docs_indexing": docs_indexing,
        },
    }


class TestDocsIndexingConfigValidation:
    """Validation for code_analysis.docs_indexing."""

    def test_docs_indexing_default_block_valid(self) -> None:
        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(
            _config_with_docs_indexing(default_docs_indexing_dict())
        )
        assert validator.get_validation_summary()["is_valid"] is True
        assert not any(r.level == "error" for r in results)

    def test_docs_indexing_minimal_enabled_valid(self) -> None:
        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(
            _config_with_docs_indexing({"enabled": True})
        )
        assert validator.get_validation_summary()["is_valid"] is True
        assert not any(r.level == "error" for r in results)

    def test_docs_indexing_unknown_nested_key_errors(self) -> None:
        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(
            _config_with_docs_indexing({"enabled": False, "typo_key": 1})
        )
        assert any(
            r.level == "error" and r.key == "docs_indexing.typo_key" for r in results
        )

    def test_docs_indexing_include_without_docs_suffix_errors(self) -> None:
        validator = CodeAnalysisConfigValidator()
        body = default_docs_indexing_dict()
        body["include"] = ["docs/**/*.txt"]
        results = validator.validate_config(_config_with_docs_indexing(body))
        err = [r for r in results if r.level == "error"]
        assert any(
            r.key is not None
            and r.key.startswith("docs_indexing.include")
            and (".md" in r.message.lower() or ".json" in r.message.lower())
            for r in err
        )

    def test_docs_indexing_include_json_only_valid(self) -> None:
        validator = CodeAnalysisConfigValidator()
        body = default_docs_indexing_dict()
        body["include"] = ["docs/**/*.json"]
        results = validator.validate_config(_config_with_docs_indexing(body))
        assert validator.get_validation_summary()["is_valid"] is True
        assert not any(r.level == "error" for r in results)

    def test_docs_indexing_roots_traversal_errors(self) -> None:
        validator = CodeAnalysisConfigValidator()
        body = default_docs_indexing_dict()
        body["roots"] = ["docs/../secrets"]
        results = validator.validate_config(_config_with_docs_indexing(body))
        assert any(r.level == "error" for r in results)

    def test_docs_indexing_not_object_errors(self) -> None:
        validator = CodeAnalysisConfigValidator()
        cfg = _config_with_docs_indexing({})
        cfg["code_analysis"]["docs_indexing"] = "no"
        results = validator.validate_config(cfg)
        assert any("docs_indexing must be an object" in r.message for r in results)
