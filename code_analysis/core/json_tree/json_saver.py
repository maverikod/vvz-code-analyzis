"""
Save JSON tree to file with backup and DB file_data update (non-CST path).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from ..backup_manager import BackupManager
from ..database_client.file_data_batch import update_file_data_atomic_batch
from ..database_client.objects.base import BaseObject
from ..database_client.objects.file import File
from ..database.file_edit_lock import (
    acquire_file_edit_lock_with_retry,
    release_file_edit_lock,
)
from ..file_lock import file_lock
from ..path_normalization import normalize_path_simple
from .tree_builder import get_tree

logger = logging.getLogger(__name__)
# @node-id: 5d2e5086-8594-49cc-b44b-ec0c9a9517a4


def _serialize_document(root_data: Any) -> str:
    return json.dumps(root_data, indent=2, ensure_ascii=False) + "\n"
update_result = update_file_data_atomic_batch(
    database=database,
    file_id=str(file_id),
    project_id=project_id,
    source_code=source_code,
    file_path=str(target_path),
    file_mtime=file_mtime,
    transaction_id=transaction_id,
    skip_file_edit_lock=True,
)
