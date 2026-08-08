"""
Guards against the unit suite depending on machine-local state (bug dc4a2c1f).

Four tests used to pass in the developer's main checkout and fail in every
fresh ``git worktree``, because they inherited untracked state that only the
main checkout happens to carry:

* ``debian/install-package.sh`` could only find ``commentjson`` through a
  ``.venv`` sitting in the tree, so the two packaging tests died with
  CalledProcessError in a worktree;
* paginated search-session storage resolved from the active config, landing in
  the real ``/var/casmgr/data/search_sessions`` when no root ``config.json``
  was present -- PermissionError;
* a preview test read the project id out of the repo root's untracked
  ``projectid`` file -- FileNotFoundError.

Every parallel agent works in its own worktree, so this class of failure fired
for all of them, every time, and was repeatedly investigated as if it were a
regression. The checks below pin the three specific escapes; the real gate is
the success criterion from the bug: a fresh worktree must produce the same
result as the main checkout.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

from code_analysis.commands.base_mcp_command import BaseMCPCommand

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_search_sessions_root_is_redirected_away_from_real_storage() -> None:
    """The autouse fixture must keep session storage out of real server paths."""
    root = Path(BaseMCPCommand._get_search_sessions_root())

    assert not str(root).startswith("/var/casmgr"), (
        f"search-session storage resolved to real server storage: {root}"
    )
    assert _REPO_ROOT not in root.parents and root != _REPO_ROOT, (
        f"search-session storage resolved inside the checkout: {root}"
    )


def test_no_test_reads_the_untracked_projectid_file() -> None:
    """No test may source its project id from the repo root's ``projectid``.

    That file is untracked: present in the developer's checkout, absent in a
    fresh worktree.
    """
    offenders = []
    for path in sorted((_REPO_ROOT / "tests").rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "_repo_root() / \"projectid\"" in line:
                offenders.append(f"{path.relative_to(_REPO_ROOT)}:{lineno}")

    assert not offenders, (
        "tests read the repo root's untracked projectid file: " + ", ".join(offenders)
    )


def test_packaging_script_accepts_an_explicit_interpreter() -> None:
    """``install-package.sh`` must let a caller name the python to use.

    Without that door the script can only reach ``commentjson`` through a
    ``.venv`` in the tree, which is untracked machine-local state.
    """
    script = (_REPO_ROOT / "debian" / "install-package.sh").read_text(
        encoding="utf-8"
    )

    assert "CASMGR_PY" in script, (
        "install-package.sh no longer honours CASMGR_PY, so its interpreter "
        "again depends on whether a .venv happens to exist in the tree"
    )
