#!/usr/bin/env python3
"""
Prepare host watch-directory mounts before casmgr-server / Docker start.

Resolves watch dirs from:

- ``file_watcher.host_watch_catalog`` (UUID4-named dirs/symlinks + config path match)
- ``code_analysis.worker.watch_dirs`` (id + host path)

Then either:

- Creates symlinks ``STAGING_ROOT/{uuid}`` → host path (host / Debian install), or
- Writes a Docker Compose override with bind-mount lines.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from code_analysis.core.constants import (
    CASMGR_DOCKER_WATCH_ROOT,
    CASMGR_NATIVE_HOST_WATCH_ROOT,
)
from code_analysis.core.storage_paths import load_raw_config
from code_analysis.core.file_watcher_pkg.watch_dirs_mount_sync import (
    _is_uuid4_name,
    _path_is_writable_dir,
    resolve_effective_watch_mount_root,
    resolve_watch_mount_root,
)
from code_analysis.core.watch_dirs_host_resolve import (
    collect_host_watch_entries,
    format_docker_compose_watch_volumes,
    host_watch_catalog_from_config,
)

logger = logging.getLogger(__name__)


def _needs_symlink_staging(config_path: Path, result) -> bool:
    if result.entries:
        return True
    config_data = load_raw_config(config_path)
    if resolve_watch_mount_root(config_data) is not None:
        return True
    if host_watch_catalog_from_config(config_data) is not None:
        return True
    return False


def resolve_staging_root(
    config_path: Path,
    *,
    explicit: Path | None = None,
) -> Path | None:
    """
    Directory for ``{uuid}`` symlinks on the host.

    Returns ``None`` when there is nothing to prepare (no-op for systemd).
    """
    if explicit is not None:
        return explicit
    config_data = load_raw_config(config_path)
    effective = resolve_effective_watch_mount_root(config_data)
    if effective is not None:
        return effective
    if host_watch_catalog_from_config(config_data) is not None:
        return Path(CASMGR_NATIVE_HOST_WATCH_ROOT)
    raw_dirs = config_data.get("code_analysis", {}).get("worker", {})
    if isinstance(raw_dirs, dict):
        watch_dirs = raw_dirs.get("watch_dirs")
        if isinstance(watch_dirs, list) and watch_dirs:
            return Path(CASMGR_NATIVE_HOST_WATCH_ROOT)
    return None


def prepare_symlinks(
    staging_root: Path,
    *,
    dry_run: bool = False,
    result,
) -> int:
    """Create/update ``staging_root/{uuid}`` symlinks for collected host entries."""
    for msg in result.errors:
        logger.error("%s", msg)

    staging_root = staging_root.resolve()
    if not dry_run:
        try:
            staging_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error(
                "Cannot create watch staging directory %s: %s. "
                "On native host set file_watcher.watch_mount_root to %s and ensure "
                "systemd ReadWritePaths includes it.",
                staging_root,
                exc,
                CASMGR_NATIVE_HOST_WATCH_ROOT,
            )
            return 1

    active_ids = set(result.entries.keys())
    if staging_root.is_dir():
        for child in staging_root.iterdir():
            if not _is_uuid4_name(child.name):
                continue
            if child.name not in active_ids:
                logger.info("Removing stale staging entry %s", child)
                if not dry_run:
                    if child.is_symlink() or child.is_file():
                        child.unlink()
                    elif child.is_dir() and not any(child.iterdir()):
                        child.rmdir()

    for wid in sorted(result.entries):
        entry = result.entries[wid]
        link = staging_root / wid
        target = entry.host_path.resolve()
        if link.is_symlink():
            try:
                if link.resolve() == target:
                    logger.debug("Symlink ok %s -> %s", link, target)
                    continue
            except OSError:
                pass
        elif link.exists() and link.is_dir() and not link.is_symlink():
            logger.warning(
                "Staging path %s is a real directory (expected symlink); skipping",
                link,
            )
            continue
        logger.info("Link %s -> %s (%s)", link, target, entry.source)
        if not dry_run:
            if link.is_symlink() or link.is_file():
                link.unlink()
            elif link.is_dir():
                logger.error(
                    "Cannot replace directory with symlink: %s; fix manually", link
                )
                continue
            link.symlink_to(target, target_is_directory=True)

    if result.errors:
        return 1
    if not result.entries:
        logger.warning(
            "No watch directories collected; check host_watch_catalog and worker.watch_dirs"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare watch-directory symlinks or Docker compose mount fragment.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("/etc/casmgr/config.json"),
        help="Server config path (default: /etc/casmgr/config.json)",
    )
    parser.add_argument(
        "--staging-root",
        type=Path,
        default=None,
        help=(
            "Host staging directory (symlink mode). Defaults to effective "
            "watch_mount_root (native host: /var/casmgr/watched when /watched is RO)."
        ),
    )
    parser.add_argument(
        "--compose-out",
        type=Path,
        default=None,
        help="Write Docker Compose volume override fragment to this path",
    )
    parser.add_argument(
        "--container-watch-root",
        default=CASMGR_DOCKER_WATCH_ROOT,
        help="Container watch root for compose output (default: /watched)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log actions without creating symlinks or writing files",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    config_path = args.config.expanduser().resolve()
    if not config_path.is_file():
        logger.error("Config not found: %s", config_path)
        return 2

    result = collect_host_watch_entries(config_path)
    for msg in result.errors:
        logger.error("%s", msg)

    if args.compose_out is not None:
        text = format_docker_compose_watch_volumes(
            list(result.entries.values()),
            container_watch_root=args.container_watch_root,
        )
        if args.dry_run:
            print(text, end="")
        else:
            args.compose_out.parent.mkdir(parents=True, exist_ok=True)
            args.compose_out.write_text(text, encoding="utf-8")
            logger.info("Wrote compose override: %s", args.compose_out)

    if not _needs_symlink_staging(config_path, result) and args.compose_out is None:
        logger.debug("No watch-dir staging required; exiting")
        return 0 if not result.errors else 1

    staging = resolve_staging_root(config_path, explicit=args.staging_root)
    if staging is None:
        logger.error(
            "Watch-dir staging required but watch_mount_root is not configured"
        )
        return 1

    if result.entries and result.errors:
        logger.error(
            "Cannot stage watch dirs: resolve collection errors first (%s)",
            len(result.errors),
        )
        return 1

    if not args.dry_run and not _path_is_writable_dir(staging):
        logger.error(
            "Watch staging %s is not writable; set watch_mount_root to %s in config",
            staging,
            CASMGR_NATIVE_HOST_WATCH_ROOT,
        )
        return 1

    return prepare_symlinks(
        staging,
        dry_run=args.dry_run,
        result=result,
    )


if __name__ == "__main__":
    sys.exit(main())
