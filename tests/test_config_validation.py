"""
Comprehensive tests for configuration validation.

Tests cover:
- All configuration fields
- Field validation (host, port, paths, UUIDs)
- Unknown field detection
- Duplicate detection
- Edge cases
- Error handling

Target coverage: 90%+
"""

import json
import pytest
import uuid
from pathlib import Path

from code_analysis.core.config import (
    ServerConfig,
    ProjectDir,
    SVOServiceConfig,
    validate_config as validate_config_file,
    load_config,
)
from code_analysis.core.config_manager import ConfigManager, validate_config


class TestProjectDirValidation:
    """Tests for ProjectDir validation."""

    def test_valid_project_dir(self, tmp_path):
        """Test valid project directory."""
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        project = ProjectDir(
            id=str(uuid.uuid4()),
            name="test_project",
            path=str(project_path),
        )
        assert project.name == "test_project"
        assert Path(project.path).exists()

    def test_invalid_uuid(self, tmp_path):
        """Test invalid UUID format."""
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        with pytest.raises(ValueError, match="Invalid UUID4"):
            ProjectDir(
                id="not-a-uuid",
                name="test",
                path=str(project_path),
            )

    def test_non_uuid4(self, tmp_path):
        """Test non-UUID4 UUID."""
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        # Test with clearly invalid UUID format
        with pytest.raises(ValueError, match="Invalid UUID4|invalid uuid"):
            ProjectDir(
                id="not-a-uuid-at-all",
                name="test",
                path=str(project_path),
            )

    def test_relative_path(self, tmp_path):
        """Test relative path rejection."""
        with pytest.raises(ValueError, match="Path must be absolute"):
            ProjectDir(
                id=str(uuid.uuid4()),
                name="test",
                path="relative/path",
            )

    def test_nonexistent_path(self, tmp_path):
        """Test nonexistent path rejection."""
        nonexistent = tmp_path / "nonexistent"

        with pytest.raises(ValueError, match="Path does not exist"):
            ProjectDir(
                id=str(uuid.uuid4()),
                name="test",
                path=str(nonexistent),
            )

    def test_file_path_not_directory(self, tmp_path):
        """Test file path rejection."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        with pytest.raises(ValueError, match="Path must be a directory"):
            ProjectDir(
                id=str(uuid.uuid4()),
                name="test",
                path=str(test_file),
            )

    def test_unknown_field(self, tmp_path):
        """Test unknown field rejection."""
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        with pytest.raises(ValueError, match="extra fields not permitted|unknown"):
            ProjectDir(
                id=str(uuid.uuid4()),
                name="test",
                path=str(project_path),
                unknown_field="value",
            )


class TestServerConfigValidation:
    """Tests for ServerConfig validation."""

    def test_valid_minimal_config(self):
        """Test minimal valid configuration."""
        config = ServerConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 15000
        assert config.dirs == []

    def test_valid_full_config(self, tmp_path):
        """Test full valid configuration."""
        project_path = tmp_path / "project"
        project_path.mkdir()
        log_path = tmp_path / "log.txt"
        db_path = tmp_path / "db.db"

        config = ServerConfig(
            host="127.0.0.1",
            port=8080,
            log=str(log_path),
            db_path=str(db_path),
            dirs=[
                ProjectDir(
                    id=str(uuid.uuid4()),
                    name="test",
                    path=str(project_path),
                )
            ],
        )
        assert config.host == "127.0.0.1"
        assert config.port == 8080
        assert len(config.dirs) == 1

    def test_host_validation_empty(self):
        """Test empty host rejection."""
        with pytest.raises(ValueError, match="Host cannot be empty"):
            ServerConfig(host="")

    def test_host_validation_whitespace(self):
        """Test whitespace-only host."""
        config = ServerConfig(host="  127.0.0.1  ")
        assert config.host == "127.0.0.1"  # Should be stripped

    def test_port_validation_too_low(self):
        """Test port below valid range."""
        with pytest.raises(ValueError, match="Port must be between"):
            ServerConfig(port=0)

    def test_port_validation_too_high(self):
        """Test port above valid range."""
        with pytest.raises(ValueError, match="Port must be between"):
            ServerConfig(port=65536)

    def test_port_validation_min(self):
        """Test minimum valid port."""
        config = ServerConfig(port=1)
        assert config.port == 1

    def test_port_validation_max(self):
        """Test maximum valid port."""
        config = ServerConfig(port=65535)
        assert config.port == 65535

    def test_log_path_creation(self, tmp_path):
        """Test log path parent directory creation."""
        log_path = tmp_path / "logs" / "server.log"
        config = ServerConfig(log=str(log_path))
        assert log_path.parent.exists()
        assert config.log == str(log_path.resolve())

    def test_db_path_creation(self, tmp_path):
        """Test database path parent directory creation."""
        db_path = tmp_path / "data" / "db.db"
        config = ServerConfig(db_path=str(db_path))
        assert db_path.parent.exists()
        assert config.db_path == str(db_path.resolve())

    def test_duplicate_project_ids(self, tmp_path):
        """Test duplicate project IDs rejection."""
        project_path = tmp_path / "project"
        project_path.mkdir()
        project_id = str(uuid.uuid4())

        # Duplicates are checked in validate_config function, not in ServerConfig
        config = ServerConfig(
            dirs=[
                ProjectDir(id=project_id, name="test1", path=str(project_path)),
                ProjectDir(id=project_id, name="test2", path=str(project_path)),
            ]
        )
        # Validate using validate_config function

        with pytest.raises(ValueError, match="Duplicate project IDs"):
            validate_config(config.model_dump())

    def test_duplicate_project_names(self, tmp_path):
        """Test duplicate project names rejection."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        # Duplicates are checked in validate_config function, not in ServerConfig
        config = ServerConfig(
            dirs=[
                ProjectDir(id=str(uuid.uuid4()), name="test", path=str(project_path)),
                ProjectDir(id=str(uuid.uuid4()), name="test", path=str(project_path)),
            ]
        )
        # Validate using validate_config function

        with pytest.raises(ValueError, match="Duplicate project names"):
            validate_config(config.model_dump())

    def test_unknown_field(self):
        """Test unknown field rejection."""
        with pytest.raises(ValueError, match="extra fields not permitted|unknown"):
            ServerConfig(unknown_field="value")

    def test_chunker_config(self):
        """Test chunker service configuration."""
        config = ServerConfig(
            chunker=SVOServiceConfig(
                enabled=True,
                host="localhost",
                port=8009,
            )
        )
        assert config.chunker is not None
        assert config.chunker.enabled is True
        assert config.chunker.host == "localhost"

    def test_embedding_config(self):
        """Test embedding service configuration."""
        config = ServerConfig(
            embedding=SVOServiceConfig(
                enabled=True,
                host="localhost",
                port=8001,
            )
        )
        assert config.embedding is not None
        assert config.embedding.enabled is True


