#!/usr/bin/env python3
"""
Move server runtime state out of a source checkout (bug de794aa3).

The resolver in ``code_analysis.core.runtime_state_root`` deliberately keeps an
existing in-tree ``data/`` directory where it is: quietly pointing a running
install at a different, empty directory is indistinguishable from data loss.
This script is the explicit way out — it reports what is there, refuses to touch
a cluster something is still attached to, and moves the state only when asked.

Usage (repo root, venv active)::

    python scripts/migrate_runtime_state.py                 # inventory only
    python scripts/migrate_runtime_state.py --apply         # move to the state home
    python scripts/migrate_runtime_state.py --apply --target /srv/casmgr-state

After a successful move the in-tree ``data/`` directory is gone, so the resolver
falls through to the state home on its own and no configuration edit is needed —
unless ``--target`` named somewhere else, in which case the script prints the
exact configuration to add.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from code_analysis.core.runtime_state_root import (  # noqa: E402
    CONFIG_KEY_RUNTIME_DIR,
    POSTGRES_DIR_NAME,
    SOURCE_LEGACY_IN_TREE,
    default_state_home,
    is_postgres_cluster_dir,
    postgres_host_data_dir_report,
    resolve_runtime_state_root,
)


def _resolve_config_path(explicit: str | None) -> Path:
    """Locate the config file the same way the bootstrap scripts do."""
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise SystemExit(f"ERROR: config file not found: {path}")
        return path
    for env_var in ("CONFIG_PATH", "CASMGR_CONFIG"):
        raw = os.environ.get(env_var)
        if raw and Path(raw).expanduser().is_file():
            return Path(raw).expanduser().resolve()
    for name in ("config-venv.json", "config.json"):
        candidate = _REPO_ROOT / name
        if candidate.is_file():
            return candidate.resolve()
    raise SystemExit(
        "ERROR: pass --config, or set CONFIG_PATH / CASMGR_CONFIG, "
        "or place config.json in the repository root."
    )


def _load_config(config_path: Path) -> Mapping[str, Any] | None:
    """Read the config file, tolerating a broken or absent one."""
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"WARNING: cannot read {config_path}: {exc}")
        return None


def _measure(path: Path) -> tuple[int, int]:
    """Return (total bytes, file count) beneath ``path``, following no symlinks."""
    total = 0
    count = 0
    for root, _dirs, files in os.walk(path, onerror=lambda _e: None):
        for name in files:
            entry = Path(root) / name
            try:
                stat = entry.lstat()
            except OSError:
                continue
            total += stat.st_size
            count += 1
    return (total, count)


def _human(size: int) -> str:
    """Render a byte count in the largest unit that keeps it readable."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _containers_binding(path: Path) -> list[str]:
    """Names of Docker containers (running or not) bind-mounting ``path``."""
    if shutil.which("docker") is None:
        print("NOTE: docker CLI not found; skipping the bind-mount safety check.")
        return []
    try:
        listed = subprocess.run(
            ["docker", "ps", "-aq"], capture_output=True, text=True, check=True
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        print(f"WARNING: cannot list Docker containers ({exc}); safety check skipped.")
        return []

    wanted = str(path.resolve())
    attached: list[str] = []
    for container_id in (line.strip() for line in listed.stdout.splitlines()):
        if not container_id:
            continue
        try:
            info = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "-f",
                    "{{.Name}}{{range .Mounts}} {{.Source}}{{end}}",
                    container_id,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.CalledProcessError, OSError):
            continue
        fields = info.stdout.split()
        if not fields:
            continue
        name = fields[0].lstrip("/")
        for source in fields[1:]:
            if source == wanted or source.startswith(wanted + os.sep):
                attached.append(name)
                break
    return attached


