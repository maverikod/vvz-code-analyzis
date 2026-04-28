"""
Unit tests for file-based batching (pack_files_into_packets).

Verifies algorithm from docs/VECTORIZATION_BATCHING_ALGORITHM.md: sort by count
descending, greedy packing with free_slots, response index = (file_id, chunk_id) order.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from code_analysis.core.vectorization_worker_pkg.file_batch_packing import (
    pack_files_into_packets,
)


class TestPackFilesIntoPackets:
    """Tests for pack_files_into_packets."""

    def test_uuid_string_file_ids_pack_correctly(self) -> None:
        """file_id is a logical UUID string (not int); packing is unchanged."""
        fid = "550e8400-e29b-41d4-a716-446655440001"
        result = pack_files_into_packets([(fid, "a.py", 3)], batch_size=10)
        assert result == [[(fid, "a.py", 3)]]

    def test_empty_file_table_returns_empty_packets(self) -> None:
        """Empty file table yields no packets."""
        assert pack_files_into_packets([], batch_size=10) == []

    def test_zero_batch_size_returns_empty_packets(self) -> None:
        """Zero batch_size yields no packets."""
        assert pack_files_into_packets([("1", "a.py", 5)], batch_size=0) == []

    def test_single_file_fits_in_one_packet(self) -> None:
        """One file with count <= batch_size produces one packet with that file."""
        result = pack_files_into_packets(
            [("1", "a.py", 3)],
            batch_size=10,
        )
        assert result == [[("1", "a.py", 3)]]

    def test_single_file_over_batch_size_capped(self) -> None:
        """One file with count > batch_size is capped to batch_size in first packet."""
        result = pack_files_into_packets(
            [("1", "a.py", 20)],
            batch_size=10,
        )
        assert result == [[("1", "a.py", 10)], [("1", "a.py", 10)]]

    def test_two_files_both_fit_one_packet(self) -> None:
        """Two files that together fit in batch_size go into one packet (largest first)."""
        result = pack_files_into_packets(
            [("1", "a.py", 4), ("2", "b.py", 3)],
            batch_size=10,
        )
        # Sorted by count desc: (1,4), (2,3). First packet: 4 + 3 = 7 <= 10
        assert result == [[("1", "a.py", 4), ("2", "b.py", 3)]]

    def test_greedy_adds_largest_that_fits(self) -> None:
        """Packet fills with first (largest) file, then largest file that fits in free_slots."""
        # Files: 5, 4, 3, 2; batch_size=10. First: 5 (free 5). Then 4 fits -> 5+4=9 (free 1). 3,2 don't fit.
        result = pack_files_into_packets(
            [("1", "a.py", 5), ("2", "b.py", 4), ("3", "c.py", 3), ("4", "d.py", 2)],
            batch_size=10,
        )
        assert result == [
            [("1", "a.py", 5), ("2", "b.py", 4)],
            [("3", "c.py", 3), ("4", "d.py", 2)],
        ]

    def test_sum_take_count_per_packet_le_batch_size(self) -> None:
        """Every packet has sum(take_count) <= batch_size."""
        file_table = [
            ("1", "a.py", 7),
            ("2", "b.py", 6),
            ("3", "c.py", 5),
            ("4", "d.py", 4),
            ("5", "e.py", 3),
        ]
        batch_size = 10
        packets = pack_files_into_packets(file_table, batch_size)
        for packet in packets:
            total = sum(take for _fid, _path, take in packet)
            assert (
                total <= batch_size
            ), f"Packet {packet} sums to {total} > {batch_size}"

    def test_all_chunks_accounted_for(self) -> None:
        """Sum of all take_counts across packets equals total chunks (when no file > batch_size split)."""
        file_table = [("1", "a.py", 3), ("2", "b.py", 2), ("3", "c.py", 4)]
        batch_size = 5
        packets = pack_files_into_packets(file_table, batch_size)
        total_in_packets = sum(
            take for packet in packets for _fid, _path, take in packet
        )
        total_chunks = sum(c for _fid, _path, c in file_table)
        assert total_in_packets == total_chunks

    def test_partial_file_remainder_in_next_packet(self) -> None:
        """When a file is partially consumed, remainder appears in next packet."""
        # One file with 25 chunks, batch_size 10 -> 3 packets: 10, 10, 5
        result = pack_files_into_packets(
            [("1", "big.py", 25)],
            batch_size=10,
        )
        assert result == [
            [("1", "big.py", 10)],
            [("1", "big.py", 10)],
            [("1", "big.py", 5)],
        ]

    def test_zero_count_files_ignored(self) -> None:
        """Entries with count 0 are ignored."""
        result = pack_files_into_packets(
            [("1", "a.py", 0), ("2", "b.py", 2)],
            batch_size=10,
        )
        assert result == [[("2", "b.py", 2)]]

    def test_ordering_stable_per_packet(self) -> None:
        """Within a packet: first file is largest, then largest that fits (greedy)."""
        file_table = [("1", "a.py", 2), ("2", "b.py", 3), ("3", "c.py", 1)]
        batch_size = 6
        packets = pack_files_into_packets(file_table, batch_size)
        # Sorted by count: 3,2,1. Packet: 3+2+1 = 6
        assert len(packets) == 1
        assert packets[0][0][2] >= packets[0][1][2] >= packets[0][2][2]
