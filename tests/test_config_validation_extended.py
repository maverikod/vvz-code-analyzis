"""
Extended tests for configuration validation to achieve 90%+ coverage.

Tests cover:
- ConfigManager methods (add_project, remove_project, update_project, etc.)
- generate_config edge cases
- Error handling paths
- Cache behavior
"""

import json
import pytest
import tempfile
import uuid
from pathlib import Path

from code_analysis.core.config import (
    ServerConfig,
    ProjectDir,
    SVOServiceConfig,
    generate_config,
    save_config,
    load_config,
)
from code_analysis.core.config_manager import ConfigManager, validate_config


class TestConfigManagerExtended:
    """Extended tests for ConfigManager methods."""

    def test_add_project(self, tmp_path):
        """Test add_project method."""
        config_file = tmp_path / "config.json"
        project_path = tmp_path / "project"
        project_path.mkdir()
        
        manager = ConfigManager(config_file)
        project_id = manager.add_project("test", str(project_path))
        
        assert project_id is not None
        config = manager.read()
        assert len(config.dirs) == 1
        assert config.dirs[0].name == "test"

    def test_add_project_with_custom_id(self, tmp_path):
        """Test add_project with custom UUID."""
        config_file = tmp_path / "config.json"
        project_path = tmp_path / "project"
        project_path.mkdir()
        custom_id = str(uuid.uuid4())
        
        manager = ConfigManager(config_file)
        project_id = manager.add_project("test", str(project_path), project_id=custom_id)
        
        assert project_id == custom_id
        project = manager.get_project(custom_id)
        assert project is not None
        assert project.name == "test"

    def test_add_project_duplicate_name(self, tmp_path):
        """Test add_project with duplicate name."""
        config_file = tmp_path / "config.json"
        project_path = tmp_path / "project"
        project_path.mkdir()
        
        manager = ConfigManager(config_file)
        manager.add_project("test", str(project_path))
        
        with pytest.raises(ValueError, match="already exists"):
            manager.add_project("test", str(project_path))

    def test_add_project_duplicate_id(self, tmp_path):
        """Test add_project with duplicate ID."""
        config_file = tmp_path / "config.json"
        project_path = tmp_path / "project"
        project_path.mkdir()
        project_id = str(uuid.uuid4())
        
        manager = ConfigManager(config_file)
        manager.add_project("test1", str(project_path), project_id=project_id)
        
        with pytest.raises(ValueError, match="already exists"):
            manager.add_project("test2", str(project_path), project_id=project_id)

    def test_add_project_invalid_path(self, tmp_path):
        """Test add_project with invalid path."""
        config_file = tmp_path / "config.json"
        nonexistent = tmp_path / "nonexistent"
        
        manager = ConfigManager(config_file)
        with pytest.raises(ValueError, match="Path does not exist"):
            manager.add_project("test", str(nonexistent))

    def test_add_project_relative_path(self, tmp_path):
        """Test add_project with relative path."""
        config_file = tmp_path / "config.json"
        
        manager = ConfigManager(config_file)
        with pytest.raises(ValueError, match="Path must be absolute"):
            manager.add_project("test", "relative/path")

    def test_add_project_invalid_uuid(self, tmp_path):
        """Test add_project with invalid UUID format."""
        config_file = tmp_path / "config.json"
        project_path = tmp_path / "project"
        project_path.mkdir()
        
        manager = ConfigManager(config_file)
        with pytest.raises(ValueError, match="Invalid UUID"):
            manager.add_project("test", str(project_path), project_id="not-a-uuid")

    def test_remove_project(self, tmp_path):
        """Test remove_project method."""
        config_file = tmp_path / "config.json"
        project_path = tmp_path / "project"
        project_path.mkdir()
        
        manager = ConfigManager(config_file)
        project_id = manager.add_project("test", str(project_path))
        
        result = manager.remove_project(project_id)
        assert result is True
        
        config = manager.read()
        assert len(config.dirs) == 0

    def test_remove_project_nonexistent(self, tmp_path):
        """Test remove_project with nonexistent project."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"host": "127.0.0.1", "port": 15000, "dirs": []}')
        
        manager = ConfigManager(config_file)
        result = manager.remove_project(str(uuid.uuid4()))
        assert result is False

    def test_remove_project_invalid_uuid(self, tmp_path):
        """Test remove_project with invalid UUID."""
        config_file = tmp_path / "config.json"
        
        manager = ConfigManager(config_file)
        with pytest.raises(ValueError, match="Invalid UUID"):
            manager.remove_project("not-a-uuid")

    def test_remove_project_no_config_file(self, tmp_path):
        """Test remove_project when config file doesn't exist."""
        config_file = tmp_path / "nonexistent.json"
        
        manager = ConfigManager(config_file)
        result = manager.remove_project(str(uuid.uuid4()))
        assert result is False

    def test_update_project(self, tmp_path):
        """Test update_project method."""
        config_file = tmp_path / "config.json"
        project_path = tmp_path / "project"
        project_path.mkdir()
        new_path = tmp_path / "new_project"
        new_path.mkdir()
        
        manager = ConfigManager(config_file)
        project_id = manager.add_project("test", str(project_path))
        
        result = manager.update_project(project_id, name="updated", path=str(new_path))
        assert result is True
        
        project = manager.get_project(project_id)
        assert project.name == "updated"
        assert project.path == str(new_path.resolve())

    def test_update_project_name_only(self, tmp_path):
        """Test update_project with name only."""
        config_file = tmp_path / "config.json"
        project_path = tmp_path / "project"
        project_path.mkdir()
        
        manager = ConfigManager(config_file)
        project_id = manager.add_project("test", str(project_path))
        
        result = manager.update_project(project_id, name="updated")
        assert result is True
        
        project = manager.get_project(project_id)
        assert project.name == "updated"
        assert project.path == str(project_path.resolve())  # Path unchanged

    def test_update_project_path_only(self, tmp_path):
        """Test update_project with path only."""
        config_file = tmp_path / "config.json"
        project_path = tmp_path / "project"
        project_path.mkdir()
        new_path = tmp_path / "new_project"
        new_path.mkdir()
        
        manager = ConfigManager(config_file)
        project_id = manager.add_project("test", str(project_path))
        
        result = manager.update_project(project_id, path=str(new_path))
        assert result is True
        
        project = manager.get_project(project_id)
        assert project.name == "test"  # Name unchanged
        assert project.path == str(new_path.resolve())

    def test_update_project_nonexistent(self, tmp_path):
        """Test update_project with nonexistent project."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"host": "127.0.0.1", "port": 15000, "dirs": []}')
        
        manager = ConfigManager(config_file)
        result = manager.update_project(str(uuid.uuid4()), name="test")
        assert result is False

    def test_update_project_duplicate_name(self, tmp_path):
        """Test update_project with duplicate name."""
        config_file = tmp_path / "config.json"
        project_path1 = tmp_path / "project1"
        project_path1.mkdir()
        project_path2 = tmp_path / "project2"
        project_path2.mkdir()
        
        manager = ConfigManager(config_file)
        project_id1 = manager.add_project("project1", str(project_path1))
        project_id2 = manager.add_project("project2", str(project_path2))
        
        with pytest.raises(ValueError, match="already exists"):
            manager.update_project(project_id2, name="project1")

    def test_update_project_invalid_path(self, tmp_path):
        """Test update_project with invalid path."""
        config_file = tmp_path / "config.json"
        project_path = tmp_path / "project"
        project_path.mkdir()
        
        manager = ConfigManager(config_file)
        project_id = manager.add_project("test", str(project_path))
        
        with pytest.raises(ValueError, match="Path does not exist"):
            manager.update_project(project_id, path=str(tmp_path / "nonexistent"))

    def test_update_project_relative_path(self, tmp_path):
        """Test update_project with relative path."""
        config_file = tmp_path / "config.json"
        project_path = tmp_path / "project"
        project_path.mkdir()
        
        manager = ConfigManager(config_file)
        project_id = manager.add_project("test", str(project_path))
        
        with pytest.raises(ValueError, match="Path must be absolute"):
            manager.update_project(project_id, path="relative/path")

    def test_update_project_invalid_uuid(self, tmp_path):
        """Test update_project with invalid UUID."""
        config_file = tmp_path / "config.json"
        
        manager = ConfigManager(config_file)
        with pytest.raises(ValueError, match="Invalid UUID"):
            manager.update_project("not-a-uuid", name="test")

    def test_update_project_no_config_file(self, tmp_path):
        """Test update_project when config file doesn't exist."""
        config_file = tmp_path / "nonexistent.json"
        
        manager = ConfigManager(config_file)
        result = manager.update_project(str(uuid.uuid4()), name="test")
        assert result is False

    def test_get_project(self, tmp_path):
        """Test get_project method."""
        config_file = tmp_path / "config.json"
        project_path = tmp_path / "project"
        project_path.mkdir()
        project_id = str(uuid.uuid4())
        
        config_data = {
            "host": "127.0.0.1",
            "port": 15000,
            "dirs": [
                {
                    "id": project_id,
                    "name": "test",
                    "path": str(project_path),
                }
            ],
        }
        config_file.write_text(json.dumps(config_data))
        
        manager = ConfigManager(config_file)
        project = manager.get_project(project_id)
        assert project is not None
        assert project.name == "test"
        
        # Test with invalid UUID
        project = manager.get_project("invalid")
        assert project is None

    def test_get_project_nonexistent(self, tmp_path):
        """Test get_project with nonexistent project ID."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"host": "127.0.0.1", "port": 15000, "dirs": []}')
        
        manager = ConfigManager(config_file)
        project = manager.get_project(str(uuid.uuid4()))
        assert project is None

    def test_get_project_no_config_file(self, tmp_path):
        """Test get_project when config file doesn't exist."""
        config_file = tmp_path / "nonexistent.json"
        
        manager = ConfigManager(config_file)
        project = manager.get_project(str(uuid.uuid4()))
        assert project is None

    def test_list_projects(self, tmp_path):
        """Test list_projects method."""
        config_file = tmp_path / "config.json"
        project_path1 = tmp_path / "project1"
        project_path1.mkdir()
        project_path2 = tmp_path / "project2"
        project_path2.mkdir()
        
        manager = ConfigManager(config_file)
        manager.add_project("project1", str(project_path1))
        manager.add_project("project2", str(project_path2))
        
        projects = manager.list_projects()
        assert len(projects) == 2
        names = [p.name for p in projects]
        assert "project1" in names
        assert "project2" in names

    def test_list_projects_empty(self, tmp_path):
        """Test list_projects with empty config."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"host": "127.0.0.1", "port": 15000, "dirs": []}')
        
        manager = ConfigManager(config_file)
        projects = manager.list_projects()
        assert len(projects) == 0

    def test_list_projects_no_config_file(self, tmp_path):
        """Test list_projects when config file doesn't exist."""
        config_file = tmp_path / "nonexistent.json"
        
        manager = ConfigManager(config_file)
        projects = manager.list_projects()
        assert len(projects) == 0

    def test_write_config(self, tmp_path):
        """Test write method."""
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        
        from code_analysis.core.config import ServerConfig
        config = ServerConfig(host="127.0.0.1", port=8080)
        manager.write(config)
        
        assert config_file.exists()
        read_config = manager.read()
        assert read_config.host == "127.0.0.1"
        assert read_config.port == 8080

    def test_read_caches_config(self, tmp_path):
        """Test that read caches config."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"host": "127.0.0.1", "port": 15000}')
        
        manager = ConfigManager(config_file)
        config1 = manager.read()
        config2 = manager.read()
        
        # Should have same values (may not be same object due to validation)
        assert config1.host == config2.host
        assert config1.port == config2.port
        # Check that _config attribute is set (cached)
        assert manager._config is not None

    def test_write_clears_cache(self, tmp_path):
        """Test that write clears cache."""
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        
        from code_analysis.core.config import ServerConfig
        config1 = ServerConfig(host="127.0.0.1", port=15000)
        manager.write(config1)
        
        # Read should get new config
        config2 = manager.read()
        assert config2.host == "127.0.0.1"


class TestGenerateConfigExtended:
    """Extended tests for generate_config function."""

    def test_generate_config_with_dirs(self, tmp_path):
        """Test generate_config with project directories."""
        project_path = tmp_path / "project"
        project_path.mkdir()
        
        config = generate_config(
            host="127.0.0.1",
            port=8080,
            dirs=[{"name": "test", "path": str(project_path)}],
        )
        
        assert config["host"] == "127.0.0.1"
        assert config["port"] == 8080
        assert len(config["dirs"]) == 1
        assert config["dirs"][0]["name"] == "test"
        assert "id" in config["dirs"][0]

    def test_generate_config_with_log_and_db(self, tmp_path):
        """Test generate_config with log and db paths."""
        log_path = tmp_path / "log.txt"
        db_path = tmp_path / "db.db"
        
        config = generate_config(
            log=str(log_path),
            db_path=str(db_path),
        )
        
        assert config["log"] == str(log_path.resolve())
        assert config["db_path"] == str(db_path.resolve())
        assert log_path.parent.exists()
        assert db_path.parent.exists()

    def test_generate_config_with_mtls(self, tmp_path):
        """Test generate_config with mTLS certificates."""
        config = generate_config(
            chunker_host="chunker.local",
            chunker_port=9000,
            embedding_host="embedding.local",
            embedding_port=9001,
            mtls_certificates={
                "cert": "/path/to/cert.pem",
                "key": "/path/to/key.pem",
            },
        )
        
        assert "chunker" in config
        assert "embedding" in config
        assert config["chunker"]["enabled"] is True
        assert config["chunker"]["host"] == "chunker.local"
        assert config["chunker"]["port"] == 9000
        assert config["embedding"]["enabled"] is True
        assert config["embedding"]["host"] == "embedding.local"
        assert config["embedding"]["port"] == 9001

    def test_generate_config_nonexistent_path(self, tmp_path):
        """Test generate_config with nonexistent project path."""
        nonexistent = tmp_path / "nonexistent"
        
        with pytest.raises(ValueError, match="Path does not exist"):
            generate_config(dirs=[{"name": "test", "path": str(nonexistent)}])

    def test_generate_config_file_path(self, tmp_path):
        """Test generate_config with file instead of directory."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        
        with pytest.raises(ValueError, match="not a directory"):
            generate_config(dirs=[{"name": "test", "path": str(test_file)}])

    def test_generate_config_multiple_dirs(self, tmp_path):
        """Test generate_config with multiple directories."""
        project_path1 = tmp_path / "project1"
        project_path1.mkdir()
        project_path2 = tmp_path / "project2"
        project_path2.mkdir()
        
        config = generate_config(
            dirs=[
                {"name": "project1", "path": str(project_path1)},
                {"name": "project2", "path": str(project_path2)},
            ],
        )
        
        assert len(config["dirs"]) == 2
        assert config["dirs"][0]["name"] == "project1"
        assert config["dirs"][1]["name"] == "project2"

    def test_generate_config_dir_without_name(self, tmp_path):
        """Test generate_config with dir without explicit name."""
        project_path = tmp_path / "my_project"
        project_path.mkdir()
        
        config = generate_config(
            dirs=[{"path": str(project_path)}],
        )
        
        assert len(config["dirs"]) == 1
        assert config["dirs"][0]["name"] == "my_project"  # Should use directory name