def _print_inventory(root: Path) -> None:
    """Print a per-entry size and file-count breakdown of the state root."""
    total, count = _measure(root)
    print(f"\nRuntime state at {root}: {_human(total)} in {count} files")
    entries: list[tuple[int, int, str]] = []
    for entry in sorted(root.iterdir()):
        if entry.is_dir() and not entry.is_symlink():
            size, files = _measure(entry)
        else:
            try:
                size, files = (entry.lstat().st_size, 1)
            except OSError:
                size, files = (0, 0)
        entries.append((size, files, entry.name))
    for size, files, name in sorted(entries, reverse=True)[:15]:
        print(f"  {_human(size):>10}  {files:>7} files  {name}")


def _check_movable(root: Path) -> list[str]:
    """Return the reasons this state root must not be moved right now."""
    blockers: list[str] = []
    cluster = root / POSTGRES_DIR_NAME
    if is_postgres_cluster_dir(cluster):
        attached = _containers_binding(cluster)
        if attached:
            blockers.append(
                f"{cluster} is bind-mounted by container(s): {', '.join(attached)}. "
                "Stop and remove them first (docker rm -f <name>), then re-run; "
                "recreate the container afterwards so it picks up the new path."
            )
    attached_root = _containers_binding(root)
    for name in attached_root:
        blockers.append(f"{root} is bind-mounted by container {name}.")
    return blockers


def _move_entries(root: Path, target: Path, entries: Iterable[Path]) -> None:
    """Move each entry into ``target``, refusing to overwrite anything."""
    target.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        destination = target / entry.name
        if destination.exists():
            raise SystemExit(
                f"ERROR: {destination} already exists; refusing to overwrite. "
                "Move or remove it and re-run."
            )
        print(f"  {entry} -> {destination}")
        shutil.move(str(entry), str(destination))


def main(argv: list[str] | None = None) -> int:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Report, and optionally move, server runtime state that lives inside "
            "the source checkout."
        )
    )
    parser.add_argument("--config", metavar="PATH", help="Path to config.json.")
    parser.add_argument(
        "--target",
        metavar="DIR",
        help="Destination directory (default: the user state home).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually move the state. Without this flag the script only reports.",
    )
    args = parser.parse_args(argv)

    config_path = _resolve_config_path(args.config)
    config_data = _load_config(config_path)
    root = resolve_runtime_state_root(config_data=config_data, config_path=config_path)
    pg_path, pg_source = postgres_host_data_dir_report(
        config_data=config_data, config_path=config_path
    )

    print(f"Config:          {config_path}")
    print(f"State root:      {root.path}  [{root.source}]")
    print(f"PostgreSQL data: {pg_path}  [{pg_source}]")

    if not root.inside_checkout and pg_source != SOURCE_LEGACY_IN_TREE:
        print("\nNothing to do: runtime state is already outside the checkout.")
        return 0

    if not root.path.is_dir():
        print(f"\nNothing to do: {root.path} does not exist.")
        return 0

    _print_inventory(root.path)

    blockers = _check_movable(root.path)
    if blockers:
        print("\nBLOCKED:")
        for reason in blockers:
            print(f"  - {reason}")
        return 1

    target = (
        Path(args.target).expanduser().resolve()
        if args.target
        else default_state_home()
    )
    print(f"\nTarget: {target}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to move the state.")
        return 0

    entries = sorted(root.path.iterdir())
    if not entries:
        print("Source directory is empty; nothing to move.")
    else:
        print("Moving:")
        _move_entries(root.path, target, entries)

    try:
        root.path.rmdir()
        print(f"Removed the now-empty {root.path}")
    except OSError as exc:
        print(f"NOTE: {root.path} not removed: {exc}")

    after = resolve_runtime_state_root(config_data=config_data, config_path=config_path)
    print(f"\nState root is now: {after.path}  [{after.source}]")
    if after.path != target:
        print(
            "\nThe resolver does not point at your target yet. Add this to "
            f"{config_path}:\n"
            '  "code_analysis": {"storage": '
            f'{{"{CONFIG_KEY_RUNTIME_DIR}": "{target}"}}}}'
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
