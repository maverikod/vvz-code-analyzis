"""
File-based batching for vectorization: pack files into packets of at most batch_size texts.

Implements algorithm from docs/VECTORIZATION_BATCHING_ALGORITHM.md:
- Sort files by non-vectorized count descending, then by file updated_at descending
  (when provided), then by file_id for a stable tie-break.
- Form packets: first file fills up to batch_size; then greedily add files with count <= free_slots (max first).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List, Optional, Tuple, Union

# Legacy input: (file_id, file_path, count). Extended: (file_id, file_path, count, updated_at).
FileCountInput = Union[Tuple[str, str, int], Tuple[str, str, int, float]]
# Internal row during packing (updated_at from files.updated_at, Julian or comparable float).
_PackRow = Tuple[str, str, int, float]


def _normalize_table(file_table: List[FileCountInput]) -> List[_PackRow]:
    """Build internal rows; missing updated_at defaults to 0.0 (sorts last when DESC by time)."""
    out: List[_PackRow] = []
    for row in file_table:
        if len(row) == 3:
            fid, path, c = row[0], row[1], row[2]
            out.append((str(fid), str(path), int(c), 0.0))
        else:
            fid, path, c, u = row[0], row[1], row[2], row[3]
            try:
                uf = float(u) if u is not None else 0.0
            except (TypeError, ValueError):
                uf = 0.0
            out.append((str(fid), str(path), int(c), uf))
    return out


def _sort_key(row: _PackRow) -> Tuple[int, float, str]:
    """Higher count first, then more recent updated_at, then deterministic file_id."""
    return (row[2], row[3], row[0])


def pack_files_into_packets(
    file_table: List[FileCountInput],
    batch_size: int,
) -> List[List[Tuple[str, str, int]]]:
    """
    Pack files into packets so each packet has at most batch_size texts (chunks).

    Files are sorted by count descending, then by file updated_at descending when the
    fourth tuple field is supplied. Each packet is built by taking the first (largest)
    file, then greedily adding the largest file that fits in remaining free slots.
    Partially consumed files remain for the next packet.

    Args:
        file_table: List of (file_id, file_path, non_vectorized_count) or four-tuples
            with optional ``updated_at`` (same semantics as ``files.updated_at``).
        batch_size: Maximum number of texts (chunks) per packet.

    Returns:
        List of packets. Each packet is a list of (file_id, file_path, take_count)
        with sum(take_count) <= batch_size.
    """
    if batch_size <= 0 or not file_table:
        return []

    remaining: List[_PackRow] = sorted(
        [r for r in _normalize_table(file_table) if r[2] > 0],
        key=_sort_key,
        reverse=True,
    )
    packets: List[List[Tuple[str, str, int]]] = []

    while remaining:
        packet = _form_one_packet(remaining, batch_size)
        if not packet:
            break
        packets.append(packet)

    return packets


def _form_one_packet(
    remaining: List[_PackRow],
    batch_size: int,
) -> List[Tuple[str, str, int]]:
    """
    Form a single packet from remaining files; mutate remaining in place.

    Returns:
        Packet: list of (file_id, file_path, take_count) only (no updated_at in output).
    """
    if not remaining or batch_size <= 0:
        return []

    packet: List[Tuple[str, str, int]] = []
    free_slots = batch_size

    remaining.sort(key=_sort_key, reverse=True)

    file_id, file_path, count, file_updated_at = remaining.pop(0)
    take = min(count, batch_size)
    packet.append((file_id, file_path, take))
    free_slots -= take
    if count > take:
        remaining.append((file_id, file_path, count - take, file_updated_at))

    while free_slots > 0 and remaining:
        remaining.sort(key=_sort_key, reverse=True)
        candidate_idx: Optional[int] = None
        for i, (_, _, c, _) in enumerate(remaining):
            if c <= free_slots:
                candidate_idx = i
                break
        if candidate_idx is None:
            break
        file_id, file_path, count, file_updated_at = remaining.pop(candidate_idx)
        take = min(count, free_slots)
        packet.append((file_id, file_path, take))
        free_slots -= take
        if count > take:
            remaining.append((file_id, file_path, count - take, file_updated_at))

    return packet
