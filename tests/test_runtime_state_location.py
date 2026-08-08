"""
Runtime state must not live inside a source checkout (bug de794aa3).

Measured on the local checkout: ``data/`` held 15 GB of server runtime state --
a 13 GB PostgreSQL cluster, the SQLite database, FAISS indexes, locks, trash and
loose blobs -- all inside the git working tree. Our own project walk already
prunes ``data/``, so this is not a listing-performance defect; the defect is the
LOCATION. Anything recursive that does not share our ignore policy pays for it
(docker build context, backup and rsync jobs, antivirus, IDE indexers), and a
database cluster inside a working tree is one ``git clean -xfd`` away from gone.

Two halves are pinned here:

* the storage defaults, which resolved every runtime directory relative to the
  config file and therefore into the checkout;
* ``scripts/postgres_setup_from_env_config.py``, which hard-coded the cluster's
  bind mount to ``<repo>/data/postgres`` with no way to configure it at all.

Backward compatibility is part of the contract, so it is pinned too: an install
that already keeps state in the tree keeps working untouched, and production
(absolute paths under ``/var/casmgr``) resolves exactly as before. Moving an
existing install is an explicit, opt-in migration, never a silent switch.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_analysis.core.storage_paths import (
    resolve_search_sessions_root,
    resolve_storage_paths,
)


def _make_checkout(tmp_path: Path, *, with_data_dir: bool = False) -> Path:
    """Create a directory that looks like a git working tree with a config."""
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    (checkout / "config.json").write_text(
        json.dumps({"code_analysis": {}}), encoding="utf-8"
    )
    if with_data_dir:
        (checkout / "data").mkdir()
    return checkout


def _make_pg_cluster(directory: Path) -> Path:
    """Create something that looks like an initialised PostgreSQL data dir."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "PG_VERSION").write_text("16\n", encoding="utf-8")
    return directory


def _is_inside(path: Path, parent: Path) -> bool:
    """Return whether ``path`` lies within ``parent``."""
    return parent.resolve() in path.resolve().parents


@pytest.fixture()
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Neutralise ambient overrides and point the state home at a temp dir."""
    state_home = tmp_path / "state_home"
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))
    monkeypatch.delenv("CODE_ANALYSIS_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("CODE_ANALYSIS_POSTGRES_DATA_DIR", raising=False)
    return state_home


def test_storage_defaults_stay_out_of_a_source_checkout(
    tmp_path: Path, clean_env: Path
) -> None:
    """Bug de794aa3: a fresh checkout must not become the runtime state root."""
    checkout = _make_checkout(tmp_path)

    paths = resolve_storage_paths(
        config_data={"code_analysis": {}},
        config_path=checkout / "config.json",
    )

    for label, path in (
        ("db_path", paths.db_path),
        ("faiss_dir", paths.faiss_dir),
        ("locks_dir", paths.locks_dir),
        ("trash_dir", paths.trash_dir),
        ("backup_dir", paths.backup_dir),
    ):
        assert not _is_inside(path, checkout), f"{label} landed in the checkout: {path}"


def test_search_sessions_follow_the_runtime_root(
    tmp_path: Path, clean_env: Path
) -> None:
    """56k session files were the second largest in-tree offender."""
    checkout = _make_checkout(tmp_path)

    sessions = resolve_search_sessions_root(
        config_data={"code_analysis": {}},
        config_path=checkout / "config.json",
    )

    assert not _is_inside(sessions, checkout), sessions


def test_batch_output_default_stays_out_of_the_checkout(
    tmp_path: Path, clean_env: Path
) -> None:
    """``data/batch_output`` was the default and resolved against the config dir."""
    from code_analysis.core.storage_paths import resolve_batch_output_dir

    checkout = _make_checkout(tmp_path)

    resolved = resolve_batch_output_dir(
        config_path=checkout / "config.json", dir_str=""
    )

    assert not _is_inside(resolved, checkout), resolved


def test_postgres_host_data_dir_is_configurable_and_not_repo_bound(
    tmp_path: Path, clean_env: Path
) -> None:
    """The 13 GB cluster path was ``_repo_root() / "data" / "postgres"``, hard-coded."""
    from code_analysis.core.runtime_state_root import resolve_postgres_host_data_dir

    checkout = _make_checkout(tmp_path)

    resolved = resolve_postgres_host_data_dir(
        config_data={"code_analysis": {}},
        config_path=checkout / "config.json",
    )

    assert not _is_inside(resolved, checkout), resolved


def test_postgres_script_uses_the_shared_resolver(
    tmp_path: Path, clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bootstrap script must honour the configured path, not the repo root."""
    import scripts.postgres_setup_from_env_config as pg_setup

    checkout = _make_checkout(tmp_path)
    elsewhere = tmp_path / "elsewhere" / "postgres"
    monkeypatch.setenv("CODE_ANALYSIS_POSTGRES_DATA_DIR", str(elsewhere))

    resolved = pg_setup.postgres_host_data_dir(checkout / "config.json")

    assert resolved == elsewhere.resolve()
    assert not _is_inside(resolved, checkout)


# --- the resolver's own contract -------------------------------------------


