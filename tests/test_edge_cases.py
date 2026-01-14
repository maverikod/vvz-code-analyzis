"""
Edge case tests for path normalization and project resolution.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import tempfile
import json
import uuid
import threading
from pathlib import Path
from code_analysis.core.path_normalization import normalize_file_path, normalize_path_simple
from code_analysis.core.project_resolution import (
    find_project_root_for_path,
    load_project_info,
)
from code_analysis.core.settings_manager import get_settings
from code_analysis.core.exceptions import (
    ProjectIdError,
    InvalidProjectIdFormatError,
    MultipleProjectIdError,
)


class TestEdgeCasesEmptyPaths:
    """Test edge cases with empty paths."""

    def test_normalize_empty_path(self):
        """Test normalizing empty path."""
        with pytest.raises((ValueError, TypeError)):
            normalize_path_simple("")

    def test_normalize_none_path(self):
        """Test normalizing None path."""
        with pytest.raises((TypeError, AttributeError)):
            normalize_path_simple(None)

    def test_find_project_root_empty_path(self):
        """Test finding project root for empty path."""
        with pytest.raises((ValueError, TypeError)):
            find_project_root_for_path("", [])


class TestEdgeCasesInvalidCharacters:
    """Test edge cases with invalid characters in paths."""

    def test_normalize_path_with_invalid_characters(self):
        """Test normalizing path with invalid characters."""
        # On Windows, some characters are invalid
        invalid_paths = [
            "test<file.py",
            "test>file.py",
            "test:file.py",
            "test\"file.py",
            "test|file.py",
            "test?file.py",
            "test*file.py",
        ]

        for invalid_path in invalid_paths:
            # Should either normalize or raise appropriate error
            try:
                result = normalize_path_simple(invalid_path)
                # If it doesn't raise, result should be valid
                assert result is not None
            except (ValueError, OSError):
                # Expected for invalid characters
                pass


class TestEdgeCasesLongPaths:
    """Test edge cases with very long paths."""

    def test_normalize_very_long_path(self):
        """Test normalizing very long path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create very long path
            long_path = Path(tmpdir)
            for i in range(50):  # Create 50 nested directories
                long_path = long_path / f"dir_{i}"
            long_path.mkdir(parents=True)

            test_file = long_path / "test.py"
            test_file.write_text("# Test\n")

            # Should handle long path
            normalized = normalize_path_simple(str(test_file))
            assert normalized is not None
            assert Path(normalized).exists()

    def test_find_project_root_very_long_path(self):
        """Test finding project root for very long path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project with long path
            long_path = Path(tmpdir)
            for i in range(30):  # Create 30 nested directories
                long_path = long_path / f"dir_{i}"
            long_path.mkdir(parents=True)

            # Create projectid file
            project_id = str(uuid.uuid4())
            projectid_file = long_path / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test"})
            )

            test_file = long_path / "test.py"
            test_file.write_text("# Test\n")

            # Should find project root
            result = find_project_root_for_path(test_file, [Path(tmpdir)])
            assert result is not None
            assert result.root_path == long_path.resolve()


class TestEdgeCasesMultipleDotDot:
    """Test edge cases with multiple .. in paths."""

    def test_normalize_path_with_multiple_dot_dot(self):
        """Test normalizing path with multiple .."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()

            nested = project_root / "nested" / "deep"
            nested.mkdir(parents=True)

            test_file = nested / "test.py"
            test_file.write_text("# Test\n")

            # Path with multiple ..
            relative_path = "../../../project/nested/deep/test.py"
            abs_path = (nested / relative_path).resolve()

            # Should normalize correctly
            normalized = normalize_path_simple(str(abs_path))
            assert normalized is not None
            assert Path(normalized).exists()


