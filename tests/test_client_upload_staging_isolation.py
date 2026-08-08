"""
Regression tests: an upload must not stage payloads in the caller's cwd.

Bug c3fafbd4. ``FileSessionClient.upload_bytes`` wrote the payload to
``Path(filename)`` -- a RELATIVE path, i.e. inside the calling process's
current working directory -- and deleted it again in a ``finally``. Uploading
a file called ``pyproject.toml`` therefore OVERWROTE and then DELETED the
caller's own ``pyproject.toml``.

That is exactly how the live acceptance pipeline destroyed files in the
developer's checkout: its ``nonpy`` suite seeds four fixture files named
``pyproject.toml``, ``script.sh``, ``.gitignore`` and ``notes.md``, and the
pipeline runs with the repository root as its working directory. Only the two
names that also exist at the repo root showed up in ``git status`` as deleted;
the other two were created and removed with no trace, which is why the
symptom always looked like "exactly these two files".

The upload staged nothing the caller asked to be staged: the filename is a
NAME sent to the server, never a path the client may write to.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis_client import CodeAnalysisAsyncClient, FileSessionClient

_PAYLOAD = b"uploaded payload\n"
_SENTINEL = b"PRECIOUS: the caller's own file\n"


def _client_with_recording_upload() -> tuple[FileSessionClient, dict]:
    """Build a FileSessionClient whose transport records the staged path.

    Returns:
        The client and a dict that receives ``source_path`` / ``filename``
        plus the payload bytes seen on disk at upload time.
    """
    recorded: dict = {}

    async def _fake_upload_file(source_path, filename=None, compression="identity"):
        recorded["source_path"] = str(source_path)
        recorded["filename"] = filename
        recorded["staged_bytes"] = Path(source_path).read_bytes()
        recorded["staged_existed_at_upload"] = Path(source_path).is_file()
        return SimpleNamespace(transfer_id="tr_1", completed=True)

    mock_rpc = MagicMock()
    mock_rpc.upload_file = AsyncMock(side_effect=_fake_upload_file)
    with patch("code_analysis_client.client.JsonRpcClient", return_value=mock_rpc):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        client.rpc.upload_file = mock_rpc.upload_file
    return FileSessionClient(client), recorded


@pytest.mark.asyncio
async def test_upload_bytes_does_not_touch_a_same_named_file_in_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bug c3fafbd4: uploading "pyproject.toml" must not eat the caller's own."""
    monkeypatch.chdir(tmp_path)
    victim = tmp_path / "pyproject.toml"
    victim.write_bytes(_SENTINEL)

    fs, recorded = _client_with_recording_upload()
    await fs.upload_bytes(_PAYLOAD, filename="pyproject.toml")

    assert victim.is_file(), "the caller's pyproject.toml was deleted"
    assert victim.read_bytes() == _SENTINEL, "the caller's pyproject.toml was rewritten"
    assert recorded["staged_bytes"] == _PAYLOAD


@pytest.mark.asyncio
async def test_upload_bytes_stages_outside_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The staged copy lives somewhere else entirely, and leaves no residue."""
    monkeypatch.chdir(tmp_path)
    before = {p.name for p in tmp_path.iterdir()}

    fs, recorded = _client_with_recording_upload()
    await fs.upload_bytes(_PAYLOAD, filename="notes.md")

    staged = Path(recorded["source_path"]).resolve()
    assert staged.parent != tmp_path.resolve(), (
        f"payload was staged inside the caller's cwd: {staged}"
    )
    assert {p.name for p in tmp_path.iterdir()} == before, "cwd gained or lost entries"
    assert not staged.exists(), "the staged copy was not cleaned up"


@pytest.mark.asyncio
async def test_upload_bytes_still_sends_the_requested_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Staging elsewhere must not change the name the server is told."""
    monkeypatch.chdir(tmp_path)

    fs, recorded = _client_with_recording_upload()
    await fs.upload_bytes(_PAYLOAD, filename=".gitignore")

    assert recorded["filename"] == ".gitignore"
    assert Path(recorded["source_path"]).name == ".gitignore"


@pytest.mark.asyncio
async def test_upload_bytes_cleans_up_when_the_transport_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed upload leaves neither the staged copy nor cwd residue behind."""
    monkeypatch.chdir(tmp_path)
    victim = tmp_path / "script.sh"
    victim.write_bytes(_SENTINEL)

    staged_paths: list[str] = []

    async def _boom(source_path, filename=None, compression="identity"):
        staged_paths.append(str(source_path))
        raise RuntimeError("transport down")

    mock_rpc = MagicMock()
    mock_rpc.upload_file = AsyncMock(side_effect=_boom)
    with patch("code_analysis_client.client.JsonRpcClient", return_value=mock_rpc):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        client.rpc.upload_file = mock_rpc.upload_file
    fs = FileSessionClient(client)

    with pytest.raises(RuntimeError):
        await fs.upload_bytes(_PAYLOAD, filename="script.sh")

    assert victim.read_bytes() == _SENTINEL
    assert staged_paths and not Path(staged_paths[0]).exists()
