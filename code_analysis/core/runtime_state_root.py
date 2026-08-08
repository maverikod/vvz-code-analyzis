"""
Where server runtime state lives (bug de794aa3).

Runtime state -- the database, FAISS indexes, locks, trash, batch output, search
sessions and the PostgreSQL cluster -- used to be resolved relative to the config
file. In production that is right: ``config.json`` sits in ``/etc/casmgr`` and
every storage key names an absolute path under ``/var/casmgr``. In development
the config file sits in the source checkout, so the same rule parked 15 GB of
server state inside a git working tree, including a 13 GB PostgreSQL cluster
whose bind mount was hard-coded to the repository root with no way to configure
it at all.

This module is the one place that answers "where does runtime state go":

1. ``code_analysis.storage.runtime_dir`` -- an explicit operator decision, which
   always wins.
2. the ``CODE_ANALYSIS_RUNTIME_DIR`` environment variable, for relocating a dev
   box without editing configuration.
3. an existing ``<config_dir>/data`` inside a checkout -- KEPT. Moving gigabytes
   of live state is the operator's decision; a resolver that quietly pointed at
   a different directory would present an existing install as an empty one, which
   is indistinguishable from data loss. ``scripts/migrate_runtime_state.py`` is
   the explicit way out.
4. ``<config_dir>/data`` when the config file is not inside a checkout at all --
   the production layout, unchanged.
5. otherwise ``$XDG_STATE_HOME/code-analysis`` (default ``~/.local/state``): a
   fresh checkout never becomes a state directory in the first place.

Every resolution reports WHICH rule produced it, so a diagnostic can explain the
answer instead of leaving an operator to guess.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

from code_analysis.core.project_ignore_policy import DATA_DIR_BASENAME

CONFIG_SECTION_CODE_ANALYSIS = "code_analysis"
CONFIG_SECTION_STORAGE = "storage"
CONFIG_KEY_RUNTIME_DIR = "runtime_dir"
CONFIG_KEY_POSTGRES_DATA_DIR = "postgres_data_dir"

ENV_RUNTIME_DIR = "CODE_ANALYSIS_RUNTIME_DIR"
ENV_POSTGRES_DATA_DIR = "CODE_ANALYSIS_POSTGRES_DATA_DIR"
ENV_STATE_HOME = "XDG_STATE_HOME"

#: Directory name used inside the user state home for a checkout-based install.
STATE_DIR_NAME = "code-analysis"
#: Sub-directory of the runtime root holding the PostgreSQL cluster.
POSTGRES_DIR_NAME = "postgres"
#: Marker file present in every initialised PostgreSQL data directory.
POSTGRES_CLUSTER_MARKER = "PG_VERSION"

# Which rule produced a resolution. Reported, never guessed at by the caller.
SOURCE_CONFIG = "config"
SOURCE_ENV = "environment"
SOURCE_LEGACY_IN_TREE = "legacy_in_tree"
SOURCE_CONFIG_DIR = "config_dir"
SOURCE_STATE_HOME = "state_home"


@dataclass(frozen=True)
class RuntimeStateRoot:
    """
    A resolved runtime state root and the rule that produced it.

    Attributes:
        path: Absolute directory holding server runtime state.
        source: One of the ``SOURCE_*`` constants.
        checkout_root: The source checkout the config file lives in, or None
            when the config file is not inside one.
    """

    path: Path
    source: str
    checkout_root: Optional[Path]

    @property
    def inside_checkout(self) -> bool:
        """Whether the resolved root lies inside the source checkout."""
        if self.checkout_root is None:
            return False
        root = self.checkout_root.resolve()
        path = self.path.resolve()
        return path == root or root in path.parents


@lru_cache(maxsize=256)
def find_source_checkout_root(directory: Path) -> Optional[Path]:
    """
    Return the git working tree containing ``directory``, or None.

    Walks upward looking for ``.git`` -- a directory in a normal clone, a file
    in a worktree or submodule -- so a config file in a subdirectory of the
    checkout is recognised too.

    Cached: this runs on the storage-resolution path, which is called often
    enough that a fresh upward stat walk per call would be the same class of
    mistake as bug 8e6acb34. A checkout does not stop being a checkout during a
    process lifetime.

    Args:
        directory: Absolute directory to start from.

    Returns:
        Absolute path of the checkout root, or None when there is none.
    """
    try:
        current = Path(directory).resolve()
    except OSError:
        return None
    for candidate in (current, *current.parents):
        try:
            if (candidate / ".git").exists():
                return candidate
        except OSError:
            continue
    return None


def default_state_home(environ: Optional[Mapping[str, str]] = None) -> Path:
    """
    Return the user state directory for a checkout-based install.

    Args:
        environ: Environment mapping; defaults to ``os.environ``.

    Returns:
        ``$XDG_STATE_HOME/code-analysis``, falling back to
        ``~/.local/state/code-analysis``.
    """
    env = os.environ if environ is None else environ
    raw = (env.get(ENV_STATE_HOME) or "").strip()
    base = Path(raw).expanduser() if raw else Path.home() / ".local" / "state"
    return (base / STATE_DIR_NAME).resolve()


def _storage_section(config_data: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Return the ``code_analysis.storage`` mapping, or an empty one."""
    if not isinstance(config_data, Mapping):
        return {}
    code_analysis = config_data.get(CONFIG_SECTION_CODE_ANALYSIS)
    if not isinstance(code_analysis, Mapping):
        return {}
    storage = code_analysis.get(CONFIG_SECTION_STORAGE)
    return storage if isinstance(storage, Mapping) else {}


