"""
Block assembler protocol for draining raw findings into published blocks.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from code_analysis.core.search_session.atomic_publication import atomic_write_bytes
from code_analysis.core.search_session.directory import SearchSessionDirectoryLayout
from code_analysis.core.search_session.raw_finding_buffer import RawFindingBuffer
from code_analysis.core.search_session.result_block import (
    assemble_block,
    serialize_block,
)

COMPLETENESS_RUNNING = "search_still_running"

_BLOCK_NAME_PATTERN = re.compile(r"^block_(\d+)\.json$")


class BlockAssembler:
    """
    Drains ``RawFindingBuffer`` into immutable result blocks under a buffer lock.
    """

    def __init__(
        self,
        layout: SearchSessionDirectoryLayout,
        buffer: RawFindingBuffer,
        max_block_size_bytes: int,
        *,
        append_index_entry: Callable[[int, str], None],
        update_manifest_metrics: Callable[[dict], None],
        finalize_index: Callable[[], None],
    ) -> None:
        self._layout = layout
        self._buffer = buffer
        self._max_block_size_bytes = max_block_size_bytes
        self._append_index_entry = append_index_entry
        self._update_manifest_metrics = update_manifest_metrics
        self._finalize_index = finalize_index

    def run_once(self, *, search_completed: bool) -> int:
        """
        Acquire the buffer lock once and publish as many blocks as allowed.

        Returns:
            Number of blocks published; ``0`` when the lock is unavailable or no
            work is performed.
        """
        if not self._buffer.buffer_dir.exists():
            return 0
        if not self._buffer.try_acquire_lock():
            return 0

        blocks_published = 0
        try:
            while True:
                volume = self._buffer.total_bytes()
                if not search_completed and volume < self._max_block_size_bytes:
                    break
                if volume == 0:
                    if search_completed:
                        self._finalize_if_empty()
                    break

                finding_paths = self._buffer.list_findings()
                findings = [self._load_finding(path) for path in finding_paths]
                position = self._next_block_position()
                block = assemble_block(
                    findings,
                    max_block_size_bytes=self._max_block_size_bytes,
                    position=position,
                )
                if not block.results:
                    break

                assembled_count = len(block.results)
                assembled_paths = finding_paths[:assembled_count]
                block_path = self._layout.blocks_dir / f"block_{block.position}.json"
                atomic_write_bytes(block_path, serialize_block(block))
                self._append_index_entry(block.position, COMPLETENESS_RUNNING)
                self._update_manifest_metrics(
                    {
                        "produced_results": assembled_count,
                        "written_blocks": 1,
                        "block_size_bytes": block.serialized_size_bytes,
                    }
                )
                self._buffer.remove_findings(assembled_paths)
                blocks_published += 1

                if search_completed and self._buffer.total_bytes() == 0:
                    self._finalize_if_empty()
                    break

                if (
                    not search_completed
                    and self._buffer.total_bytes() < self._max_block_size_bytes
                ):
                    break
        finally:
            self._buffer.release_lock()

        return blocks_published

    def run_until_idle(self, *, search_completed: bool) -> int:
        """Repeatedly run ``run_once`` until it publishes no blocks."""
        total = 0
        while True:
            published = self.run_once(search_completed=search_completed)
            if published == 0:
                break
            total += published
            if search_completed and not self._buffer.buffer_dir.exists():
                break
        return total

    def _finalize_if_empty(self) -> None:
        if self._buffer.total_bytes() != 0:
            return
        self._finalize_index()
        self._buffer.delete_buffer()

    def _next_block_position(self) -> int:
        highest = 0
        if self._layout.blocks_dir.is_dir():
            for path in self._layout.blocks_dir.iterdir():
                match = _BLOCK_NAME_PATTERN.match(path.name)
                if match is not None:
                    highest = max(highest, int(match.group(1)))
        return highest + 1

    @staticmethod
    def _load_finding(path: Path) -> dict:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError(f"Finding payload must be a JSON object: {path}")
        return payload
