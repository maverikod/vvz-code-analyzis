"""
File-based batching for vectorization: pack files into packets of at most batch_size texts.

Implements algorithm from docs/VECTORIZATION_BATCHING_ALGORITHM.md:
- Sort files by non-vectorized count descending.
- Form packets: first file fills up to batch_size; then greedily add files with count <= free_slots (max first).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List, Optional, Tuple

# (file_id, file_path, count or take_count)
FileCountRow = Tuple[int, str, int]


def pack_files_into_packets(
    file_table: List[FileCountRow],
    batch_size: int,
) -> List[List[FileCountRow]]:
    """
    Pack files into packets so each packet has at most batch_size texts (chunks).

    Files are sorted by count descending. Each packet is built by taking the
    first (largest) file, then greedily adding the largest file that fits in
    remaining free slots. Partially consumed files remain for the next packet.

    Args:
        file_table: List of (file_id, file_path, non_vectorized_count). Not required
            to be sorted; will be sorted internally per pass.
        batch_size: Maximum number of texts (chunks) per packet.

    Returns:
        List of packets. Each packet is a list of (file_id, file_path, take_count)
        with sum(take_count) <= batch_size. Order of files within a packet
        follows the greedy algorithm (first file = largest, then largest that fits).
    """
    if batch_size <= 0 or not file_table:
        return []

    # Work on a mutable list of (file_id, file_path, count); sort by count desc
    remaining: List[FileCountRow] = sorted(
        [(fid, path, c) for fid, path, c in file_table if c > 0],
        key=lambda x: x[2],
        reverse=True,
    )
    packets: List[List[FileCountRow]] = []

    while remaining:
        packet = _form_one_packet(remaining, batch_size)
        if not packet:
            break
        packets.append(packet)
        # _form_one_packet mutates remaining (removes consumed, re-adds partials)

    return packets


def _form_one_packet(
    remaining: List[FileCountRow],
    batch_size: int,
) -> List[FileCountRow]:
    """
    Form a single packet from remaining files; mutate remaining in place.

    Takes first (largest) file, then repeatedly adds the largest file that fits
    in free_slots. Partially consumed files are re-inserted into remaining.

    Returns:
        Packet: list of (file_id, file_path, take_count).
    """
    if not remaining or batch_size <= 0:
        return []

    packet: List[FileCountRow] = []
    free_slots = batch_size

    # Sort by count descending so we always take the largest first
    remaining.sort(key=lambda x: x[2], reverse=True)

    # Take first file
    file_id, file_path, count = remaining.pop(0)
    take = min(count, batch_size)
    packet.append((file_id, file_path, take))
    free_slots -= take
    if count > take:
        remaining.append((file_id, file_path, count - take))

    # Greedily add files with count <= free_slots (largest first)
    while free_slots > 0 and remaining:
        remaining.sort(key=lambda x: x[2], reverse=True)
        # Find largest file with count <= free_slots
        candidate_idx: Optional[int] = None
        for i, (_, _, c) in enumerate(remaining):
            if c <= free_slots:
                candidate_idx = i
                break
        if candidate_idx is None:
            break
        file_id, file_path, count = remaining.pop(candidate_idx)
        take = min(count, free_slots)
        packet.append((file_id, file_path, take))
        free_slots -= take
        if count > take:
            remaining.append((file_id, file_path, count - take))

    return packet
