#!/usr/bin/env python3
"""
Live-server config-load-count diagnostics check (bug 9f5d860e regression guard).

Queries ``get_worker_status`` (worker_type=file_watcher) twice, ~10s apart, on a
live server and asserts:
  - the ``config_load_count`` diagnostic field is present in both responses, and
  - its delta over the sampling window is SMALL (a handful of loads at most, not
    hundreds) — a robust counter-based criterion instead of CPU sampling.

Root cause this guards against: ``get_server_instance_id()`` (config-file branch)
used to re-parse ``config.json`` (commentjson + lark grammar) on every call. The
file watcher calls it once per project per scan cycle, so on a multi-project
server this amplified into a config-reparse storm and 100% CPU. The fix
memoizes the config-file-backed instance id for the process lifetime
(``code_analysis/core/server_instance.py``); ``config_load_count`` is the
process-local counter incremented once per real disk load (cache miss).

This is a STANDALONE smoke check, deliberately NOT registered in
``_verify_client_all_commands_lifecycles.py`` (that shared registry drives the
always-on live command sweep; this script targets one specific regression and
must not be folded into it).

============================================================
USAGE: connecting to the real target server
============================================================
Same mTLS connection recipe as ``verify_client_all_commands_live.py`` — see
that script's module docstring for how to generate a disposable client
certificate. Example::

    python scripts/_verify_client_all_commands_lifecycle_watcher_config_load.py \\
        --host 192.168.254.26 --port 15010 \\
        --cert verifier.crt --key verifier.key --ca ca.crt

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_REPO = Path(__file__).resolve().parents[1]
_CLIENT = _REPO / "client"
_EXAMPLES = _CLIENT / "examples"
for _p in (_REPO, _CLIENT, _EXAMPLES):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from _common import chdir_repo_root, ensure_client_package_on_path  # noqa: E402

ensure_client_package_on_path()
chdir_repo_root()

from code_analysis_client import CodeAnalysisAsyncClient  # noqa: E402

# Sampling window and the acceptance threshold for the delta. A few loads (hot
# reload / concurrent first-call races) are tolerated; hundreds of loads in a
# ~10s window is exactly the reparse-storm signature bug 9f5d860e fixed.
_DEFAULT_SAMPLE_INTERVAL_SECONDS = 10.0
_DEFAULT_MAX_ACCEPTABLE_DELTA = 3


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments for this check.

    Returns:
        Parsed argparse namespace.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Live-server regression guard for bug 9f5d860e: asserts "
            "get_worker_status's config_load_count diagnostic stays flat "
            "(not a per-cycle reparse storm) over a sampling window."
        ),
    )
    parser.add_argument(
        "--host", default="192.168.254.26", help="Server host (default: %(default)s)."
    )
    parser.add_argument(
        "--port", type=int, default=15010, help="Server port (default: %(default)s)."
    )
    parser.add_argument(
        "--cert", required=True, help="Path to the client certificate (mTLS)."
    )
    parser.add_argument(
        "--key", required=True, help="Path to the client private key (mTLS)."
    )
    parser.add_argument(
        "--ca",
        required=True,
        help="Path to the CA certificate used to verify the server.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=_DEFAULT_SAMPLE_INTERVAL_SECONDS,
        help="Seconds between the two samples (default: %(default)s).",
    )
    parser.add_argument(
        "--max-delta",
        type=int,
        default=_DEFAULT_MAX_ACCEPTABLE_DELTA,
        help=(
            "Max acceptable config_load_count delta over the interval "
            "(default: %(default)s)."
        ),
    )
    return parser.parse_args()


async def _get_config_load_count(client: CodeAnalysisAsyncClient) -> Optional[int]:
    """Fetch ``config_load_count`` from ``get_worker_status`` for file_watcher.

    Args:
        client: Connected async client.

    Returns:
        The counter value, or ``None`` if the diagnostics field is absent
        (e.g. the watcher has not completed a scan cycle yet).
    """
    resp = await client.call_validated(
        "get_worker_status", {"worker_type": "file_watcher"}
    )
    if resp.get("success") is not True:
        raise RuntimeError(f"get_worker_status failed: {resp.get('error')!r}")
    data: Dict[str, Any] = resp.get("data") or {}
    value = data.get("config_load_count")
    return int(value) if value is not None else None


async def main() -> int:
    """Run the two-sample config_load_count regression check.

    Returns:
        0 when the diagnostic is present in both samples and its delta over
        the sampling window is within the acceptable threshold; 1 otherwise.
    """
    args = _parse_args()
    settings = {
        "host": args.host,
        "port": args.port,
        "protocol": "https",
        "ssl": {"cert": args.cert, "key": args.key, "ca": args.ca},
    }
    async with CodeAnalysisAsyncClient.from_adapter_settings(
        settings, check_hostname=False, timeout=120.0
    ) as client:
        try:
            await client.rpc.health()
        except Exception as exc:
            print(f"FAILED health-check: {exc!r}")
            return 1

        try:
            first = await _get_config_load_count(client)
        except Exception as exc:
            print(f"FAILED first sample: {exc!r}")
            return 1
        if first is None:
            print(
                "FAILED: config_load_count absent from get_worker_status response "
                "(diagnostics surface missing, or the watcher has not completed "
                "a scan cycle yet)"
            )
            return 1

        await asyncio.sleep(args.interval)

        try:
            second = await _get_config_load_count(client)
        except Exception as exc:
            print(f"FAILED second sample: {exc!r}")
            return 1
        if second is None:
            print("FAILED: config_load_count disappeared on the second sample")
            return 1

        delta = second - first
        print(
            f"config_load_count: first={first} second={second} delta={delta} "
            f"(interval={args.interval}s, max_acceptable={args.max_delta})"
        )
        if delta < 0:
            print(
                "FAILED: config_load_count went backwards "
                "(counter reset unexpectedly, e.g. process restart mid-check)"
            )
            return 1
        if delta > args.max_delta:
            print(
                f"FAILED: config_load_count delta {delta} exceeds threshold "
                f"{args.max_delta} over {args.interval}s — reparse-storm signature "
                "(bug 9f5d860e regression)"
            )
            return 1
        print("OK: config_load_count stayed flat — no per-cycle config reparse storm")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
