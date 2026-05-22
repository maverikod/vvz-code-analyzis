#!/usr/bin/env python3
r"""
================================================================================
NAME
================================================================================
    ex_universal_files — live-server demo of ``UniversalFileClient`` (all methods).

================================================================================
SYNOPSIS
================================================================================
::

    cd /path/to/code_analysis_repository
    source .venv/bin/activate
    casmgr --config config.json start
    python client/examples/ex_universal_files.py

================================================================================
DESCRIPTION
================================================================================
Exercises every public method on :class:`code_analysis_client.UniversalFileClient`
against a running daemon. The edit workflow uses ``write_mode=preview`` and
``close`` without commit so the on-disk file is unchanged.

Author: Vasiliy Zdanovskiy <vasilyvz@gmail.com>
"""

from __future__ import annotations

import asyncio
import sys
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict

_EXAMPLES = Path(__file__).resolve().parent
_CLIENT = _EXAMPLES.parent
if str(_CLIENT) not in sys.path:
    sys.path.insert(0, str(_CLIENT))

from _common import chdir_repo_root, default_config_path, ensure_client_package_on_path  # noqa: E402

ensure_client_package_on_path()

from code_analysis_client import CodeAnalysisAsyncClient  # noqa: E402

CLIENT_API_COVERAGE = frozenset(
    {
        "CodeAnalysisAsyncClient.from_server_config_path",
        "CodeAnalysisAsyncClient.universal_files",
        "CodeAnalysisAsyncClient.__aenter__",
        "CodeAnalysisAsyncClient.__aexit__",
        "UniversalFileClient.open",
        "UniversalFileClient.preview",
        "UniversalFileClient.edit",
        "UniversalFileClient.write",
        "UniversalFileClient.close",
    }
)


def _data(resp: Dict[str, Any]) -> Dict[str, Any]:
    inner = resp.get("data")
    return inner if isinstance(inner, dict) else resp


async def _discover_text_file(client: CodeAnalysisAsyncClient) -> tuple[str, str]:
    resp = await client.call("list_projects", {"include_deleted": False})
    if resp.get("success") is not True:
        raise RuntimeError(f"list_projects failed: {resp!r}")
    data = _data(resp)
    for proj in data.get("projects") or data.get("items") or []:
        if not isinstance(proj, dict):
            continue
        pid = str(proj.get("id") or proj.get("project_id") or "").strip()
        if not pid:
            continue
        files_resp = await client.call(
            "list_project_files",
            {"project_id": pid, "limit": 200},
        )
        if files_resp.get("success") is not True:
            continue
        fdata = _data(files_resp)
        for row in fdata.get("files") or []:
            if not isinstance(row, dict):
                continue
            rel = str(row.get("relative_path") or row.get("path") or "").strip()
            if not rel:
                continue
            if Path(rel).suffix.lower() in {".txt", ".md", ".rst", ".adoc"}:
                return pid, rel.replace("\\", "/")
    raise RuntimeError(
        "No .txt/.md file found in any project — add a text file or run update_indexes"
    )


async def run_all() -> int:
    chdir_repo_root()
    cfg = default_config_path()

    async with CodeAnalysisAsyncClient.from_server_config_path(cfg) as client:
        uf = client.universal_files
        project_id, _sample_path = await _discover_text_file(client)
        file_path = f"tmp/client_uf_ex_{uuid.uuid4().hex[:12]}.txt"
        print(f"Fixture: project_id={project_id} file_path={file_path!r}")

        opened = await uf.open(
            project_id,
            file_path,
            create=True,
            initial_content="line one\nline two\n",
        )
        session_id = str(opened.get("session_id") or "").strip()
        if not session_id:
            raise AssertionError(f"open returned no session_id: {opened!r}")
        print(f"  open OK session_id={session_id}")

        prev = await uf.preview(project_id, file_path, session_id=session_id)
        if not isinstance(prev, dict):
            raise AssertionError(f"preview unexpected: {prev!r}")
        print("  preview OK")

        edited = await uf.edit(
            project_id,
            session_id,
            operations=[
                {
                    "type": "replace",
                    "start_line": 1,
                    "end_line": 1,
                    "content": "# client example preview-only edit\n",
                }
            ],
        )
        if edited.get("success") is False:
            raise AssertionError(f"edit failed: {edited!r}")
        print("  edit OK")

        wr_preview = await uf.write(project_id, session_id, write_mode="preview")
        if wr_preview.get("phase") != "preview" and "diff" not in wr_preview:
            raise AssertionError(f"write preview unexpected: {wr_preview!r}")
        print("  write(preview) OK")

        closed = await uf.close(project_id, session_id)
        if closed.get("success") is not True and closed.get("closed") is not True:
            if closed.get("success") is not False:
                print(f"  close OK: {closed!r}")
            else:
                raise AssertionError(f"close failed: {closed!r}")
        else:
            print("  close OK")

    print("All UniversalFileClient methods exercised.")
    return 0


def main() -> int:
    try:
        return asyncio.run(run_all())
    except KeyboardInterrupt:
        return 130
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