def _configured_path(
    config_data: Optional[Mapping[str, Any]],
    key: str,
    config_dir: Path,
) -> Optional[Path]:
    """Read a storage path key, resolved relative to the config directory."""
    raw = _storage_section(config_data).get(key)
    if not isinstance(raw, str) or not raw.strip():
        return None
    return _absolute(raw.strip(), config_dir)


def _env_path(
    environ: Optional[Mapping[str, str]], name: str, config_dir: Path
) -> Optional[Path]:
    """Read a path from the environment, resolved relative to the config dir."""
    env = os.environ if environ is None else environ
    raw = (env.get(name) or "").strip()
    if not raw:
        return None
    return _absolute(raw, config_dir)


def _absolute(value: str, base: Path) -> Path:
    """Expand ``value`` and make it absolute against ``base``."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def resolve_runtime_state_root(
    *,
    config_data: Optional[Mapping[str, Any]],
    config_path: Path,
    environ: Optional[Mapping[str, str]] = None,
) -> RuntimeStateRoot:
    """
    Resolve the directory that holds server runtime state.

    Precedence is documented in the module docstring; the short version is
    explicit configuration, then the environment, then "never abandon an
    existing in-tree install", then the production layout, then the user state
    home for a fresh checkout.

    Args:
        config_data: Raw config dict, or None when no config is available.
        config_path: Path to the config file; its directory anchors relative
            values and decides whether we are inside a checkout.
        environ: Environment mapping; defaults to ``os.environ``.

    Returns:
        The resolved root together with the rule that produced it.
    """
    config_dir = Path(config_path).resolve().parent
    checkout_root = find_source_checkout_root(config_dir)

    configured = _configured_path(config_data, CONFIG_KEY_RUNTIME_DIR, config_dir)
    if configured is not None:
        return RuntimeStateRoot(configured, SOURCE_CONFIG, checkout_root)

    from_env = _env_path(environ, ENV_RUNTIME_DIR, config_dir)
    if from_env is not None:
        return RuntimeStateRoot(from_env, SOURCE_ENV, checkout_root)

    legacy = (config_dir / DATA_DIR_BASENAME).resolve()
    if checkout_root is None:
        return RuntimeStateRoot(legacy, SOURCE_CONFIG_DIR, None)

    if legacy.is_dir():
        return RuntimeStateRoot(legacy, SOURCE_LEGACY_IN_TREE, checkout_root)

    return RuntimeStateRoot(
        default_state_home(environ), SOURCE_STATE_HOME, checkout_root
    )


def postgres_host_data_dir_report(
    *,
    config_data: Optional[Mapping[str, Any]],
    config_path: Path,
    environ: Optional[Mapping[str, str]] = None,
) -> Tuple[Path, str]:
    """
    Resolve the host directory bind-mounted as the PostgreSQL data directory.

    Same precedence as the runtime root, with one extra guard: an in-tree
    directory that already holds an initialised cluster stays where it is even
    when the runtime root has moved on. Re-pointing a bind mount away from a
    real cluster hands the operator an empty database and looks exactly like
    data loss; migrating a cluster is a deliberate, offline operation.

    Args:
        config_data: Raw config dict, or None.
        config_path: Path to the config file.
        environ: Environment mapping; defaults to ``os.environ``.

    Returns:
        Tuple of (absolute path, one of the ``SOURCE_*`` constants).
    """
    config_dir = Path(config_path).resolve().parent

    configured = _configured_path(config_data, CONFIG_KEY_POSTGRES_DATA_DIR, config_dir)
    if configured is not None:
        return (configured, SOURCE_CONFIG)

    from_env = _env_path(environ, ENV_POSTGRES_DATA_DIR, config_dir)
    if from_env is not None:
        return (from_env, SOURCE_ENV)

    legacy = (config_dir / DATA_DIR_BASENAME / POSTGRES_DIR_NAME).resolve()
    if is_postgres_cluster_dir(legacy):
        return (legacy, SOURCE_LEGACY_IN_TREE)

    root = resolve_runtime_state_root(
        config_data=config_data, config_path=config_path, environ=environ
    )
    return ((root.path / POSTGRES_DIR_NAME).resolve(), root.source)


def resolve_postgres_host_data_dir(
    *,
    config_data: Optional[Mapping[str, Any]],
    config_path: Path,
    environ: Optional[Mapping[str, str]] = None,
) -> Path:
    """Return only the path from :func:`postgres_host_data_dir_report`."""
    path, _source = postgres_host_data_dir_report(
        config_data=config_data, config_path=config_path, environ=environ
    )
    return path


def is_postgres_cluster_dir(path: Path) -> bool:
    """
    Return whether ``path`` holds an initialised PostgreSQL cluster.

    Args:
        path: Candidate data directory.

    Returns:
        True when the directory exists and contains ``PG_VERSION``.
    """
    try:
        return (path / POSTGRES_CLUSTER_MARKER).is_file()
    except OSError:
        return False


def describe_runtime_state_root(
    *,
    config_data: Optional[Mapping[str, Any]],
    config_path: Path,
    environ: Optional[Mapping[str, str]] = None,
) -> str:
    """
    Return a one-line human-readable explanation of the resolved root.

    Diagnostics only; carries paths, never credentials.
    """
    root = resolve_runtime_state_root(
        config_data=config_data, config_path=config_path, environ=environ
    )
    suffix = " (inside the source checkout)" if root.inside_checkout else ""
    return f"{root.path} [{root.source}]{suffix}"
