"""
Client-side per-call overhead regression guard (bug 8e6acb34, Fix 1).

Registered in ``realsrv_test.suites.s16_client_overhead`` (SUITE_NAME
"client_overhead").

MEASURED FACTS this check guards (taken by the orchestrator on the deployed
1.6.94 server; same ``health`` call, warm/reused connection, three clients):
``curl`` (no GIL) -- 1.2ms; a raw ``httpx.AsyncClient`` in Python -- 4.6ms;
this project's ``code_analysis_client`` -- 7.6ms. The ~3.0ms gap between
"raw httpx" and "code_analysis_client" was traced (see
``client/code_analysis_client/schema_disk_cache.py`` module docstring and
bug 8e6acb34's fix report) to ``get_command_schema()``'s in-memory-only
schema cache: it starts empty on every new process, and most real callers
(one-shot CLI invocations, individual agent tool calls, this very pipeline's
per-suite process) construct a fresh client and call a command once, so the
in-memory cache never pays for itself -- every such call was paying a full
extra ``help(cmdname)`` network round trip (measured: ~2.7-4.5ms) before the
command itself even ran. Fix 1 added a persisted, bounded-TTL on-disk schema
cache shared across process invocations against the same server.

This check reproduces that realistic pattern directly: for each of ``_N``
iterations it takes ONE reference sample (see below) immediately followed by
ONE client-under-test sample -- a BRAND NEW ``CodeAnalysisAsyncClient``
(mirroring a fresh process/tool invocation), TCP/TLS warmed with one
throwaway ``echo`` call, then timing exactly one ``call_validated("health",
{})`` (the first, and in a real one-shot caller the only, use of that
command's schema on this instance) -- and records ``client_ms - floor_ms``
as ONE overhead sample. INTERLEAVING the two measurements this tightly (as
opposed to running all ``_N`` floor samples then all ``_N`` client samples,
which this check did in an earlier revision) matters: this shared server's
network path shows real multi-millisecond drift over just a few hundred
milliseconds of wall clock, confirmed while calibrating this check --
un-interleaved medians of two back-to-back blocks disagreed with the true
systematic gap by more than the gap itself on some runs. Differencing
same-iteration pairs cancels most of that shared drift, exactly like this
project's own client-overhead profiling work for Fix 1.

Reference floor per iteration: the ALREADY-CONNECTED ``client`` fixture's
own cached ``httpx.AsyncClient`` (``JsonRpcTransport.get_async_http_client()``,
public), called with raw ``.post()`` directly -- i.e. every wrapper layer
(``JsonRpcClient``, ``CodeAnalysisAsyncClient``) is bypassed for this
measurement, leaving only the underlying warm, connection-reused httpx
client. This is the "raw httpx" data point from the bug report, not
``curl``'s 1.2ms: ``curl`` invoked as a subprocess per call was tried while
building this check and found to renegotiate TLS on every invocation in
this environment (no keep-alive reuse across separate process launches,
confirmed with ``curl -v``), which would grade subprocess/TLS-handshake
cost instead of client code -- exactly the kind of contaminated measurement
bug 8e6acb34 is about. Hand-rolling an independent ``httpx.AsyncClient``
from ``JsonRpcTransport``'s public ``cert``/``verify`` attributes was also
tried and rejected: ``verify`` stays the raw CA-path STRING even after the
client is warm (``_get_client()`` resolves the real SSLContext into a local
variable and never writes it back), so reconstructing it naively re-enables
hostname verification and fails outright against an IP address like
``192.168.254.26``. Reusing the fixture's own cached client sidesteps that
trap entirely while still measuring genuine httpx-level, non-wrapper cost.

Budget (``_CLIENT_OVERHEAD_BUDGET_MS`` = 2.0ms): calibrated empirically by
running THIS check's interleaved methodology against the real deployed
server in both states (bug 8e6acb34): with
``CODE_ANALYSIS_CLIENT_DISABLE_SCHEMA_CACHE=1`` (Fix 1's on-disk cache
disabled, i.e. the pre-fix per-instance-only-cache behavior) repeated runs
measured median per-iteration overhead consistently at or above ~2.7ms;
with the cache enabled (the fixed, default behavior) repeated runs measured
consistently at or below ~1.3ms. 2.0ms sits in that gap: above every
observed fixed-behavior run (headroom against ordinary jitter) and below
every observed pre-fix run (still catches the regression). This directly
matches the reported "7.6ms observed today against a ~1.2ms server floor"
pattern -- a ~6.4ms gap on that specific single-shot measurement; this
check's own reference floor (a warmed, shared connection, not a
per-call-fresh one) and its interleaved, differenced methodology naturally
read smaller and steadier in absolute terms, so the budget was calibrated
against ITS OWN measured pre-/post-fix ranges rather than reused verbatim
from the original number.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import statistics
import time
from typing import Dict, List, NamedTuple, Optional

import httpx

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.ambient_load import probe_ambient_load
from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext

CHECK_NAME = "client_overhead_over_server_floor_8e6acb34"

_N = 12
# See module docstring for the empirically-measured pre-/post-Fix-1 ranges
# this budget separates (>=~2.7ms vs <=~1.3ms median interleaved overhead
# on the real deployed server).
_CLIENT_OVERHEAD_BUDGET_MS = 2.0

_JSONRPC_HEALTH_PAYLOAD = {"jsonrpc": "2.0", "method": "health", "params": {}, "id": 1}
_JSONRPC_HEADERS = {"Content-Type": "application/json"}


class _IterationSample(NamedTuple):
    """One interleaved (floor, client-under-test) pair and their difference."""

    floor_ms: float
    client_ms: float
    overhead_ms: float


async def _one_floor_sample(url: str, raw_http_client: httpx.AsyncClient) -> float:
    """Time one raw-httpx POST to ``url`` on the already-warm shared client."""
    t0 = time.perf_counter()
    resp = await raw_http_client.post(
        url, json=_JSONRPC_HEALTH_PAYLOAD, headers=_JSONRPC_HEADERS
    )
    resp.raise_for_status()
    resp.json()
    return (time.perf_counter() - t0) * 1000.0


async def _one_client_sample(
    *,
    protocol: str,
    host: str,
    port: int,
    cert: Optional[str],
    key: Optional[str],
    ca: Optional[str],
) -> float:
    """Build a fresh client, warm its TCP/TLS, and time one ``call_validated("health")``."""
    fresh = CodeAnalysisAsyncClient(
        protocol=protocol,
        host=host,
        port=port,
        cert=cert,
        key=key,
        ca=ca,
        check_hostname=False,
        timeout=30.0,
    )
    try:
        await fresh.rpc.execute_command("echo", {"message": "warm"})
        t0 = time.perf_counter()
        await fresh.call_validated("health", {})
        return (time.perf_counter() - t0) * 1000.0
    finally:
        await fresh.close()


async def _run_interleaved_measurement(
    client: CodeAnalysisAsyncClient,
) -> List[_IterationSample]:
    """Return ``_N`` interleaved (floor, client, overhead) samples.

    Each iteration takes one reference sample immediately followed by one
    client-under-test sample, so both see nearly the same network/server
    conditions -- see module docstring for why this matters on this shared
    server's network path.
    """
    transport = client.rpc
    url = f"{transport.base_url}/api/jsonrpc"
    raw_http_client = await transport.get_async_http_client()

    # JsonRpcTransport exposes no public host/port/protocol/CA-path
    # accessors (only base_url/cert/verify/headers are public); reaching
    # into these private fields is the only way to rebuild an equivalent
    # fresh client without hardcoding connection details this check was not
    # given.
    host = transport._host
    port = transport._port
    protocol = transport._protocol
    ca_path = transport._ca
    cert_path = transport.cert[0] if transport.cert else None
    key_path = transport.cert[1] if transport.cert else None

    # Warm-up both measurement paths once before the timed round (absorbs
    # any first-touch cost on the shared connection; the fresh-client path
    # warms itself per iteration by construction).
    await _one_floor_sample(url, raw_http_client)

    samples: List[_IterationSample] = []
    for _ in range(_N):
        floor_ms = await _one_floor_sample(url, raw_http_client)
        client_ms = await _one_client_sample(
            protocol=protocol, host=host, port=port, cert=cert_path, key=key_path, ca=ca_path
        )
        samples.append(_IterationSample(floor_ms, client_ms, client_ms - floor_ms))
    return samples


async def run_client_overhead_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Assert the client's fresh-process per-call overhead stays within budget.

    Args:
        client: Connected async client (its resolved connection settings are
            reused to build both the reference and the client-under-test
            connections).
        fixtures: Only ``fixtures.project_id`` is used, to run the shared
            ambient-load pre-measurement probe (see below) -- this check
            otherwise targets no project data, only the ``health`` control
            call.

    Returns:
        One-entry map keyed by :data:`CHECK_NAME`.
    """
    # Ambient-load gate (bug 2aaac911), same mechanism s11/s15 already use:
    # this check's own full-sweep run exposed real interference from a
    # neighbouring suite's residual concurrent load (s15's own deliberate
    # 8-way concurrent probe, immediately before s16 in suite-discovery
    # order) inflating overhead_median_ms just past budget on an otherwise
    # healthy build. Skip the timed round entirely rather than report that
    # noise as a verdict.
    probe_degraded, probe_avg, probe_detail = await probe_ambient_load(
        client, fixtures.project_id
    )
    if probe_degraded:
        reason = (
            f"ambient load detected before measurement started -- skipping "
            f"the timed round rather than reporting noise as a verdict "
            f"(bug 2aaac911): last_probe_avg_s={probe_avg:.4f} {probe_detail}"
        )
        return {
            CHECK_NAME: CommandOutcome(
                CHECK_NAME, Bucket.BUCKET_A, Status.INCONCLUSIVE, reason
            )
        }

    try:
        samples = await _run_interleaved_measurement(client)
    except Exception as exc:  # noqa: BLE001 - recorded as data, not raised
        return {
            CHECK_NAME: CommandOutcome(
                CHECK_NAME,
                Bucket.BUCKET_A,
                Status.FAILED,
                f"measurement round crashed: {truncate(repr(exc))}",
            )
        }

    floor_median = statistics.median(s.floor_ms for s in samples)
    client_median = statistics.median(s.client_ms for s in samples)
    overhead_median = statistics.median(s.overhead_ms for s in samples)

    reason = (
        f"N={_N} (interleaved per-iteration pairs); "
        f"raw_httpx_floor_median_ms={floor_median:.3f}; "
        f"client_fresh_process_median_ms={client_median:.3f}; "
        f"overhead_median_ms={overhead_median:.3f}; "
        f"budget_ms={_CLIENT_OVERHEAD_BUDGET_MS:.3f}"
    )
    if overhead_median > _CLIENT_OVERHEAD_BUDGET_MS:
        status = Status.FAILED
        reason = f"client per-call overhead exceeded its budget: {reason}"
    else:
        status = Status.EXECUTED_OK
        reason = f"client per-call overhead within budget: {reason}"

    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}