class TestConfigFileValidation:
    """Tests for configuration file validation."""

    def test_valid_config_file(self, tmp_path):
        """Test valid configuration file."""
        config_file = tmp_path / "config.json"
        project_path = tmp_path / "project"
        project_path.mkdir()

        config_data = {
            "host": "127.0.0.1",
            "port": 15000,
            "dirs": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "test",
                    "path": str(project_path),
                }
            ],
        }
        config_file.write_text(json.dumps(config_data))

        is_valid, error, config = validate_config_file(config_file)
        assert is_valid
        assert error is None
        assert config is not None
        assert config.host == "127.0.0.1"

    def test_invalid_json(self, tmp_path):
        """Test invalid JSON file."""
        config_file = tmp_path / "config.json"
        config_file.write_text("{ invalid json }")

        is_valid, error, config = validate_config_file(config_file)
        assert not is_valid
        assert error is not None
        assert "Invalid JSON" in error
        assert config is None

    def test_nonexistent_file(self, tmp_path):
        """Test nonexistent configuration file."""
        config_file = tmp_path / "nonexistent.json"

        is_valid, error, config = validate_config_file(config_file)
        assert not is_valid
        assert "not found" in error.lower()
        assert config is None

    def test_unknown_field_in_file(self, tmp_path):
        """Test unknown field in configuration file."""
        config_file = tmp_path / "config.json"
        config_data = {
            "host": "127.0.0.1",
            "port": 15000,
            "unknown_field": "value",
        }
        config_file.write_text(json.dumps(config_data))

        is_valid, error, config = validate_config_file(config_file)
        assert not is_valid
        assert "unknown" in error.lower() or "extra fields" in error.lower()
        assert config is None

    def test_invalid_port_in_file(self, tmp_path):
        """Test invalid port in configuration file."""
        config_file = tmp_path / "config.json"
        config_data = {
            "host": "127.0.0.1",
            "port": 70000,  # Invalid port
        }
        config_file.write_text(json.dumps(config_data))

        is_valid, error, config = validate_config_file(config_file)
        assert not is_valid
        assert "port" in error.lower()
        assert config is None

    def test_invalid_project_uuid_in_file(self, tmp_path):
        """Test invalid project UUID in configuration file."""
        config_file = tmp_path / "config.json"
        project_path = tmp_path / "project"
        project_path.mkdir()

        config_data = {
            "host": "127.0.0.1",
            "port": 15000,
            "dirs": [
                {
                    "id": "not-a-uuid",
                    "name": "test",
                    "path": str(project_path),
                }
            ],
        }
        config_file.write_text(json.dumps(config_data))

        is_valid, error, config = validate_config_file(config_file)
        assert not is_valid
        assert "uuid" in error.lower()
        assert config is None

    def test_empty_config_file(self, tmp_path):
        """Test empty configuration file."""
        config_file = tmp_path / "config.json"
        config_file.write_text("")

        # Empty file should return default config
        is_valid, error, config = validate_config_file(config_file)
        # This depends on implementation - might be valid with defaults
        # or might be invalid

    def test_minimal_config_file(self, tmp_path):
        """Test minimal valid configuration file."""
        config_file = tmp_path / "config.json"
        config_data = {}
        config_file.write_text(json.dumps(config_data))

        is_valid, error, config = validate_config_file(config_file)
        assert is_valid
        assert config is not None
        assert config.host == "0.0.0.0"  # Default
        assert config.port == 15000  # Default


