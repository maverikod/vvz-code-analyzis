"""
Verbatim text IO for completed transfer buffers and project file writes.

Bug 44724d35: the save path used to read the completed upload buffer in
Python's default *text* mode (``Path.read_text()`` / ``gzip.open(..., "rt")``),
which enables universal-newline translation -- every ``\\r\\n`` and every lone
``\\r`` became ``\\n`` before the content ever reached a file handler. A caller
that uploaded ``b"alpha\\r\\nbeta\\r\\ngamma\\r\\n"`` (20 bytes) got
``b"alpha\\nbeta\\ngamma\\n"`` (17 bytes) on disk, the save reported success,
and the declared schema offered no way to opt out.

Both readers here open with ``newline=""``, which disables translation on the
way in, and :func:`write_text_verbatim` writes with ``newline=""``, which
disables it on the way out (default text-mode write turns every ``\\n`` into
``os.linesep``). Together they make "the bytes the caller sent are the bytes
that land on disk" a property of the code, not of the host platform.

The two command modules that consume upload buffers
(``project_file_transfer_by_id_commands`` and ``cst_apply_buffer_command``)
carried the same duplicated read block; both now call
:func:`read_transfer_buffer_text` so the property cannot regress in one of
them alone.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import gzip
from pathlib import Path

# Compression value that means "the staged buffer holds the bytes as-is".
COMPRESSION_IDENTITY = "identity"
COMPRESSION_GZIP = "gzip"


def read_text_verbatim(path: Path, *, errors: str = "strict") -> str:
    """Read a text file without any newline translation.

    Args:
        path: File to read.
        errors: Decoding error policy passed to :func:`open`.

    Returns:
        The file's decoded content with ``\\r\\n`` and lone ``\\r`` preserved.
    """
    with open(path, "r", encoding="utf-8", errors=errors, newline="") as handle:
        return handle.read()


def read_transfer_buffer_text(buffer_path: Path, compression: str) -> str:
    """Read a completed transfer buffer as text, preserving its line endings.

    Args:
        buffer_path: Path to the staged upload buffer.
        compression: Transfer compression reported by the transfer store
            (``identity`` or ``gzip``); anything else is read as ``identity``.

    Returns:
        The buffer's decoded content, byte-faithful for line terminators.
    """
    if compression == COMPRESSION_GZIP:
        with gzip.open(buffer_path, "rt", encoding="utf-8", newline="") as handle:
            return str(handle.read())
    return read_text_verbatim(buffer_path)


def write_text_verbatim(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` with no newline translation.

    Args:
        path: Destination file (overwritten).
        content: Exact text to store.
    """
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(content)
