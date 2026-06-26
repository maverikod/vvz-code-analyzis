"""
File change processor for file watcher worker.

Implements Step 3 of refactor plan: scan → queue → process phases.
- Scan phase: compute_delta (delegated to processor_delta)
- Queue phase: queue_changes (delegated to processor_queue)
- Process phase: downstream workers consume queued items

Deleted file handling (FILE_TRASH_SPEC step 10):
- When a file disappears from disk, the watcher **hard-deletes** the ``files`` row
  and all dependent index data via ``DatabaseClient.purge_file_ids_cascade``
  (logical write → driver → DB). This includes projects that produced no scan hits
  in a cycle but still have DB rows reconciled in ``compute_delta``.
- No physical move to trash is performed (the file is already gone from disk).
- Explicit "mark for deletion" (``mark_file_deleted``) moves the file to
  ``trash_dir/project_id`` and then sets the soft-delete flag; that path is separate
  from missing-on-disk purge.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from .processor_delta import FileDelta, compute_delta, compute_project_delta
from .processor_queue import ProcessorQueueOps

__all__ = ["FileChangeProcessor", "FileDelta"]


class FileChangeProcessor:
    """
    Processes file changes with separated scan → queue → process phases.

    - compute_delta: Scan phase (no DB operations)
    - queue_changes: Queue phase (batch DB operations)
    - Process phase: handled by downstream workers

    Always works in multi-project mode: discovers projects automatically
    within watched directories.
    """

    def __init__(
        self,
        database: Any,
        watch_dirs: List[Path],
        version_dir: Optional[str] = None,
    ) -> None:
        """Initialize the instance."""
        self.database = database
        self.watch_dirs = watch_dirs
        self.version_dir = version_dir
        self.watch_dirs_resolved = [Path(wd).resolve() for wd in watch_dirs]
        self._queue_ops = ProcessorQueueOps(self.database, self.watch_dirs_resolved)

    def compute_delta(
        self, root_dir: Path, scanned_files: Dict[str, Dict]
    ) -> Dict[str, FileDelta]:
        """Compute file change delta for multiple projects (SCAN PHASE - no DB operations)."""
        return compute_delta(
            self.database,
            self.watch_dirs_resolved,
            root_dir,
            scanned_files,
        )

    def compute_project_delta(
        self,
        project_root: Path,
        project_id: str,
        scanned_files: Dict[str, Dict],
    ) -> FileDelta:
        """Compute delta for one project (scan phase — no DB writes)."""
        return compute_project_delta(
            self.database, project_root, project_id, scanned_files
        )

    def queue_changes(
        self, root_dir: Path, deltas: Dict[str, FileDelta], **kwargs: Any
    ) -> Dict[str, Any]:
        """Queue file changes for multiple projects (QUEUE PHASE - batch DB operations)."""
        return self._queue_ops.queue_changes(root_dir, deltas, **kwargs)

    def queue_project_bulk_sync(
        self,
        project_id: str,
        project_root: Path,
        disk_rows: List[Any],
        *,
        watch_dir_id: Optional[str] = None,
        watcher_coord: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """PostgreSQL bulk queue for one project (manifest built at scan)."""
        return self._queue_ops.queue_project_bulk_sync(
            project_id,
            project_root,
            disk_rows,
            watch_dir_id=watch_dir_id,
            watcher_coord=watcher_coord,
        )

    def process_changes(
        self, root_dir: Path, scanned_files: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """Process file changes (combines scan and queue)."""
        delta = self.compute_delta(root_dir, scanned_files)
        return self.queue_changes(root_dir, delta)
