"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA block merging helpers for `CUDABlockProcessor`.

Implements overlap-aware merging of processed CUDA blocks and creation of
weight masks to ensure smooth transitions across block boundaries.

Example:
    >>> # Used internally by CUDABlockProcessor
"""

from __future__ import annotations

from typing import Any, List, Tuple

try:
    import cupy as cp
except Exception:  # pragma: no cover
    cp = None  # type: ignore


def create_weight_mask_cuda(
    block_shape: tuple,
    n_dims: int,
    overlap: int,
    start_indices: tuple,
    end_indices: tuple,
    domain_shape: tuple,
) -> "cp.ndarray":
    """Create weight mask for overlap handling on GPU for a block."""
    weight_mask = cp.ones(block_shape, dtype=cp.float64)
    for dim in range(n_dims):
        if start_indices[dim] > 0:
            ov = min(overlap, block_shape[dim])
            weight_mask[
                tuple(slice(0, ov) if i == dim else slice(None) for i in range(n_dims))
            ] *= 0.5
        if end_indices[dim] < domain_shape[dim]:
            ov = min(overlap, block_shape[dim])
            weight_mask[
                tuple(
                    slice(-ov, None) if i == dim else slice(None) for i in range(n_dims)
                )
            ] *= 0.5
    return weight_mask


def merge_blocks_cuda(
    processed_blocks: List[Tuple["cp.ndarray", Any]],
    domain_shape: tuple,
    n_dims: int,
    overlap: int,
) -> "cp.ndarray":
    """Merge processed CUDA blocks into a full array with overlap weights."""
    result = cp.zeros(domain_shape, dtype=cp.complex128)
    weight_map = cp.zeros(domain_shape, dtype=cp.float64)

    for block_data, block_info in processed_blocks:
        start_indices = block_info.start_indices
        end_indices = block_info.end_indices
        block_shape = block_info.shape
        slices = tuple(slice(s, e) for s, e in zip(start_indices, end_indices))
        weight_mask = create_weight_mask_cuda(
            block_shape, n_dims, overlap, start_indices, end_indices, domain_shape
        )
        result[slices] += block_data * weight_mask
        weight_map[slices] += weight_mask

    return cp.divide(
        result, weight_map, out=cp.zeros_like(result), where=weight_map != 0
    )
