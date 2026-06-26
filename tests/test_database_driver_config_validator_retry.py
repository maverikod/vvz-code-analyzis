"""
Tests for database driver retry/timeout config validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.core.config_validator import CodeAnalysisConfigValidator


def _shell():
    """Return shell."""
    return {
        "server": {
            "host": "localhost",
            "port": 15000,
            "protocol": "mtls",
            "ssl": {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"},
        },
        "queue_manager": {"enabled": True},
    }


def _pg_base():
    """Return pg base."""
    return {
        "host": "localhost",
        "port": 5432,
        "dbname": "code_analysis",
        "user": "u",
        "password_env": "CODE_ANALYSIS_POSTGRES_PASSWORD",
    }


class TestDatabaseDriverConfigValidatorRetry:
    """Represent TestDatabaseDriverConfigValidatorRetry."""

    def test_existing_config_without_retry_timeout_fields_passes(self):
        """Verify test existing config without retry timeout fields passes."""
        config = {
            **_shell(),
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "postgres",
                        "config": _pg_base(),
                    }
                }
            },
        }
        validator = CodeAnalysisConfigValidator()
        results = validator.validate_config(config)
        errors = [r for r in results if r.level == "error"]
        retry_msgs = [
            r
            for r in errors
            if "write_retry" in r.message or "lock_timeout_seconds" in r.message
        ]
        assert not retry_msgs
        assert validator.get_validation_summary()["is_valid"] is True

    def test_postgres_config_with_valid_canonical_fields_passes(self):
        """Verify test postgres config with valid canonical fields passes."""
        config = {
            **_shell(),
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "postgres",
                        "config": {
                            **_pg_base(),
                            "write_retry_attempts": 3,
                            "write_retry_delay_seconds": 1.5,
                            "write_retry_backoff_multiplier": 2.0,
                            "write_retry_jitter_seconds": 0.5,
                            "lock_timeout_seconds": 120,
                            "statement_timeout_seconds": 600,
                        },
                    }
                }
            },
        }
        validator = CodeAnalysisConfigValidator()
        validator.validate_config(config)
        assert validator.get_validation_summary()["is_valid"] is True

    def test_sqlite_config_with_valid_canonical_retry_fields_passes(self):
        """Verify test sqlite config with valid canonical retry fields passes."""
        config = {
            **_shell(),
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite",
                        "config": {
                            "path": "data/test.db",
                            "write_retry_attempts": 2,
                            "write_retry_delay_seconds": 0,
                            "write_retry_backoff_multiplier": 1.0,
                            "write_retry_jitter_seconds": 0,
                            "lock_timeout_seconds": 10,
                            "statement_timeout_seconds": 30,
                        },
                    }
                }
            },
        }
        validator = CodeAnalysisConfigValidator()
        validator.validate_config(config)
        assert validator.get_validation_summary()["is_valid"] is True

    def test_sqlite_proxy_config_with_valid_canonical_retry_fields_passes(self):
        """Verify test sqlite proxy config with valid canonical retry fields passes."""
        config = {
            **_shell(),
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "sqlite_proxy",
                        "config": {
                            "path": "data/test.db",
                            "write_retry_attempts": 5,
                            "write_retry_delay_seconds": 2,
                            "write_retry_backoff_multiplier": 1.5,
                            "write_retry_jitter_seconds": 1,
                            "lock_timeout_seconds": 60,
                            "statement_timeout_seconds": 120,
                        },
                    }
                }
            },
        }
        validator = CodeAnalysisConfigValidator()
        validator.validate_config(config)
        assert validator.get_validation_summary()["is_valid"] is True

    def test_invalid_retry_attempts_ranges_fail(self):
        """Verify test invalid retry attempts ranges fail."""
        for bad_attempts in (0, 21, 3.0, "3"):
            config = {
                **_shell(),
                "code_analysis": {
                    "database": {
                        "driver": {
                            "type": "postgres",
                            "config": {
                                **_pg_base(),
                                "write_retry_attempts": bad_attempts,
                            },
                        }
                    }
                },
            }
            validator = CodeAnalysisConfigValidator()
            validator.validate_config(config)
            errors = [r for r in validator.validation_results if r.level == "error"]
            assert any(
                "code_analysis.database.driver.config.write_retry_attempts" in r.message
                or r.key == "database.driver.config.write_retry_attempts"
                for r in errors
            ), f"expected write_retry_attempts error for {bad_attempts!r}"

    def test_invalid_delay_backoff_jitter_ranges_fail(self):
        """Verify test invalid delay backoff jitter ranges fail."""
        cases = [
            (
                "write_retry_delay_seconds",
                -1,
                "database.driver.config.write_retry_delay_seconds",
            ),
            (
                "write_retry_jitter_seconds",
                -0.1,
                "database.driver.config.write_retry_jitter_seconds",
            ),
            (
                "write_retry_backoff_multiplier",
                0.9,
                "database.driver.config.write_retry_backoff_multiplier",
            ),
            (
                "write_retry_delay_seconds",
                61,
                "database.driver.config.write_retry_delay_seconds",
            ),
            (
                "write_retry_jitter_seconds",
                11,
                "database.driver.config.write_retry_jitter_seconds",
            ),
            (
                "write_retry_backoff_multiplier",
                10.1,
                "database.driver.config.write_retry_backoff_multiplier",
            ),
        ]
        for field_name, bad_value, expect_key in cases:
            config = {
                **_shell(),
                "code_analysis": {
                    "database": {
                        "driver": {
                            "type": "postgres",
                            "config": {
                                **_pg_base(),
                                field_name: bad_value,
                            },
                        }
                    }
                },
            }
            validator = CodeAnalysisConfigValidator()
            validator.validate_config(config)
            errors = [r for r in validator.validation_results if r.level == "error"]
            assert any(
                expect_key in (r.key or "") or expect_key.split(".")[-1] in r.message
                for r in errors
            ), f"expected range error for {field_name}={bad_value!r}"

    def test_invalid_timeout_ranges_fail(self):
        """Verify test invalid timeout ranges fail."""
        cases = [
            ("lock_timeout_seconds", 0),
            ("lock_timeout_seconds", 301),
            ("statement_timeout_seconds", -1),
            ("statement_timeout_seconds", 3601),
        ]
        for field_name, bad_value in cases:
            config = {
                **_shell(),
                "code_analysis": {
                    "database": {
                        "driver": {
                            "type": "postgres",
                            "config": {**_pg_base(), field_name: bad_value},
                        }
                    }
                },
            }
            validator = CodeAnalysisConfigValidator()
            validator.validate_config(config)
            errors = [r for r in validator.validation_results if r.level == "error"]
            assert any(
                f"database.driver.config.{field_name}" == r.key
                or field_name in r.message
                for r in errors
            ), f"expected timeout error for {field_name}={bad_value!r}"

    def test_invalid_types_fail_with_clear_messages(self):
        """Verify test invalid types fail with clear messages."""
        cases = [
            ("write_retry_attempts", "2", "write_retry_attempts"),
            ("write_retry_delay_seconds", True, "write_retry_delay_seconds"),
            ("write_retry_backoff_multiplier", [], "write_retry_backoff_multiplier"),
            ("write_retry_jitter_seconds", {}, "write_retry_jitter_seconds"),
            ("lock_timeout_seconds", "30", "lock_timeout_seconds"),
            ("statement_timeout_seconds", False, "statement_timeout_seconds"),
        ]
        for field_name, bad_value, expect_name in cases:
            config = {
                **_shell(),
                "code_analysis": {
                    "database": {
                        "driver": {
                            "type": "postgres",
                            "config": {**_pg_base(), field_name: bad_value},
                        }
                    }
                },
            }
            validator = CodeAnalysisConfigValidator()
            validator.validate_config(config)
            errors = [r for r in validator.validation_results if r.level == "error"]
            assert any(
                expect_name in r.message
                and "code_analysis.database.driver.config" in r.message
                for r in errors
            ), f"expected clear message for {field_name}={bad_value!r}"

    def test_deprecated_aliases_fail_with_suggestion(self):
        """Verify test deprecated aliases fail with suggestion."""
        for alias, canonical in (
            ("retry_attempts", "write_retry_attempts"),
            ("retry_delay_seconds", "write_retry_delay_seconds"),
        ):
            config = {
                **_shell(),
                "code_analysis": {
                    "database": {
                        "driver": {
                            "type": "postgres",
                            "config": {**_pg_base(), alias: 3},
                        }
                    }
                },
            }
            validator = CodeAnalysisConfigValidator()
            validator.validate_config(config)
            errors = [r for r in validator.validation_results if r.level == "error"]
            assert any(
                alias in r.message and canonical in r.message for r in errors
            ), f"expected deprecation hint for {alias}"

    def test_no_unknown_retry_aliases_are_silently_accepted(self):
        """Verify test no unknown retry aliases are silently accepted."""
        config = {
            **_shell(),
            "code_analysis": {
                "database": {
                    "driver": {
                        "type": "postgres",
                        "config": {
                            **_pg_base(),
                            "write_retry_attemps": 999,
                        },
                    }
                }
            },
        }
        validator = CodeAnalysisConfigValidator()
        validator.validate_config(config)
        errors = [r for r in validator.validation_results if r.level == "error"]
        assert any("write_retry_attemps" in r.message for r in errors)
        assert validator.get_validation_summary()["is_valid"] is False
