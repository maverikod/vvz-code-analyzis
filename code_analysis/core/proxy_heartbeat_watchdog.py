"""
Independent proxy-heartbeat watchdog.

Runs in its own daemon OS thread, independent of the main asyncio loop, so it
keeps working even if the loop is momentarily busy. Two jobs:

1. Stall detection (defense in depth). It reads :mod:`loop_liveness`. If the
   main loop has not produced a beat for ``STALL_LIMIT`` seconds, the loop is
   wedged: the watchdog logs an error and dumps all thread tracebacks
   (``faulthandler``) so the blocking call is diagnosable, and it SUPPRESSES the
   independent heartbeat so the proxy correctly deregisters a truly-wedged
   server.

2. Independent heartbeat (best effort). While the loop is proven alive, it posts
   the same heartbeat payload the adapter posts (``/proxy/heartbeat``) over mTLS,
   reading the ``registration`` section of the server config directly. This is a
   safety net; the adapter's own heartbeat remains the primary channel.

This module does NOT modify ``mcp_proxy_adapter``; it only reads config and the
liveness beacon and posts via ``httpx``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import faulthandler
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from code_analysis.core import loop_liveness

logger = logging.getLogger(__name__)

# The loop is "busy" if it beats every LOOP_BEAT_INTERVAL (5s). Treat it as
# wedged only well beyond that, but below the proxy's ~130s stale window so the
# proxy still gets a chance to deregister a genuinely stuck server.
STALL_LIMIT_SECONDS: float = 45.0

# Liveness is checked at least this often, independently of the (longer)
# heartbeat interval, so stalls are detected promptly.
LIVENESS_CHECK_INTERVAL: float = 5.0


def _abs_path(value: Optional[str], base_dir: Path) -> Optional[str]:
    """Resolve a possibly-relative config path against the config directory."""
    if not value:
        return None
    p = Path(value)
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    return str(p)


def _resolve_settings(
    full_config: Dict[str, Any], config_path: Path
) -> Optional[Dict[str, Any]]:
    """Build heartbeat settings from the ``registration`` config section.

    Returns None when registration is disabled or the heartbeat URL is absent
    (the watchdog then runs in stall-detection-only mode).
    """
    reg = full_config.get("registration") if isinstance(full_config, dict) else None
    if not isinstance(reg, dict) or not reg.get("enabled", True):
        return None

    heartbeat = reg.get("heartbeat") if isinstance(reg.get("heartbeat"), dict) else {}
    url = heartbeat.get("url")
    if not url:
        # Derive from register_url base when only that is configured.
        register_url = str(reg.get("register_url") or "").strip()
        if register_url:
            base = register_url.rsplit("/", 1)[0]
            url = f"{base}/proxy/heartbeat"
    if not url:
        return None

    interval = heartbeat.get("interval") or reg.get("heartbeat_interval") or 30
    try:
        interval = max(2.0, float(interval))
    except (TypeError, ValueError):
        interval = 30.0

    base_dir = config_path.parent
    ssl_cfg = reg.get("ssl") if isinstance(reg.get("ssl"), dict) else {}
    cert_file = _abs_path(ssl_cfg.get("cert"), base_dir)
    key_file = _abs_path(ssl_cfg.get("key"), base_dir)
    ca_file = _abs_path(ssl_cfg.get("ca"), base_dir)

    cert: Optional[Tuple[str, str]] = (
        (cert_file, key_file) if cert_file and key_file else None
    )
    # Honor the registration SSL posture: when hostname checking is disabled (the
    # proxy server cert is not issued for the LAN IP), full httpx verification
    # against the CA fails, so verify server-side loosely and rely on the mTLS
    # client cert to authenticate to the local proxy.
    check_hostname = bool(ssl_cfg.get("check_hostname", False))
    verify: Union[bool, str] = ca_file if (ca_file and check_hostname) else False

    server = full_config.get("server") if isinstance(full_config, dict) else {}
    server = server if isinstance(server, dict) else {}
    protocol = str(server.get("protocol") or reg.get("protocol") or "https")
    advertised_host = str(server.get("advertised_host") or server.get("host") or "")
    port = server.get("port")
    server_url = reg.get("server_url")
    if not server_url and advertised_host and port:
        server_url = f"{protocol}://{advertised_host}:{int(port)}"

    metadata = dict(reg.get("metadata") or {})
    uuid_value = (
        reg.get("instance_uuid") or reg.get("uuid") or metadata.pop("uuid", None)
    )

    return {
        "url": str(url),
        "interval": interval,
        "cert": cert,
        "verify": verify,
        "server_id": str(reg.get("server_id") or ""),
        "server_url": str(server_url or ""),
        "metadata": metadata,
        "uuid": uuid_value,
    }


def _build_payload(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Build the heartbeat payload (matches the adapter's payload shape)."""
    payload: Dict[str, Any] = {
        "server_id": settings["server_id"],
        "server_url": settings["server_url"],
        "capabilities": [],
        "metadata": settings["metadata"],
        "timestamp": int(time.time()),
    }
    if settings.get("uuid"):
        payload["uuid"] = settings["uuid"]
    return payload