def test_an_explicit_config_value_wins_over_everything(
    tmp_path: Path, clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Operators keep the last word; the environment does not override them."""
    from code_analysis.core.runtime_state_root import (
        SOURCE_CONFIG,
        resolve_runtime_state_root,
    )

    checkout = _make_checkout(tmp_path)
    chosen = tmp_path / "chosen"
    monkeypatch.setenv("CODE_ANALYSIS_RUNTIME_DIR", str(tmp_path / "from_env"))

    root = resolve_runtime_state_root(
        config_data={"code_analysis": {"storage": {"runtime_dir": str(chosen)}}},
        config_path=checkout / "config.json",
    )

    assert root.path == chosen.resolve()
    assert root.source == SOURCE_CONFIG


def test_the_environment_overrides_the_default(
    tmp_path: Path, clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dev box can relocate state without editing configuration."""
    from code_analysis.core.runtime_state_root import (
        SOURCE_ENV,
        resolve_runtime_state_root,
    )

    checkout = _make_checkout(tmp_path)
    from_env = tmp_path / "from_env"
    monkeypatch.setenv("CODE_ANALYSIS_RUNTIME_DIR", str(from_env))

    root = resolve_runtime_state_root(
        config_data={"code_analysis": {}},
        config_path=checkout / "config.json",
    )

    assert root.path == from_env.resolve()
    assert root.source == SOURCE_ENV


def test_an_existing_in_tree_data_dir_is_never_silently_abandoned(
    tmp_path: Path, clean_env: Path
) -> None:
    """The whole point: moving 15 GB is the operator's decision, not a side effect."""
    from code_analysis.core.runtime_state_root import (
        SOURCE_LEGACY_IN_TREE,
        resolve_runtime_state_root,
    )

    checkout = _make_checkout(tmp_path, with_data_dir=True)

    root = resolve_runtime_state_root(
        config_data={"code_analysis": {}},
        config_path=checkout / "config.json",
    )

    assert root.path == (checkout / "data").resolve()
    assert root.source == SOURCE_LEGACY_IN_TREE
    assert root.inside_checkout is True


def test_a_config_dir_outside_any_checkout_keeps_its_data_subdirectory(
    tmp_path: Path, clean_env: Path
) -> None:
    """Production layout: /etc/casmgr is not a working tree, nothing changes."""
    from code_analysis.core.runtime_state_root import (
        SOURCE_CONFIG_DIR,
        resolve_runtime_state_root,
    )

    etc = tmp_path / "etc" / "casmgr"
    etc.mkdir(parents=True)

    root = resolve_runtime_state_root(
        config_data={"code_analysis": {}},
        config_path=etc / "config.json",
    )

    assert root.path == (etc / "data").resolve()
    assert root.source == SOURCE_CONFIG_DIR
    assert root.inside_checkout is False


def test_the_default_state_home_follows_xdg(tmp_path: Path, clean_env: Path) -> None:
    """A fresh checkout parks its state under the user's state home."""
    from code_analysis.core.runtime_state_root import (
        SOURCE_STATE_HOME,
        STATE_DIR_NAME,
        resolve_runtime_state_root,
    )

    checkout = _make_checkout(tmp_path)

    root = resolve_runtime_state_root(
        config_data={"code_analysis": {}},
        config_path=checkout / "config.json",
    )

    assert root.path == (clean_env / STATE_DIR_NAME).resolve()
    assert root.source == SOURCE_STATE_HOME


def test_a_config_in_a_subdirectory_still_finds_the_checkout(
    tmp_path: Path, clean_env: Path
) -> None:
    """``.git`` sits at the top; the config may not. Walk up, do not guess."""
    from code_analysis.core.runtime_state_root import resolve_runtime_state_root

    checkout = _make_checkout(tmp_path)
    nested = checkout / "deploy" / "local"
    nested.mkdir(parents=True)

    root = resolve_runtime_state_root(
        config_data={"code_analysis": {}},
        config_path=nested / "config.json",
    )

    assert not _is_inside(root.path, checkout), root.path


def test_an_existing_cluster_pins_the_postgres_mount_in_place(
    tmp_path: Path, clean_env: Path
) -> None:
    """Re-pointing a bind mount away from a live cluster would look like data loss."""
    from code_analysis.core.runtime_state_root import (
        SOURCE_LEGACY_IN_TREE,
        postgres_host_data_dir_report,
    )

    checkout = _make_checkout(tmp_path, with_data_dir=True)
    cluster = _make_pg_cluster(checkout / "data" / "postgres")

    path, source = postgres_host_data_dir_report(
        config_data={"code_analysis": {}},
        config_path=checkout / "config.json",
    )

    assert path == cluster.resolve()
    assert source == SOURCE_LEGACY_IN_TREE


def test_production_absolute_paths_resolve_exactly_as_before(tmp_path: Path) -> None:
    """Regression guard: the deployed layout must not shift by a single byte."""
    etc = tmp_path / "etc" / "casmgr"
    etc.mkdir(parents=True)
    config_data = {
        "server": {"log_dir": "/var/log/casmgr"},
        "code_analysis": {
            "batch_output_dir": "/var/casmgr/data/batch_output",
            "storage": {
                "db_path": "/var/casmgr/data/code_analysis.db",
                "faiss_dir": "/var/casmgr/faiss",
                "locks_dir": "/var/casmgr/locks",
                "trash_dir": "/var/casmgr/trash",
            },
        },
    }

    paths = resolve_storage_paths(
        config_data=config_data, config_path=etc / "config.json"
    )

    assert paths.db_path == Path("/var/casmgr/data/code_analysis.db")
    assert paths.faiss_dir == Path("/var/casmgr/faiss")
    assert paths.locks_dir == Path("/var/casmgr/locks")
    assert paths.trash_dir == Path("/var/casmgr/trash")
    assert paths.backup_dir == Path("/var/casmgr/backups")
    assert paths.log_dir == Path("/var/log/casmgr")
    assert resolve_search_sessions_root(
        config_data=config_data, config_path=etc / "config.json"
    ) == Path("/var/casmgr/data/search_sessions")
