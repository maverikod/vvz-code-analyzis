"""
Live-server leak audit for livetest fixture projects (bug d5835fbf; feeds
93d45b21): a read-only detector, not a cleaner.

Two independent signals, either one alone is RED:

  (a) any REGISTERED (live) project whose name matches a known livetest
      fixture-name prefix -- a live stray means some run's teardown never
      even got as far as ``project_set_mark_del``.
  (b) any TRASH entry whose parsed ``original_name`` matches a fixture
      prefix AND whose ``deleted_at`` is older than
      :data:`DEFAULT_MAX_TRASH_AGE` -- an aged trash entry means
      ``project_set_mark_del`` ran but the ``permanently_delete_from_trash``
      purge never followed. This is the exact defect class fixed across
      ``livetests/realsrv_test/core/teardown.py`` and the ``lifecycle_*``
      teardown paths by
      ``realsrv_test.core.disposable_project.purge_disposable_project``. A
      grace window (default 2h) tolerates trash entries from a run still in
      flight (mark_del succeeded, the purge call just hasn't landed yet).

This module owns only the read-only inventory fetch and the classification;
it never mutates server state (no ``mark_del``/purge calls here) -- pair it
with the individual ``pipeline live-*`` checks (which DO purge their own
disposable projects) to actually clear a RED verdict.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

# Another project's own live fixtures (ai_editor) -- never ours to flag or
# touch, even though the name would otherwise match the generic "verify_"
# fallback bucket below. Keep this list ahead of FIXTURE_NAME_PREFIXES in
# every lookup: exclusion always wins.
ALWAYS_EXCLUDED_PREFIXES: Tuple[str, ...] = ("verify_editor_",)

# Every livetest-fixture project-name prefix this repo's suites create.
# Order does not affect the RED/GREEN classification (a name only needs to
# match ANY one prefix to count as a fixture); more specific prefixes are
# listed first only so the reported "bucket" breakdown reads naturally.
# Names matching none of these (e.g. a human's own project, "workmgr...")
# are never flagged -- no explicit exclusion entry is needed for them, they
# simply never match a prefix here.
FIXTURE_NAME_PREFIXES: Tuple[str, ...] = (
    "verify-global-search-",  # lifecycle_global_search.py (2 throwaway projects)
    "verify_lock_",  # lifecycle_project_lock.py rename target names
    "verify_indexer_usage_idem_",  # lifecycle_indexer_correctness.py
    "verify_vecbatchcap_",  # lifecycle_vectorization_batch_cap.py
    "verify_vecdimparity_",  # lifecycle_vector_dim_parity.py
    "verify_worker_activity_",  # lifecycle_worker_activity.py
    "verify_ignore_parity_",  # lifecycle_indexing_ignore_parity.py (src + target)
    "verify_trashrestore_",  # lifecycle_project_trash_restore.py
    "pipeline_live_",  # pipeline_cli.py's own --project-prefix default
    "verify_live_",  # realsrv-test CLI's own --project-prefix default
    "verify_",  # generic fallback: any other verify_* suite fixture
)

DEFAULT_MAX_TRASH_AGE = timedelta(hours=2)

_TRASH_TIMESTAMP_FORMAT = "%Y-%m-%dT%H-%M-%SZ"


def _matched_bucket(name: str) -> Optional[str]:
    """Return the fixture-prefix bucket ``name`` belongs to, or ``None``."""
    if not name:
        return None
    for excluded in ALWAYS_EXCLUDED_PREFIXES:
        if name.startswith(excluded):
            return None
    for prefix in FIXTURE_NAME_PREFIXES:
        if name.startswith(prefix):
            return prefix
    return None


def parse_trash_timestamp(raw: Any) -> Optional[datetime]:
    """Parse a trash item's ``deleted_at`` (``YYYY-MM-DDThh-mm-ssZ``) to aware UTC.

    Args:
        raw: The ``deleted_at`` value from a ``list_trashed_projects`` item.

    Returns:
        An aware UTC ``datetime``, or ``None`` on anything unparsable --
        callers must treat that as "age unknown", never as "old" (a parse
        failure must never manufacture a false RED).
    """
    if not raw or not isinstance(raw, str):
        return None
    try:
        parsed = datetime.strptime(raw, _TRASH_TIMESTAMP_FORMAT)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class LeakAuditResult:
    """Outcome of one leak-audit classification pass."""

    status: str  # "RED" or "GREEN"
    reason: str
    live_stray_names: Tuple[str, ...]
    aged_trash_folder_names: Tuple[str, ...]


def classify_leak_audit(
    live_project_names: Iterable[str],
    trash_items: Iterable[Mapping[str, Any]],
    *,
    now: datetime,
    max_trash_age: timedelta = DEFAULT_MAX_TRASH_AGE,
) -> LeakAuditResult:
    """Pure classifier: fixture-prefix live/trash inventories -> RED or GREEN.

    Args:
        live_project_names: Every REGISTERED (non-deleted) project's
            ``name`` the caller fetched. Extra, unrelated names are harmless
            noise -- this function only ever flags names that match a
            fixture prefix (see :data:`FIXTURE_NAME_PREFIXES`).
        trash_items: ``list_trashed_projects`` ``items`` rows (each with
            ``folder_name``/``original_name``/``deleted_at``).
        now: Caller-supplied "current time" (aware UTC) -- kept explicit so
            this stays a pure, deterministic function for unit tests.
        max_trash_age: Grace window before an aged fixture-prefix trash
            entry counts as a leak (default 2h).

    Returns:
        RED if any live fixture-prefix project exists, or any fixture-prefix
        trash entry is older than ``max_trash_age``; GREEN otherwise.
    """
    live_strays: List[Tuple[str, str]] = []
    for name in live_project_names:
        bucket = _matched_bucket(str(name))
        if bucket:
            live_strays.append((str(name), bucket))

    aged_trash: List[Tuple[str, str]] = []
    for item in trash_items:
        original_name = str(item.get("original_name") or "")
        bucket = _matched_bucket(original_name)
        if not bucket:
            continue
        deleted_at = parse_trash_timestamp(item.get("deleted_at"))
        if deleted_at is None:
            continue
        if now - deleted_at > max_trash_age:
            folder_name = str(item.get("folder_name") or original_name)
            aged_trash.append((folder_name, bucket))

    if not live_strays and not aged_trash:
        return LeakAuditResult(
            "GREEN", "no live or aged-trash fixture strays found", (), ()
        )

    parts: List[str] = []
    if live_strays:
        counts = Counter(bucket for _, bucket in live_strays)
        breakdown = ", ".join(f"{n}x {bucket}" for bucket, n in sorted(counts.items()))
        parts.append(f"{len(live_strays)} live stray fixture project(s) [{breakdown}]")
    if aged_trash:
        counts = Counter(bucket for _, bucket in aged_trash)
        breakdown = ", ".join(f"{n}x {bucket}" for bucket, n in sorted(counts.items()))
        hours = max_trash_age.total_seconds() / 3600.0
        plural = "y" if len(aged_trash) == 1 else "ies"
        parts.append(
            f"{len(aged_trash)} fixture trash entr{plural} older than "
            f"{hours:g}h [{breakdown}]"
        )
    return LeakAuditResult(
        "RED",
        "; ".join(parts),
        tuple(name for name, _ in live_strays),
        tuple(name for name, _ in aged_trash),
    )


async def _fetch_all_pages(
    client: Any, command: str, base_params: Mapping[str, Any]
) -> List[Dict[str, Any]]:
    """Page through a ``list_projects``-shaped paginated command (read-only)."""
    items: List[Dict[str, Any]] = []
    block_position = 1
    while True:
        params = dict(base_params)
        params["block_position"] = block_position
        params["page_size"] = 200
        resp = await client.call_validated(command, params)
        if not resp.get("success"):
            raise RuntimeError(f"{command} failed: {resp.get('error')!r}")
        data = resp.get("data") or {}
        page_items = data.get("items")
        if isinstance(page_items, list):
            items.extend(item for item in page_items if isinstance(item, dict))
        if not data.get("has_more"):
            break
        block_position += 1
    return items


async def fetch_live_leak_inventory(client: Any) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Read-only fetch of everything :func:`classify_leak_audit` needs.

    Args:
        client: Connected ``CodeAnalysisAsyncClient``.

    Returns:
        ``(live_project_names, trash_items)``. Live projects are fetched via
        two narrow, server-side ``name_contains`` substring passes ("verify"
        and "pipeline_live" -- broad enough to cover every entry in
        :data:`FIXTURE_NAME_PREFIXES`, filtered before pagination) instead of
        an unfiltered full-fleet scan; ``list_trashed_projects`` has no
        server-side filter, so it is fetched in full (one call, read-only).
    """
    live_names: List[str] = []
    seen_ids: set[str] = set()
    for substring in ("verify", "pipeline_live"):
        rows = await _fetch_all_pages(
            client,
            "list_projects",
            {"name_contains": substring, "include_deleted": False},
        )
        for row in rows:
            project_id = str(row.get("id") or "")
            if project_id:
                if project_id in seen_ids:
                    continue
                seen_ids.add(project_id)
            name = row.get("name") or row.get("root_path") or ""
            if name:
                live_names.append(str(name))

    trash_resp = await client.call_validated("list_trashed_projects", {})
    if not trash_resp.get("success"):
        raise RuntimeError(f"list_trashed_projects failed: {trash_resp.get('error')!r}")
    trash_data = trash_resp.get("data") or {}
    trash_items = [
        item for item in (trash_data.get("items") or []) if isinstance(item, dict)
    ]

    return live_names, trash_items


