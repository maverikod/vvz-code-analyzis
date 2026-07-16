#!/usr/bin/env python3
r"""
================================================================================
NAME
================================================================================
    ex_universal_files — live-server demo of ``UniversalFileClient`` (preview).

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
Exercises the only public method on
:class:`code_analysis_client.UniversalFileClient` against a running daemon:
``preview`` (structured, read-only). Content editing (open/edit/write/close
sessions) is not served by this project's code-analysis server; that workflow
lives in the ai-editor client instead.

Author: Vasiliy Zdanovskiy <vasilyvz@gmail.com>
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from pathlib import Path
from typing import Any, Dict

_EXAMPLES = Path(__file__).resolve().parent
_CLIENT = _EXAMPLES.parent
if str(_CLIENT) not in sys.path:
    sys.path.insert(0, str(_CLIENT))

from _common import (  # noqa: E402
    chdir_repo_root,
    default_config_path,
    ensure_client_package_on_path,
)

ensure_client_package_on_path()

from code_analysis_client import CodeAnalysisAsyncClient  # noqa: E402

CLIENT_API_COVERAGE = frozenset(
    {
        "CodeAnalysisAsyncClient.from_server_config_path",
        "CodeAnalysisAsyncClient.universal_files",
        "CodeAnalysisAsyncClient.__aenter__",
        "CodeAnalysisAsyncClient.__aexit__",
        "UniversalFileClient.preview",
    }
)


def _data(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Return data."""
    inner = resp.get("data")
    return inner if isinstance(inner, dict) else resp


async def _discover_text_file(client: CodeAnalysisAsyncClient) -> tuple[str, str]:
    """Return discover text file."""
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
    """Return run all."""
    chdir_repo_root()
    cfg = default_config_path()

    async with CodeAnalysisAsyncClient.from_server_config_path(cfg) as client:
        uf = client.universal_files
        project_id, file_path = await _discover_text_file(client)
        print(f"Fixture: project_id={project_id} file_path={file_path!r}")

        prev = await uf.preview(project_id, file_path)
        if not isinstance(prev, dict):
            raise AssertionError(f"preview unexpected: {prev!r}")
        print("  preview OK")

    print("UniversalFileClient.preview exercised.")
    return 0


def main() -> int:
    """Run the command-line entry point."""
    try:
        return asyncio.run(run_all())
    except KeyboardInterrupt:
        return 130
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
