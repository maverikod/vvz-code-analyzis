"""Universal file save command package."""

from __future__ import annotations

# Re-exports for tests and legacy patch targets (see tests/test_universal_file_save_command.py).
from code_analysis.core.backup_manager import BackupManager
from code_analysis.core.file_handlers.text_handler import (
    persist_plain_text_file_metadata,
)
from code_analysis.core.git_integration import commit_after_write

from code_analysis.commands.universal_file_save_command.save_command import (
    UniversalFileSaveCommand,
)

__all__ = [
    "BackupManager",
    "UniversalFileSaveCommand",
    "commit_after_write",
    "persist_plain_text_file_metadata",
]
