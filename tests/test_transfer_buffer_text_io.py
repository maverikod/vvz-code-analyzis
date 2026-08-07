"""
Regression tests for byte-verbatim text IO on the save path (bug 44724d35).

The defect: the completed transfer buffer was read in Python's default text
mode, so universal-newline translation collapsed every ``\\r\\n`` and lone
``\\r`` to ``\\n`` before the content reached a file handler. 20 bytes of CRLF
were stored as 17 bytes of LF, the save reported success, and no parameter
let a caller opt out.

These tests pin the two halves of the fix -- the buffer reader and the text
handler's write -- so neither can silently start translating again.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import gzip
from pathlib import Path
from unittest.mock import MagicMock, patch

from code_analysis.core.file_handlers.base import FileHandlerRequest
from code_analysis.core.file_handlers.registry import HANDLER_TEXT
from code_analysis.core.file_handlers.text_handler import TextFileHandler
from code_analysis.core.transfer_buffer_text import (
    read_text_verbatim,
    read_transfer_buffer_text,
    write_text_verbatim,
)

CRLF_BYTES = b"alpha\r\nbeta\r\ngamma\r\n"
CRLF_TEXT = "alpha\r\nbeta\r\ngamma\r\n"
MIXED_BYTES = b"crlf\r\ncr\rlf\n\r\nno-trailing-newline"


def test_read_text_verbatim_preserves_crlf(tmp_path: Path) -> None:
    """Verify a plain buffer read keeps CRLF terminators intact."""
    buffer_path = tmp_path / "buffer.txt"
    buffer_path.write_bytes(CRLF_BYTES)

    assert read_text_verbatim(buffer_path) == CRLF_TEXT
    assert len(read_text_verbatim(buffer_path)) == len(CRLF_BYTES)


def test_read_text_verbatim_preserves_lone_cr_and_mixed_endings(
    tmp_path: Path,
) -> None:
    """Verify lone CR, mixed terminators, and a missing final newline survive."""
    buffer_path = tmp_path / "buffer.txt"
    buffer_path.write_bytes(MIXED_BYTES)

    assert read_text_verbatim(buffer_path).encode("utf-8") == MIXED_BYTES


def test_read_transfer_buffer_text_identity_preserves_crlf(tmp_path: Path) -> None:
    """Verify the identity branch of the buffer reader preserves CRLF."""
    buffer_path = tmp_path / "identity.bin"
    buffer_path.write_bytes(CRLF_BYTES)

    assert read_transfer_buffer_text(buffer_path, "identity") == CRLF_TEXT


def test_read_transfer_buffer_text_unknown_compression_reads_as_identity(
    tmp_path: Path,
) -> None:
    """Verify an unrecognized compression value falls back to a verbatim read."""
    buffer_path = tmp_path / "identity.bin"
    buffer_path.write_bytes(CRLF_BYTES)

    assert read_transfer_buffer_text(buffer_path, "") == CRLF_TEXT


def test_read_transfer_buffer_text_gzip_preserves_crlf(tmp_path: Path) -> None:
    """Verify the gzip branch of the buffer reader preserves CRLF."""
    buffer_path = tmp_path / "buffer.gz"
    with gzip.open(buffer_path, "wb") as handle:
        handle.write(CRLF_BYTES)

    assert read_transfer_buffer_text(buffer_path, "gzip") == CRLF_TEXT


def test_write_text_verbatim_writes_exact_bytes(tmp_path: Path) -> None:
    """Verify the verbatim writer stores the string it was given, byte for byte."""
    target = tmp_path / "out.txt"

    write_text_verbatim(target, CRLF_TEXT)

    assert target.read_bytes() == CRLF_BYTES


def _reject_ast(*args: object, **kwargs: object) -> None:
    """Fail if the text path ever reaches the Python AST parser."""
    raise AssertionError("ast.parse must not be called for markdown/text")


def _reject_batch(*args: object, **kwargs: object) -> None:
    """Fail if the text path ever reaches the code-index batch writer."""
    raise AssertionError("update_file_data_atomic_batch must not be called for text")


@patch(
    "code_analysis.core.database_client.file_data_batch.update_file_data_atomic_batch",
    side_effect=_reject_batch,
)
@patch("ast.parse", side_effect=_reject_ast)
def test_text_handler_save_stores_crlf_verbatim(
    _mock_ast_parse: MagicMock,
    _mock_batch: MagicMock,
    tmp_path: Path,
) -> None:
    """Bug 44724d35: a full-file text save stores CRLF content unchanged."""
    target = tmp_path / "crlf.txt"
    request = FileHandlerRequest(
        project_id="p",
        file_path="crlf.txt",
        handler_id=HANDLER_TEXT,
        operation="save",
        dry_run=False,
        diff=False,
        backup=False,
        extra={"absolute_path": target, "content": CRLF_TEXT},
    )

    result = TextFileHandler().save(request)

    assert result.success is True
    assert target.read_bytes() == CRLF_BYTES


@patch(
    "code_analysis.core.database_client.file_data_batch.update_file_data_atomic_batch",
    side_effect=_reject_batch,
)
@patch("ast.parse", side_effect=_reject_ast)
def test_text_handler_save_reports_line_ending_only_change(
    _mock_ast_parse: MagicMock,
    _mock_batch: MagicMock,
    tmp_path: Path,
) -> None:
    """Verify a CRLF-to-LF rewrite of the same lines counts as a change.

    The pre-write comparison reads the existing file verbatim, so replacing a
    CRLF file with its LF equivalent is reported as ``changed`` instead of
    being masked by a translating read.
    """
    target = tmp_path / "crlf.md"
    target.write_bytes(CRLF_BYTES)
    request = FileHandlerRequest(
        project_id="p",
        file_path="crlf.md",
        handler_id=HANDLER_TEXT,
        operation="save",
        dry_run=False,
        diff=False,
        backup=False,
        extra={"absolute_path": target, "content": "alpha\nbeta\ngamma\n"},
    )

    result = TextFileHandler().save(request)

    assert result.success is True
    assert result.changed is True
    assert target.read_bytes() == b"alpha\nbeta\ngamma\n"


@patch(
    "code_analysis.core.database_client.file_data_batch.update_file_data_atomic_batch",
    side_effect=_reject_batch,
)
@patch("ast.parse", side_effect=_reject_ast)
def test_text_handler_save_dry_run_does_not_touch_disk(
    _mock_ast_parse: MagicMock,
    _mock_batch: MagicMock,
    tmp_path: Path,
) -> None:
    """Verify the verbatim write is still skipped entirely on a dry run."""
    target = tmp_path / "crlf.txt"
    target.write_bytes(CRLF_BYTES)
    request = FileHandlerRequest(
        project_id="p",
        file_path="crlf.txt",
        handler_id=HANDLER_TEXT,
        operation="save",
        dry_run=True,
        diff=False,
        backup=False,
        extra={"absolute_path": target, "content": "replaced\r\n"},
    )

    result = TextFileHandler().save(request)

    assert result.success is True
    assert target.read_bytes() == CRLF_BYTES