async def run_live_leak_audit(
    client: Any,
    *,
    now: Optional[datetime] = None,
    max_trash_age: timedelta = DEFAULT_MAX_TRASH_AGE,
) -> LeakAuditResult:
    """Fetch the live inventory (read-only) and classify it.

    Args:
        client: Connected ``CodeAnalysisAsyncClient``.
        now: Overrides "current time" for the age comparison (tests only);
            defaults to ``datetime.now(timezone.utc)``.
        max_trash_age: Forwarded to :func:`classify_leak_audit`.

    Returns:
        The classification result.
    """
    live_names, trash_items = await fetch_live_leak_inventory(client)
    return classify_leak_audit(
        live_names, trash_items, now=now or datetime.now(timezone.utc), max_trash_age=max_trash_age
    )


async def run_live_leak_audit_cli(
    *, host: str, port: int, ssl_paths: Mapping[str, str]
) -> int:
    """Connect, run the audit, print the verdict, and return an exit code.

    Args:
        host: Server host.
        port: Server port.
        ssl_paths: ``{"cert": ..., "key": ..., "ca": ...}`` mTLS file paths.

    Returns:
        0 on GREEN, 1 on RED or any connection/audit failure.
    """
    from code_analysis_client import CodeAnalysisAsyncClient

    settings = {
        "host": host,
        "port": port,
        "protocol": "https",
        "ssl": {
            "cert": ssl_paths["cert"],
            "key": ssl_paths["key"],
            "ca": ssl_paths["ca"],
        },
    }
    async with CodeAnalysisAsyncClient.from_adapter_settings(
        settings, check_hostname=False, timeout=120.0
    ) as client:
        try:
            await client.rpc.health()
        except Exception as exc:  # noqa: BLE001 - report, don't crash the CLI
            print(f"FAILED health-check: {exc!r}")
            return 1
        try:
            result = await run_live_leak_audit(client)
        except Exception as exc:  # noqa: BLE001 - report, don't crash the CLI
            print(f"FAILED live-leak-audit: {exc!r}")
            return 1

    print(f"{result.status}  live-leak-audit: {result.reason}")
    return 0 if result.status == "GREEN" else 1