class TestEdgeCasesSymbolicLinks:
    """Test edge cases with symbolic links."""

    def test_normalize_path_with_symlink_to_nonexistent(self):
        """Test normalizing path with symlink to nonexistent file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create symlink to nonexistent file
            target = Path(tmpdir) / "nonexistent.py"
            link = Path(tmpdir) / "link.py"

            try:
                link.symlink_to(target)

                # Should handle symlink (may or may not resolve)
                try:
                    normalized = normalize_path_simple(str(link))
                    # If it resolves, should be valid
                    assert normalized is not None
                except (OSError, FileNotFoundError):
                    # Expected for broken symlink
                    pass
            except (OSError, NotImplementedError):
                # Symlinks not supported on this platform
                pytest.skip("Symlinks not supported")


class TestEdgeCasesConcurrentAccess:
    """Test edge cases with concurrent access."""

    def test_concurrent_settings_manager_access(self):
        """Test concurrent access to SettingsManager."""
        settings = get_settings()

        def get_setting():
            for _ in range(100):
                _ = settings.get("max_file_lines")
                _ = settings.poll_interval

        # Create multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=get_setting)
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Should complete without errors
        assert True

    def test_concurrent_project_root_detection(self):
        """Test concurrent project root detection for same file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()

            # Create projectid file
            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test"})
            )

            test_file = project_root / "test.py"
            test_file.write_text("# Test\n")

            watch_dirs = [Path(tmpdir)]

            def find_root():
                for _ in range(50):
                    result = find_project_root_for_path(test_file, watch_dirs)
                    assert result is not None

            # Create multiple threads
            threads = []
            for _ in range(3):
                thread = threading.Thread(target=find_root)
                threads.append(thread)
                thread.start()

            # Wait for all threads
            for thread in threads:
                thread.join()

            # Should complete without errors
            assert True


class TestEdgeCasesCorruptedProjectId:
    """Test edge cases with corrupted projectid files."""

    def test_load_corrupted_projectid_file(self):
        """Test loading corrupted projectid file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()

            # Create corrupted projectid file (invalid JSON)
            projectid_file = project_root / "projectid"
            projectid_file.write_text("{invalid json}")

            # Should raise appropriate error
            with pytest.raises((InvalidProjectIdFormatError, json.JSONDecodeError)):
                load_project_info(project_root)

    def test_load_projectid_file_with_invalid_uuid(self):
        """Test loading projectid file with invalid UUID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()

            # Create projectid file with invalid UUID
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": "not-a-uuid", "description": "Test"})
            )

            # Should raise appropriate error
            with pytest.raises((InvalidProjectIdFormatError, ValueError)):
                load_project_info(project_root)

    def test_load_projectid_file_missing_id_field(self):
        """Test loading projectid file missing id field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()

            # Create projectid file without id field
            projectid_file = project_root / "projectid"
            projectid_file.write_text(json.dumps({"description": "Test"}))

            # Should raise appropriate error
            with pytest.raises((InvalidProjectIdFormatError, KeyError)):
                load_project_info(project_root)


class TestEdgeCasesMissingDirectories:
    """Test edge cases with missing directories."""

    def test_find_project_root_missing_directory(self):
        """Test finding project root for missing directory."""
        nonexistent_path = Path("/nonexistent/path/to/file.py")

        # Should return None or raise appropriate error
        result = find_project_root_for_path(nonexistent_path, [])
        assert result is None

    def test_normalize_path_missing_file(self):
        """Test normalizing path to missing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_file = Path(tmpdir) / "nonexistent.py"

            # Should still normalize (file doesn't need to exist)
            normalized = normalize_path_simple(str(missing_file))
            assert normalized is not None
            assert Path(normalized) == missing_file.resolve()


class TestEdgeCasesFilePermissions:
    """Test edge cases with file permissions."""

    def test_load_projectid_file_no_read_permission(self):
        """Test loading projectid file without read permission."""
        import os
        import stat

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()

            # Create projectid file
            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test"})
            )

            # Remove read permission (if supported)
            try:
                projectid_file.chmod(stat.S_IWRITE)  # Write only

                # Should raise appropriate error
                with pytest.raises((PermissionError, OSError)):
                    load_project_info(project_root)
            except (OSError, NotImplementedError):
                # Permission changes not supported on this platform
                pytest.skip("Permission changes not supported")
            finally:
                # Restore permissions
                try:
                    projectid_file.chmod(stat.S_IREAD | stat.S_IWRITE)
                except (OSError, NotImplementedError):
                    pass