def _watchdog_main(
    full_config: Dict[str, Any],
    config_path: Path,
    heartbeat_stop: threading.Event,
) -> None:
    """Thread body: detect main-loop stalls and post independent heartbeats."""
    settings = _resolve_settings(full_config, config_path)
    if settings is None:
        logger.info(
            "Proxy heartbeat watchdog: registration/heartbeat not configured; "
            "running in stall-detection-only mode."
        )
        heartbeat_interval = LIVENESS_CHECK_INTERVAL
    else:
        heartbeat_interval = settings["interval"]
        logger.info(
            "Proxy heartbeat watchdog started (url=%s, interval=%.0fs, stall_limit=%.0fs)",
            settings["url"],
            heartbeat_interval,
            STALL_LIMIT_SECONDS,
        )
    # Tick on the shorter of liveness-check vs heartbeat interval so stalls are
    # detected promptly even when the heartbeat interval is long.
    tick = max(0.05, min(LIVENESS_CHECK_INTERVAL, heartbeat_interval))

    # httpx is an adapter dependency; import lazily so a missing dep degrades to
    # stall-detection-only rather than failing server startup.
    try:
        import httpx
    except Exception:  # pragma: no cover - httpx always present in practice
        httpx = None  # type: ignore[assignment]

    stall_logged = False
    client = None
    if settings is not None and httpx is not None:
        try:
            client = httpx.Client(
                cert=settings["cert"], verify=settings["verify"], timeout=10.0
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Watchdog could not create heartbeat client: %s", exc)
            client = None

    next_heartbeat = 0.0  # monotonic deadline; 0 → send on first healthy tick
    hb_fail_logged = False  # throttle: log a heartbeat failure once until it recovers

    def _maybe_send_heartbeat() -> None:
        """Send the independent heartbeat if due; throttle failure logging."""
        nonlocal next_heartbeat, hb_fail_logged
        if client is None or settings is None:
            return
        now = time.monotonic()
        if now < next_heartbeat:
            return
        next_heartbeat = now + heartbeat_interval
        try:
            resp = client.post(settings["url"], json=_build_payload(settings))
            resp.raise_for_status()
            if hb_fail_logged:
                logger.info("Independent proxy heartbeat recovered.")
                hb_fail_logged = False
        except Exception as exc:
            if not hb_fail_logged:
                logger.warning(
                    "Independent proxy heartbeat failing (suppressing repeats): %s",
                    exc,
                )
                hb_fail_logged = True

    try:
        while not heartbeat_stop.wait(tick):
            # During startup the beat coroutine has not run yet; don't treat the
            # boot window as a stall. Heartbeats below still flow (server booting).
            if not loop_liveness.has_beaten():
                _maybe_send_heartbeat()
                continue
            stale = loop_liveness.seconds_since_beat()
            if stale > STALL_LIMIT_SECONDS:
                if not stall_logged:
                    logger.error(
                        "MAIN EVENT LOOP STALLED for %.1fs — suppressing independent "
                        "heartbeat so the proxy can deregister a wedged server. "
                        "Dumping thread tracebacks for diagnosis.",
                        stale,
                    )
                    try:
                        faulthandler.dump_traceback()
                    except Exception:
                        pass
                    stall_logged = True
                continue
            if stall_logged:
                logger.warning(
                    "Main event loop recovered after stall (%.1fs since beat).",
                    stale,
                )
                stall_logged = False
            _maybe_send_heartbeat()
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def start_proxy_heartbeat_watchdog(
    full_config: Dict[str, Any],
    config_path: Path,
    heartbeat_stop: threading.Event,
) -> threading.Thread:
    """Start the watchdog daemon thread; stopped by setting ``heartbeat_stop``."""
    thread = threading.Thread(
        target=_watchdog_main,
        args=(full_config, config_path, heartbeat_stop),
        name="proxy-heartbeat-watchdog",
        daemon=True,
    )
    thread.start()
    return thread
