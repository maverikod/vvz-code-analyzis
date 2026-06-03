#!/usr/bin/env python3
"""Demo: paginated universal_file_preview via read_only_batch on live server."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
_CLIENT = _REPO / "client"
_EXAMPLES = _CLIENT / "examples"
for p in (_CLIENT, _EXAMPLES):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from _common import chdir_repo_root, default_config_path, ensure_client_package_on_path  # noqa: E402

ensure_client_package_on_path()
chdir_repo_root()

from code_analysis_client import CodeAnalysisAsyncClient  # noqa: E402

PROJECT_ID = json.loads((_REPO / "projectid").read_text(encoding="utf-8"))["id"]
LARGE_FILE = "code_analysis/core/project_bootstrap/template_data.py"
PAGE_CHARS = 4_000
MAX_PAGES = 4


def _data(resp: dict[str, Any]) -> dict[str, Any]:
    if resp.get("success") is not True:
        raise RuntimeError(resp)
    payload = resp.get("data")
    if not isinstance(payload, dict):
        raise RuntimeError(f"unexpected response shape: {resp!r}")
    return payload


async def main() -> None:
    config = default_config_path()
    async with CodeAnalysisAsyncClient.from_server_config_path(
        config, timeout=180.0
    ) as client:
        probe = _data(
            await client.call(
                "universal_file_preview",
                {
                    "project_id": PROJECT_ID,
                    "file_path": LARGE_FILE,
                    "preview_lines": 5,
                    "max_chars": PAGE_CHARS,
                    "preview_offset": 0,
                },
            )
        )
        total = int(probe["preview_total_chars"])
        print(f"file={LARGE_FILE} preview_total_chars={total}")

        offsets = list(range(0, min(total, PAGE_CHARS * MAX_PAGES), PAGE_CHARS)) or [0]
        invocations = [
            {
                "command": "universal_file_preview",
                "params": {
                    "project_id": PROJECT_ID,
                    "file_path": LARGE_FILE,
                    "preview_lines": 5,
                    "max_chars": PAGE_CHARS,
                    "preview_offset": off,
                },
            }
            for off in offsets
        ]
        print(f"read_only_batch pages={len(invocations)} offsets={offsets}")

        batch = _data(
            await client.call(
                "read_only_batch",
                {"invocations": invocations, "max_response_bytes": 512_000},
            )
        )
        if batch.get("inline") is not True:
            print("batch returned file reference:", batch.get("output_file"))
            print(f"file_size={batch.get('file_size')}")
            return

        stitched: list[str] = []
        for entry in batch.get("results") or []:
            result = (entry or {}).get("result") or {}
            if result.get("success") is not True:
                raise RuntimeError(entry)
            page = result.get("data") or {}
            chunk = page.get("preview_chunk")
            if not isinstance(chunk, str):
                raise RuntimeError(f"expected preview_chunk, got keys={list(page)}")
            stitched.append(chunk)
            print(
                f"  offset={offsets[len(stitched)-1]} chunk_len={len(chunk)} "
                f"has_more={page.get('preview_has_more')} "
                f"next={page.get('preview_next_offset')}"
            )

        combined = "".join(stitched)
        print(f"stitched_len={len(combined)} pages={len(stitched)}")
        if len(combined) > total:
            raise SystemExit("stitched payload longer than preview_total_chars")
        print("OK: read_only_batch paginated preview works")


if __name__ == "__main__":
    asyncio.run(main())
