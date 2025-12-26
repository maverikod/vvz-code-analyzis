"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Batch and streaming helpers for FieldArray instances.

Provides utilities that transform block generators into swap-aware
FieldArray objects and expose batch iterators bounded by 80% GPU memory,
enabling Level A sources, solvers, and analyzers to run CUDA workloads
without allocating full tensors at once.

Physical Meaning:
    Keeps 7D phase fields in swap-backed containers while exposing
    iterators that deliver manageable spatial-phase-time chunks to CUDA
    kernels, honoring the 80% GPU memory cap mandated by the project.

Example:
    >>> batches = FieldArrayBatchIterator(field_array).iterate()
    >>> for payload in batches:
    ...     gpu_block = payload["gpu"]
    ...     process(gpu_block)
"""

from __future__ import annotations

import logging
from itertools import product
from typing import (
    TYPE_CHECKING,
    Dict,
    Iterator,
    Optional,
    Sequence,
    Tuple,
)

import numpy as np

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except Exception:  # pragma: no cover - CUDA unavailable on CI
    CUDA_AVAILABLE = False
    cp = None

if TYPE_CHECKING:
    from .field_array import FieldArray
    from ..sources.blocked_field_generator import BlockedFieldGenerator


logger = logging.getLogger(__name__)


def _compute_default_block_shape(
    shape: Tuple[int, ...],
    dtype_size: int,
    max_bytes: int,
    axis_priority: Sequence[int],
) -> Tuple[int, ...]:
    """
    Compute conservative block shape that respects memory limits.
    """

    block_shape = list(shape)
    total_bytes = np.prod(block_shape) * dtype_size
    if total_bytes <= max_bytes:
        return tuple(block_shape)

    # Iteratively shrink least-priority axes until within budget
    priority = list(axis_priority)
    if not priority:
        priority = list(range(len(shape)))

    while total_bytes > max_bytes and priority:
        axis = priority.pop()  # shrink lowest-priority axis first
        current = block_shape[axis]
        if current > 1:
            block_shape[axis] = max(1, current // 2)
            total_bytes = np.prod(block_shape) * dtype_size
        else:
            # Cannot shrink further; remove axis and continue
            continue

    return tuple(block_shape)


def _generate_slices(
    shape: Tuple[int, ...],
    block_shape: Tuple[int, ...],
) -> Iterator[Tuple[slice, ...]]:
    """
    Yield slice tuples that tile the array with given block_shape.
    """

    ranges = [
        list(range(0, dim, block))
        for dim, block in zip(shape, block_shape)
    ]
    for start_indices in product(*ranges):
        slices = []
        for axis, start in enumerate(start_indices):
            end = min(shape[axis], start + block_shape[axis])
            slices.append(slice(start, end))
        yield tuple(slices)


class FieldArrayBatchIterator:
    """
    Iterate over FieldArray data in GPU-friendly batches.
    """

    def __init__(
        self,
        field_array: "FieldArray",
        *,
        block_shape: Optional[Tuple[int, ...]] = None,
        max_gpu_ratio: float = 0.8,
        axis_priority: Optional[Sequence[int]] = None,
        use_cuda: bool = True,
        stream: Optional["cp.cuda.Stream"] = None,
    ) -> None:
        self._field = field_array
        self._shape = field_array.shape
        self._dtype = field_array.dtype
        self._axis_priority = axis_priority or tuple(range(len(self._shape)))
        self._use_cuda = use_cuda and CUDA_AVAILABLE
        self._stream = stream
        self._max_gpu_ratio = max(0.1, min(max_gpu_ratio, 0.95))
        self._block_shape = block_shape or self._auto_block_shape()

    def _available_gpu_bytes(self) -> int:
        if not self._use_cuda:
            return int(0.8 * (1024**3))  # fallback 0.8 GB
        try:
            free_mem, _ = cp.cuda.runtime.memGetInfo()
            return int(free_mem * self._max_gpu_ratio)
        except Exception as exc:  # pragma: no cover - runtime specific
            logger.warning("Failed to read GPU memory info: %s", exc)
            return int(0.8 * (1024**3))

    def _auto_block_shape(self) -> Tuple[int, ...]:
        max_bytes = self._available_gpu_bytes()
        dtype_size = np.dtype(self._dtype).itemsize
        return _compute_default_block_shape(
            self._shape,
            dtype_size,
            max_bytes,
            self._axis_priority,
        )

    def iterate(self) -> Iterator[Dict[str, object]]:
        """
        Yield batches with CPU and optional GPU views.
        """

        base_array = self._field.array
        for batch_id, slices in enumerate(_generate_slices(self._shape, self._block_shape)):
            cpu_view = base_array[slices]
            gpu_view = None
            if self._use_cuda:
                gpu_view = self._to_gpu(cpu_view)
            yield {
                "batch_id": batch_id,
                "slices": slices,
                "cpu": cpu_view,
                "gpu": gpu_view,
            }

    def _to_gpu(self, cpu_view: np.ndarray):
        arr = np.ascontiguousarray(cpu_view)
        if not CUDA_AVAILABLE:
            return None
        if self._stream is None:
            return cp.asarray(arr)
        with self._stream:
            gpu_arr = cp.asarray(arr)
        self._stream.synchronize()
        return gpu_arr


def create_field_array_from_block_generator(
    *,
    field_cls,
    block_generator: "BlockedFieldGenerator",
    dtype: np.dtype = np.complex128,
    swap_threshold_gb: Optional[float] = None,
    flush_every: int = 8,
) -> "FieldArray":
    """
    Materialize a FieldArray by streaming blocks from generator.
    """

    target_shape = tuple(block_generator.domain.shape)
    field = field_cls(
        shape=target_shape,
        dtype=dtype,
        swap_threshold_gb=swap_threshold_gb,
    )
    target = field.array
    block_size = tuple(block_generator.block_size)

    def _to_cpu(block):
        if CUDA_AVAILABLE and isinstance(block, cp.ndarray):
            return cp.asnumpy(block)
        return np.array(block, copy=False)

    for block_idx, (block, metadata) in enumerate(block_generator.iterate_blocks()):
        cpu_block = _to_cpu(block)
        start = tuple(idx * size for idx, size in zip(metadata["block_indices"], block_size))
        end = tuple(start_dim + cpu_block.shape[i] for i, start_dim in enumerate(start))
        slices = tuple(slice(start_dim, end_dim) for start_dim, end_dim in zip(start, end))
        target[slices] = cpu_block
        if isinstance(target, np.memmap) and (block_idx + 1) % flush_every == 0:
            target.flush()

    if isinstance(target, np.memmap):
        target.flush()

    return field