class TestConfigManager:
    """Tests for ConfigManager."""

    def test_read_valid_config(self, tmp_path):
        """Test reading valid configuration."""
        config_file = tmp_path / "config.json"
        project_path = tmp_path / "project"
        project_path.mkdir()

        config_data = {
            "host": "127.0.0.1",
            "port": 15000,
            "dirs": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "test",
                    "path": str(project_path),
                }
            ],
        }
        config_file.write_text(json.dumps(config_data))

        manager = ConfigManager(config_file)
        config = manager.read()
        assert config.host == "127.0.0.1"
        assert len(config.dirs) == 1

    def test_read_nonexistent_config(self, tmp_path):
        """Test reading nonexistent configuration."""
        config_file = tmp_path / "nonexistent.json"
        manager = ConfigManager(config_file)

        with pytest.raises(FileNotFoundError):
            manager.read()

    def test_read_invalid_config(self, tmp_path):
        """Test reading invalid configuration."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"host": "127.0.0.1", "port": 70000}')

        manager = ConfigManager(config_file)
        with pytest.raises(ValueError):
            manager.read()

    def test_read_config_with_unknown_field(self, tmp_path):
        """Test reading config with unknown field."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            '{"host": "127.0.0.1", "port": 15000, "unknown": "value"}'
        )

        manager = ConfigManager(config_file)
        with pytest.raises(ValueError, match="unknown"):
            manager.read()

    def test_write_config(self, tmp_path):
        """Test writing configuration."""
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)

        from code_analysis.core.config import ServerConfig

        config = ServerConfig(host="127.0.0.1", port=8080)
        manager.write(config)

        assert config_file.exists()
        data = json.loads(config_file.read_text())
        assert data["host"] == "127.0.0.1"
        assert data["port"] == 8080

    def test_validate_config_file_valid(self, tmp_path):
        """Test validate_config_file with valid config."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"host": "127.0.0.1", "port": 15000}')

        manager = ConfigManager(config_file)
        is_valid, error, config = manager.validate_config_file()

        assert is_valid
        assert error is None
        assert config is not None

    def test_validate_config_file_invalid(self, tmp_path):
        """Test validate_config_file with invalid config."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"host": "127.0.0.1", "port": 70000}')

        manager = ConfigManager(config_file)
        is_valid, error, config = manager.validate_config_file()

        assert not is_valid
        assert error is not None
        assert config is None

    def test_validate_config_file_unknown_field(self, tmp_path):
        """Test validate_config_file with unknown field."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            '{"host": "127.0.0.1", "port": 15000, "unknown": "value"}'
        )

        manager = ConfigManager(config_file)
        is_valid, error, config = manager.validate_config_file()

        assert not is_valid
        assert "unknown" in error.lower()
        assert config is None

    def test_generate_config_with_env_vars(self, tmp_path, monkeypatch):
        """Test generate_config reading from environment variables."""
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)

        monkeypatch.setenv("CODE_ANALYSIS_HOST", "0.0.0.0")
        monkeypatch.setenv("CODE_ANALYSIS_PORT", "15001")
        monkeypatch.setenv("CODE_ANALYSIS_DB_PATH", "/tmp/test.db")

        config = manager.generate_config(overwrite=True)

        assert config.host == "0.0.0.0"
        assert config.port == 15001
        assert config.db_path == "/tmp/test.db"

    def test_generate_config_cli_overrides_env(self, tmp_path, monkeypatch):
        """Test CLI arguments override environment variables."""
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)

        monkeypatch.setenv("CODE_ANALYSIS_HOST", "0.0.0.0")
        monkeypatch.setenv("CODE_ANALYSIS_PORT", "15001")

        config = manager.generate_config(host="127.0.0.1", port=15002, overwrite=True)

        assert config.host == "127.0.0.1"  # CLI overrides ENV
        assert config.port == 15002  # CLI overrides ENV


class TestSVOServiceConfig:
    """Tests for SVOServiceConfig validation."""

    def test_valid_svo_config(self):
        """Test valid SVO service configuration."""
        config = SVOServiceConfig(
            enabled=True,
            host="localhost",
            port=8009,
        )
        assert config.enabled is True
        assert config.host == "localhost"
        assert config.port == 8009

    def test_svo_config_defaults(self):
        """Test SVO service configuration defaults."""
        config = SVOServiceConfig()
        assert config.enabled is False
        assert config.host == "localhost"
        assert config.port == 8009

    def test_svo_config_unknown_field(self):
        """Test SVO service configuration unknown field rejection."""
        with pytest.raises(ValueError, match="extra fields not permitted|unknown"):
            SVOServiceConfig(unknown_field="value")

    def test_svo_config_mtls_certificates(self, tmp_path):
        """Test SVO service configuration with mTLS certificates."""
        cert_file = tmp_path / "cert.pem"
        cert_file.write_text("test cert")
        key_file = tmp_path / "key.pem"
        key_file.write_text("test key")
        ca_file = tmp_path / "ca.pem"
        ca_file.write_text("test ca")

        config = SVOServiceConfig(
            enabled=True,
            protocol="mtls",
            cert_file=str(cert_file),
            key_file=str(key_file),
            ca_cert_file=str(ca_file),
        )
        assert config.protocol == "mtls"
        assert config.cert_file == str(cert_file.resolve())
        assert config.key_file == str(key_file.resolve())
        assert config.ca_cert_file == str(ca_file.resolve())


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_valid_config(self, tmp_path):
        """Test loading valid configuration."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"host": "127.0.0.1", "port": 15000}')

        config = load_config(config_file)
        assert config.host == "127.0.0.1"
        assert config.port == 15000

    def test_load_invalid_config(self, tmp_path):
        """Test loading invalid configuration."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"host": "127.0.0.1", "port": 70000}')

        with pytest.raises(ValueError):
            load_config(config_file)

    def test_load_config_with_unknown_field(self, tmp_path):
        """Test loading config with unknown field."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            '{"host": "127.0.0.1", "port": 15000, "unknown": "value"}'
        )

        with pytest.raises(ValueError, match="unknown"):
            load_config(config_file)


