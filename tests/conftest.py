"""
Pytest fixtures for MCP commands testing.

Provides common fixtures for testing MCP commands with DatabaseClient.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path

import pytest

TEST_SERVER_INSTANCE_ID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture(autouse=True)
def _partition_tests_by_server_instance_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """All DB queries in tests use a fixed server instance partition key.

    The ``setattr`` patches below rebind the ``get_server_instance_id`` /
    ``current_server_instance_id`` attribute on the two modules named in the
    string target. That only affects callers that access the function via a
    module-qualified attribute lookup; it does NOT affect the many modules
    that did ``from code_analysis.core.database.watch_dirs_partition import
    current_server_instance_id`` (or the equivalent for
    ``get_server_instance_id``) - a plain name import captures its own
    reference to the ORIGINAL function object at import time, before this
    per-test fixture ever runs, so those call sites are never redirected to
    ``_sid`` and instead execute the real implementation.

    The real implementation resolves ``registration.instance_uuid`` from
    whatever ``config.json`` ``Path.cwd() / "config.json"`` finds (see
    ``server_instance._resolve_active_config_path``). Several isolated
    command tests (file-editing session tests) intentionally patch only the
    database handle and rely on that real-config lookup being UNAVAILABLE -
    the comment in ``resolve_file_path_from_project`` documents this: no live
    config.json means ``get_project()`` raises ``FileNotFoundError``, which
    is caught and the test falls back to the mocked
    ``database.get_project()``. On a developer machine that has ever run the
    real server from this checkout, a genuine ``config.json`` sits at the
    repo root (gitignored, "machine-local ... never commit" per
    .gitignore) - so the disk lookup UNEXPECTEDLY SUCCEEDS with that
    machine's real instance_uuid, the scoped ``driver.select(...)`` call
    proceeds against the unconfigured mock, and the tests blow up with an
    unrelated ``ValueError`` from ``Project.from_dict`` instead of hitting
    the intended fallback. This makes the unit suite's outcome depend on
    ambient host state (a file outside git, outside pytest's control)
    instead of being deterministic.

    Force the config-file lookup to fail the same way in EVERY environment
    (matching "no config.json is bootstrapped" - the assumption the isolated
    tests are written against) by pointing
    ``_resolve_active_config_path()`` at a path that is guaranteed not to
    exist. Unlike the two ``setattr`` targets above, this interception point
    works for every caller regardless of which module imported
    ``current_server_instance_id`` / ``get_server_instance_id``: the name
    ``_resolve_active_config_path`` is only ever referenced from inside
    ``get_server_instance_id``'s own function body, which always resolves it
    via ``server_instance.py``'s own namespace (where this fixture patches
    it), never via whichever module happens to hold a reference to
    ``get_server_instance_id`` itself.

    ``test_server_instance_cache.py`` tests the real implementation directly
    and restores/overrides all of this per-test (see that module's own
    autouse fixture and explicit ``setenv``/``delenv`` calls), so it is
    unaffected by the blanket patch here.
    """

    def _sid(**_kwargs: object) -> str:
        """Return sid."""
        return TEST_SERVER_INSTANCE_ID

    missing_config_path = tmp_path_factory.mktemp("no-config") / "config.json"
    monkeypatch.setattr(
        "code_analysis.core.server_instance._resolve_active_config_path",
        lambda: missing_config_path,
    )
    monkeypatch.setattr(
        "code_analysis.core.server_instance.get_server_instance_id",
        _sid,
    )
    monkeypatch.setattr(
        "code_analysis.core.database.watch_dirs_partition.current_server_instance_id",
        _sid,
    )


@pytest.fixture(autouse=True)
def _isolate_git_xdg_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Keep subprocess git tests independent from inaccessible user config."""

    xdg_root = Path(tmp_path_factory.mktemp("git-xdg"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_root))


def pytest_configure(config) -> None:
    """Register custom marks."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration (slower, real DB/driver).",
    )
    config.addinivalue_line(
        "markers",
        "postgres: optional live PostgreSQL (e.g. CODE_ANALYSIS_POSTGRES_TEST_DSN).",
    )
