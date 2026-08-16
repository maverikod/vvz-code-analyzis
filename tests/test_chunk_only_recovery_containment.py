"""
Tests for bug e548fcc0: process_chunk_only_files must contain per-chunk
embed exceptions raised INSIDE recover_unvectorized_by_neighbor_merge, not
let them propagate to the outer except in process_chunk_only_files.

Before the fix, a chunk whose embed_one call RAISES during neighbor-merge
recovery (instead of returning a soft miss (None, None)) blew past the
recovery function entirely and hit the outer except in
process_chunk_only_files, which does ``error_count += missing_before_recovery;
continue`` on the FILE loop. That ``continue`` skips the commit block, so a
file's OTHER sub-batches that already embedded successfully were silently
discarded (never written), the attempts-map/dead-letter accounting never ran
for the failing chunks (they retried forever), and the file was reprocessed
from scratch on every cycle.

After the fix, an embed_one exception raised for one merge-window attempt
during recovery is caught right there and treated identically to a soft miss
(None, None): the merge window keeps growing/retrying as it already does for
soft misses, and if no window ever produces a vector the chunk is simply left
unresolved. The file therefore always reaches the commit block with whatever
sub-batches succeeded, and the existing attempts/dead-letter accounting sees
the unresolved chunks like it does for any other unrecoverable chunk.

Live-repro limitation: this defect requires making the embed service RAISE
(not just return empty results) mid-file, specifically during the
neighbor-merge recovery retry of a subset of a file's chunks after an earlier
sub-batch already committed successfully. There is no supported way to force
the real embed service into that failure mode against the live server (its
failure modes are network-level and untimed), so this defect is not safely
reproducible end-to-end; the covering check here is a unit-level regression
test against fake DB/SVO-manager doubles that deterministically reproduce the
exception-during-recovery condition. This is the same limitation pattern
documented in test_vectorization_embed_batch_cap.py for the sibling
16b1abbe/e548fcc0 family of chunk_only recovery defects.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from embed_client.exceptions import EmbedClientError

from code_analysis.core.vectorization_worker_pkg.batch_processor import (
    VECTORIZATION_DEAD_LETTER_SKIPPED_VALUE,
    process_chunk_only_files,
)

_CAP = 20
_TOTAL_CHUNKS = 25
_POISONED_COUNT = 5


class _FakeDatabase:
    """Fake database with one file that has _TOTAL_CHUNKS un-vectorized chunks.

    Unfiltered by design (mirrors tests/test_vectorization_dead_letter.py's
    ``_FakeChunkOnlyDatabase``): the SELECT/GROUP-BY queries always return the
    full original chunk set regardless of prior commits, so calling
    ``process_chunk_only_files`` again on the same instance simulates a fresh
    retry pass while the persistent ``worker._chunk_only_attempts`` map (set
    on the same worker object across calls) tracks attempt counts exactly as
    the real driver loop would across polling cycles.
    """

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        """Initialize the instance."""
        self.chunks = chunks
        self.logical_writes: list[dict[str, Any]] = []
        self.batch_writes: list[list[Any]] = []
        self.dead_letters: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: Any = None, **_kwargs: Any) -> dict[str, Any]:
        """Execute the command."""
        if "GROUP BY cc.file_id" in sql:
            return {
                "data": [
                    {
                        "file_id": "file-1",
                        "file_path": "big_file.py",
                        "cnt": len(self.chunks),
                    }
                ]
            }
        if "SET vectorization_skipped = ?" in sql:
            self.dead_letters.append(tuple(params))
            return {"data": []}
        return {"data": self.chunks}

    def execute_logical_write_operation(self, payload: dict[str, Any]) -> None:
        """Return execute logical write operation."""
        self.logical_writes.append(payload)

    def execute_batch(self, ops: list[Any], **_kwargs: Any) -> None:
        """Return execute batch."""
        self.batch_writes.append(ops)


class _PoisonedSvoManager:
    """SVO manager double where the tail chunks RAISE on every attempt.

    Poisoning is keyed on substring markers baked into the chunk text (not
    chunk id), because neighbor-merge recovery re-embeds via a synthetic
    single-item ``EmbeddingInput(id="__merged__")`` whose id never matches
    the original chunk id, but whose text is the concatenation of the
    original chunks' text, so the marker substring survives every merge
    window. This guarantees the poisoned chunks RAISE on every recovery
    retry regardless of how wide the neighbor-merge window grows -- exactly
    the "raises instead of a soft miss" condition the fix must contain.
    """

    def __init__(self, cap: int = _CAP) -> None:
        """Initialize the instance."""
        self.cap = cap
        self._embedding_available = True
        self._embedding_max_batch_size = cap
        self.call_sizes: list[int] = []

    async def get_embeddings(self, chunks: list[Any]) -> list[Any]:
        """Return get embeddings, raising for any call touching a poisoned chunk."""
        self.call_sizes.append(len(chunks))
        if any("POISON" in getattr(c, "text", "") for c in chunks):
            raise EmbedClientError("embed-service rejected poisoned chunk")
        for chunk in chunks:
            chunk.embedding = [1.0]
            chunk.embedding_model = "fake-model"
        return chunks


class _TransientOnceSvoManager:
    """SVO manager double whose tail sub-batch fails exactly once, then recovers.

    Models a genuine transient failure (e.g. one dropped connection), as
    opposed to a permanently poisoned chunk: the bulk sub-batch call fails a
    single time, but every subsequent call (including the neighbor-merge
    recovery retries the fix now runs for that sub-batch's chunks) succeeds.
    This is the "still healthy" case the fix must not regress: recovery must
    still fully resolve a file when the embed service comes back.
    """

    def __init__(self, cap: int = _CAP) -> None:
        """Initialize the instance."""
        self.cap = cap
        self._embedding_available = True
        self._embedding_max_batch_size = cap
        self.call_sizes: list[int] = []
        self._tail_batch_failed_once = False

    async def get_embeddings(self, chunks: list[Any]) -> list[Any]:
        """Return get embeddings, failing the first multi-item tail call only."""
        self.call_sizes.append(len(chunks))
        if len(chunks) > 1 and not self._tail_batch_failed_once:
            self._tail_batch_failed_once = True
            raise EmbedClientError("transient embed-service failure")
        for chunk in chunks:
            chunk.embedding = [1.0]
            chunk.embedding_model = "fake-model"
        return chunks


def _worker(manager: Any, retry_attempts: int = 2) -> SimpleNamespace:
    """Return a minimal worker double for process_chunk_only_files."""
    return SimpleNamespace(
        chunk_only=True,
        svo_client_manager=manager,
        project_id="project-1",
        max_files_per_pass=30,
        docs_markdown_embeddings_enabled=True,
        retry_attempts=retry_attempts,
        _stop_event=MagicMock(is_set=MagicMock(return_value=False)),
    )


def _chunks_with_tail_poisoned() -> list[dict[str, Any]]:
    """Return 25 chunk rows where the last 5 carry a POISON marker in their text."""
    rows = []
    for i in range(_TOTAL_CHUNKS):
        if i >= _TOTAL_CHUNKS - _POISONED_COUNT:
            text = f"POISON{i} unrecoverable chunk text {i}"
        else:
            text = f"chunk text {i}"
        rows.append({"id": f"c{i}", "chunk_text": text})
    return rows


@pytest.mark.asyncio
async def test_poisoned_recovery_chunks_do_not_discard_sibling_success() -> None:
    """A raised embed_one during recovery must not discard the file's committed subset.

    25 chunks, cap=20: the first 20-chunk sub-batch embeds cleanly; the tail
    5-chunk sub-batch is poisoned so both the raw STEP 3 call and every
    neighbor-merge recovery retry for those 5 chunks RAISE. FIXED behavior:
    - Pass 1: the 20 successful embeddings still commit (updated == 20), the
      5 poisoned chunks are counted as errors (errors == 5) instead of being
      lost via the outer except's early ``continue``, and each poisoned
      chunk's attempts counter is incremented exactly once this pass.
    - Pass 2 (retry_attempts=2): the poisoned chunks' attempts counter
      reaches the cap and they are dead-lettered (vectorization_skipped=2
      UPDATE issued for each), matching how any other unresolved chunk is
      dead-lettered.

    Before the fix this asserted the opposite of what actually happens:
    the recovery exception propagates to process_chunk_only_files' outer
    except, which does ``error_count += missing_before_recovery; continue``
    BEFORE the commit block -- so updated == 0 (the 20 successful embeddings
    are silently discarded every pass) and the attempts map is never
    populated (infinite retry, no dead-letter ever fires).
    """
    db = _FakeDatabase(_chunks_with_tail_poisoned())
    manager = _PoisonedSvoManager(cap=_CAP)
    worker = _worker(manager, retry_attempts=2)

    # --- Pass 1 ---
    updated1, errors1 = await process_chunk_only_files(worker, db)

    assert (updated1, errors1) == (20, 5)
    poisoned_ids = [f"c{i}" for i in range(20, 25)]
    for cid in poisoned_ids:
        assert worker._chunk_only_attempts.get(cid) == 1, (
            f"expected attempts==1 for {cid} after pass 1, got "
            f"{worker._chunk_only_attempts.get(cid)!r}"
        )
    assert db.dead_letters == []

    # --- Pass 2: attempts reach retry_attempts(2) -> dead-lettered. ---
    updated2, errors2 = await process_chunk_only_files(worker, db)

    assert errors2 == 5
    dead_lettered_ids = {params[1] for params in db.dead_letters}
    assert dead_lettered_ids == set(poisoned_ids)
    for params in db.dead_letters:
        assert params[0] == VECTORIZATION_DEAD_LETTER_SKIPPED_VALUE
    for cid in poisoned_ids:
        assert cid not in worker._chunk_only_attempts


@pytest.mark.asyncio
async def test_transient_recovery_failure_still_fully_resolves_file() -> None:
    """A one-off transient failure (not permanently poisoned) still fully recovers.

    25 chunks, cap=20: the tail 5-chunk sub-batch raises once (transient),
    but every later call -- including this fix's per-chunk-contained
    neighbor-merge recovery retries -- succeeds. The file must still end up
    fully embedded (updated == 25, errors == 0): containing the recovery
    exception must not make genuinely-recoverable chunks worse off.
    """
    db = _FakeDatabase(
        [{"id": f"c{i}", "chunk_text": f"chunk text {i}"} for i in range(_TOTAL_CHUNKS)]
    )
    manager = _TransientOnceSvoManager(cap=_CAP)

    updated, errors = await process_chunk_only_files(_worker(manager), db)

    assert (updated, errors) == (_TOTAL_CHUNKS, 0)
