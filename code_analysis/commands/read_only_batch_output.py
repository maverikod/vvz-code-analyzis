"""
Oversized batch output serialization and metadata for read-only batch command.

Serializes combined batch result deterministically, writes to a file, and returns
metadata (output_file, file_size, per-command size/offset/length) for byte-range
extraction. No approximate offsets; no inline oversized payload fallback.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence, TypedDict


def _default_serializer(obj: Any) -> Any:
    """Convert non-JSON types to deterministic serializable form."""
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _dumps_deterministic(obj: dict[str, Any]) -> str:
    """Serialize dict to deterministic JSON string (stable key order, no whitespace)."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_default_serializer,
    )


class _ResultEntry(TypedDict, total=False):
    """Single entry in batch results: command id and result payload."""

    command: str
    result: Any


class _CommandMetadata(TypedDict):
    """Per-command metadata for byte-range extraction."""

    command: str
    size: int
    offset: int
    length: int


class _OutputMetadata(TypedDict):
    """Metadata returned when oversized output is written to file."""

    output_file: str
    file_size: int
    results_metadata: list[_CommandMetadata]


def write_oversized_batch_output(
    results: Sequence[_ResultEntry],
    output_dir: str,
    *,
    file_prefix: str = "batch_output",
) -> _OutputMetadata:
    """Serialize batch results deterministically to a file and return metadata.

    Writes one JSON object per line (JSON Lines). Each line is serialized with
    sort_keys and fixed separators so that byte offsets are deterministic.
    Per-command size, offset, and length refer to exact byte ranges in the
    file; extraction via file[offset:offset+length] reproduces the exact
    fragment for that command.

    Args:
        results: Sequence of dicts with "command" (str) and "result" (payload).
        output_dir: Directory path to write the output file.
        file_prefix: Prefix for the output filename (default "batch_output").

    Returns:
        Dict with:
        - output_file: Absolute path to the written file.
        - file_size: Total file size in bytes.
        - results_metadata: List of per-command dicts with command, size,
          offset, length (exact byte range for this command's line).

    Raises:
        OSError: If writing the file fails.
        TypeError: If any result payload is not JSON-serializable.
    """
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    name = f"{file_prefix}_{uuid.uuid4().hex}.jsonl"
    output_path = (path / name).resolve()

    lines_utf8: list[bytes] = []
    running_offset = 0
    results_metadata: list[_CommandMetadata] = []

    for entry in results:
        command_name = entry.get("command", "")
        result_payload = entry.get("result")
        line_obj: dict[str, Any] = {"command": command_name, "result": result_payload}
        line_str = _dumps_deterministic(line_obj)
        line_bytes = (line_str + "\n").encode("utf-8")
        length = len(line_bytes)
        results_metadata.append(
            _CommandMetadata(
                command=command_name,
                size=length,
                offset=running_offset,
                length=length,
            )
        )
        running_offset += length
        lines_utf8.append(line_bytes)

    with open(output_path, "wb") as f:
        for bline in lines_utf8:
            f.write(bline)

    file_size = running_offset

    return _OutputMetadata(
        output_file=str(output_path),
        file_size=file_size,
        results_metadata=results_metadata,
    )


def extract_command_fragment(file_path: str, offset: int, length: int) -> bytes:
    """Read exact byte range from batch output file for one command.

    Used to verify or consume a single command's fragment using metadata
    returned by write_oversized_batch_output. Byte-range extraction
    reproduces the exact serialized fragment.

    Args:
        file_path: Path to the batch output file.
        offset: Start byte offset (from results_metadata).
        length: Fragment length in bytes (from results_metadata).

    Returns:
        Raw bytes for the fragment (includes trailing newline).
    """
    with open(file_path, "rb") as f:
        f.seek(offset)
        return f.read(length)
