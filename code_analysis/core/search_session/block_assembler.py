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
from code_analysis.core.search_session.result_index import (
    COMPLETENESS_FINISHED,
    mark_index_finished,
    read_index,
)

COMPLETENESS_RUNNING = "search_still_running"

_BLOCK_NAME_PATTERN = re.compile(r"^block_(\d+)\.json$")


class BlockAssembler:
    """
    Drains ``RawFindingBuffer`` into immutable result blocks under a buffer lock.

    Temporal blocks are written in arrival order while the search runs.
    On completion, all findings are re-segmented by relevance score into a
    separate ``blocks_relevance/`` set.
    """

    def __init__(
        self,
        layout: SearchSessionDirectoryLayout,
        buffer: RawFindingBuffer,
        max_block_size_bytes: int,
        *,
        max_results_per_block: int | None = None,
        append_index_entry: Callable[[int, str], None],
        update_manifest_metrics: Callable[[dict], None],
        on_block_published: Callable[[int, int, int], None] | None = None,
    ) -> None:
        """Initialize the instance."""
        self._layout = layout
        self._buffer = buffer
        self._max_block_size_bytes = max_block_size_bytes
        self._max_results_per_block = max_results_per_block
        self._append_index_entry = append_index_entry
        self._update_manifest_metrics = update_manifest_metrics
        self._on_block_published = on_block_published

    def run_once(self, *, search_completed: bool) -> int:
        """
        Acquire the buffer lock once and publish as many temporal blocks as
        allowed.  On ``search_completed`` also triggers re-segmentation and
        finalizes the index.

        Returns:
            Number of blocks published; ``0`` when the lock is unavailable,
            already finished, or no work is performed.
        """
        if not self._buffer.buffer_dir.exists():
            return 0

        # Idempotent guard: if index is already finished, nothing to do.
        if self._layout.index_path.is_file():
            try:
                idx = read_index(self._layout.index_path)
                if idx.completeness == COMPLETENESS_FINISHED:
                    return 0
            except Exception:
                pass

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
                        self._finalize()
                    break

                finding_paths = self._buffer.list_findings()
                findings = [self._load_finding(path) for path in finding_paths]
                position = self._next_block_position()
                block = assemble_block(
                    findings,
                    max_block_size_bytes=self._max_block_size_bytes,
                    max_results=self._max_results_per_block,
                    position=position,
                )
                if not block.items:
                    break

                assembled_count = len(block.items)
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
                self._buffer.remove_findings(finding_paths[:assembled_count])
                blocks_published += 1
                if self._on_block_published is not None:
                    self._on_block_published(
                        block.position,
                        assembled_count,
                        block.serialized_size_bytes,
                    )

                if search_completed and self._buffer.total_bytes() == 0:
                    self._finalize()
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

    def _finalize(self) -> None:
        """
        One-way finalization: re-segment all findings by relevance, write
        ``blocks_relevance/``, call ``mark_index_finished``, delete buffer.

        Safe to call when buffer is empty (zero findings -> empty relevance set).
        """
        relevance_entries = self._build_relevance_blocks()
        if self._layout.index_path.is_file():
            mark_index_finished(
                self._layout.index_path,
                relevance_blocks=relevance_entries,
            )
        else:
            from code_analysis.core.search_session.atomic_publication import (
                atomic_write_json,
            )

            atomic_write_json(
                self._layout.index_path,
                {
                    "blocks": [],
                    "completeness": COMPLETENESS_FINISHED,
                    "temporal_blocks": [],
                    "relevance_blocks": relevance_entries,
                },
            )
        self._buffer.delete_buffer()

    def _build_relevance_blocks(self) -> list[dict]:
        """
        Read all findings from the buffer, sort by relevance, and write
        ``blocks_relevance/`` files.  Returns the list of index entries
        ``{position, size_bytes}`` for the relevance set.
        """
        if not self._buffer.buffer_dir.exists():
            return []

        finding_paths = self._buffer.list_findings()
        if not finding_paths:
            return []

        findings = [self._load_finding(p) for p in finding_paths]

        def _sort_key(f: dict) -> tuple:
            """Return sort key."""
            score = f.get("score")
            score_val = -float(score) if score is not None else 0.0
            result_id = str(f.get("result_id") or "")
            return (score_val, result_id)

        findings.sort(key=_sort_key)

        relevance_dir = self._layout.relevance_blocks_dir
        relevance_dir.mkdir(parents=True, exist_ok=True)

        entries: list[dict] = []
        position = 0
        remaining = findings
        while remaining:
            position += 1
            block = assemble_block(
                remaining,
                max_block_size_bytes=self._max_block_size_bytes,
                max_results=self._max_results_per_block,
                position=position,
            )
            if not block.items:
                break
            block_path = relevance_dir / f"block_{block.position}.json"
            data = serialize_block(block)
            atomic_write_bytes(block_path, data)
            entries.append({"position": position, "size_bytes": len(data)})
            remaining = remaining[len(block.items) :]

        return entries

    def _next_block_position(self) -> int:
        """Return next block position."""
        highest = 0
        if self._layout.blocks_dir.is_dir():
            for path in self._layout.blocks_dir.iterdir():
                match = _BLOCK_NAME_PATTERN.match(path.name)
                if match is not None:
                    highest = max(highest, int(match.group(1)))
        return highest + 1

    @staticmethod
    def _load_finding(path: Path) -> dict:
        """Return load finding."""
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError(f"Finding payload must be a JSON object: {path}")
        return payload