class TestValidateConfigExtended:
    """Extended tests for validate_config function."""

    def test_validate_config_with_duplicates(self, tmp_path):
        """Test validate_config function with duplicate IDs."""
        project_path = tmp_path / "project"
        project_path.mkdir()
        project_id = str(uuid.uuid4())
        
        config_data = {
            "host": "127.0.0.1",
            "port": 15000,
            "dirs": [
                {"id": project_id, "name": "test1", "path": str(project_path)},
                {"id": project_id, "name": "test2", "path": str(project_path)},
            ],
        }
        
        with pytest.raises(ValueError, match="Duplicate project IDs"):
            validate_config(config_data)

    def test_validate_config_with_duplicate_names(self, tmp_path):
        """Test validate_config function with duplicate names."""
        project_path = tmp_path / "project"
        project_path.mkdir()
        
        config_data = {
            "host": "127.0.0.1",
            "port": 15000,
            "dirs": [
                {"id": str(uuid.uuid4()), "name": "test", "path": str(project_path)},
                {"id": str(uuid.uuid4()), "name": "test", "path": str(project_path)},
            ],
        }
        
        with pytest.raises(ValueError, match="Duplicate project names"):
            validate_config(config_data)

    def test_validate_config_unknown_field(self, tmp_path):
        """Test validate_config with unknown field."""
        config_data = {
            "host": "127.0.0.1",
            "port": 15000,
            "unknown_field": "value",
        }
        
        with pytest.raises(ValueError, match="unknown"):
            validate_config(config_data)

    def test_validate_config_invalid_port(self):
        """Test validate_config with invalid port."""
        config_data = {
            "host": "127.0.0.1",
            "port": 70000,
        }
        
        with pytest.raises(ValueError):
            validate_config(config_data)


class TestSaveLoadConfig:
    """Tests for save_config and load_config functions."""

    def test_save_config(self, tmp_path):
        """Test save_config function."""
        config_file = tmp_path / "config.json"
        
        config = {"host": "127.0.0.1", "port": 15000}
        save_config(config, config_file)
        
        assert config_file.exists()
        data = json.loads(config_file.read_text())
        assert data["host"] == "127.0.0.1"

    def test_save_config_creates_parent_dir(self, tmp_path):
        """Test save_config creates parent directory."""
        config_file = tmp_path / "nested" / "config.json"
        
        config = {"host": "127.0.0.1", "port": 15000}
        save_config(config, config_file)
        
        assert config_file.exists()
        assert config_file.parent.exists()

    def test_load_config_nonexistent_file(self, tmp_path):
        """Test load_config with nonexistent file."""
        config_file = tmp_path / "nonexistent.json"
        
        with pytest.raises(ValueError, match="not found"):
            load_config(config_file)

