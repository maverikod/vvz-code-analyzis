"""
Tests for get_driver_config helper.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.core.config import get_driver_config

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