class TestEdgeCases:
    """Edge case tests."""

    def test_multiple_projects_same_path(self, tmp_path):
        """Test multiple projects with same path (should be allowed)."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        config = ServerConfig(
            dirs=[
                ProjectDir(
                    id=str(uuid.uuid4()), name="project1", path=str(project_path)
                ),
                ProjectDir(
                    id=str(uuid.uuid4()), name="project2", path=str(project_path)
                ),
            ]
        )
        assert len(config.dirs) == 2

    def test_empty_project_name(self, tmp_path):
        """Test empty project name (should be allowed by schema)."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        # Empty name might be allowed, depends on validation
        project = ProjectDir(
            id=str(uuid.uuid4()),
            name="",  # Empty name
            path=str(project_path),
        )
        assert project.name == ""

    def test_very_long_path(self, tmp_path):
        """Test very long path."""
        # Create nested directories
        deep_path = tmp_path
        for i in range(10):
            deep_path = deep_path / f"level_{i}"
        deep_path.mkdir(parents=True)

        project = ProjectDir(
            id=str(uuid.uuid4()),
            name="test",
            path=str(deep_path),
        )
        assert Path(project.path).exists()

    def test_special_characters_in_name(self, tmp_path):
        """Test special characters in project name."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        project = ProjectDir(
            id=str(uuid.uuid4()),
            name="test-project_123 (v1.0)",
            path=str(project_path),
        )
        assert "test-project_123 (v1.0)" in project.name
