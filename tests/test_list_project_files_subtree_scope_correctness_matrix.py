"""
Correctness matrix for the subtree-scoped ``enumerate_project_paths`` walk (bug 25c8d9dd).

Compares the SCOPED result (``request_pattern`` set, walk bounded to the
pattern's static-prefix subtree when safe) against the FORCED-FULL-WALK
result (``request_pattern=None``, exactly the pre-25c8d9dd behavior:
whole-root walk, unconditional ``ignore_exceptions`` expansion) for one
fixture tree covering every origin type the design calls out: normal
source, ignored-without-exception, ignored-with-exception, hidden +
``show_hidden``, venv RECORD-allowlisted, venv ``ignore_exceptions`` with/
without ``include_venv_ignore_exceptions``, and vendor/build (never
returned). Both raw walks are filtered through the same
``relative_path_matches_listing_pattern`` a real ``list_project_files`` call
applies afterward, so this is the true end-to-end contract: the scoped path
must be byte-identical (same items, same order) to what the full walk would
have produced for that pattern -- never a subset, never a superset.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import List
from unittest.mock import patch

import pytest

from code_analysis.commands.file_management.relative_path_list_pattern import (
    canonical_relative_path,
    relative_path_matches_listing_pattern,
    static_prefix_of_listing_pattern,
)
from code_analysis.commands.project_fs_enumerate import (
    _resolve_scope_root_for_request_pattern,
    enumerate_project_paths,
)


def _matched_relative_paths(
    root: Path,
    *,
    pattern: str,
    show_venv: bool = False,
    python_only: bool = False,
    include_venv_ignore_exceptions: bool = False,
    show_hidden: bool = False,
    request_pattern: str | None,
) -> List[str]:
    """One ``enumerate_project_paths`` call, filtered by ``pattern`` like the real command.

    ``request_pattern=None`` reproduces the pre-25c8d9dd forced-full-walk,
    unconditional-exception-expansion behavior exactly (see
    ``enumerate_project_paths``'s own docstring); passing ``pattern`` itself
    lets the subtree-scoping optimization engage when safe.
    """
    paths = enumerate_project_paths(
        root,
        show_venv=show_venv,
        python_only=python_only,
        include_venv_ignore_exceptions=include_venv_ignore_exceptions,
        show_hidden=show_hidden,
        request_pattern=request_pattern,
    )
    return [
        canonical_relative_path(root, p, already_resolved=True)
        for p in paths
        if relative_path_matches_listing_pattern(
            canonical_relative_path(root, p, already_resolved=True), pattern
        )
    ]


def _build_matrix_fixture(root: Path) -> None:
    """Build the shared fixture tree covering every origin type in the matrix."""
    root.mkdir()
    pkg = root / "pkg"
    pkg.mkdir()
    (pkg / "normal.py").write_text("# normal source\n")
    (pkg / "sub").mkdir()
    (pkg / "sub" / "nested.py").write_text("# nested normal source\n")

    # ignored, no exception -- __pycache__ pruned unless show_hidden.
    cache_dir = pkg / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "blocked.pyc_src.py").write_text("# must never appear\n")

    # ignored, WITH a matching ignore_exceptions entry -- force-included.
    # "data" is pruned at WALK time (venv_path_policy's ignore_dirs unions in
    # DATA_DIR_NAME unconditionally) but is NOT itself one of the segment
    # names the final is_ignored_project_relative_path filter excludes (only
    # the "data/trash" / "data/versions" adjacent-pair shapes are) -- so a
    # plain "pkg/data/*" file is real, walk-pruned-but-exception-rescuable
    # content, unlike a cache dir (whose final-filter exclusion has no
    # override at all outside the venv segments).
    data_dir = pkg / "data"
    data_dir.mkdir()
    (data_dir / "rescued.py").write_text("# force-included via ignore_exceptions\n")

    # hidden dot-dir -- only with show_hidden.
    hidden_dir = pkg / ".hidden_dir"
    hidden_dir.mkdir()
    (hidden_dir / "h.py").write_text("# hidden source\n")

    # vendor/build -- always pruned, even under the scoped subtree.
    vendor_dir = pkg / "node_modules"
    vendor_dir.mkdir()
    (vendor_dir / "vendor.py").write_text("# must never appear\n")

    # venv RECORD-allowlisted site-packages file (outside "pkg", added via show_venv).
    sp = root / ".venv" / "lib" / "python3.12" / "site-packages"
    sp.mkdir(parents=True)
    pkg_dir = sp / "mypkg"
    pkg_dir.mkdir()
    (pkg_dir / "mod.py").write_text("x = 1\n")
    dist = sp / "mypkg-1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: mypkg\nVersion: 1.0\n")
    (dist / "RECORD").write_text("mypkg/mod.py,sha256=abc,12\n", encoding="utf-8")

    # venv ignore_exceptions file (outside "pkg").
    (root / ".venv" / "forced.py").write_text("# venv-forced\n")


_IGNORE_EXCEPTIONS = ["pkg/data/rescued.py", ".venv/forced.py"]


@pytest.mark.parametrize("show_hidden", [False, True])
def test_scoped_matches_forced_full_walk_for_glob_pattern(
    tmp_path: Path, show_hidden: bool
) -> None:
    """``pkg/*`` scoped result must byte-match the forced-full-walk result."""
    root = tmp_path / "proj"
    _build_matrix_fixture(root)
    pattern = "pkg/*"

    with patch(
        "code_analysis.commands.project_fs_enumerate.load_ignore_exceptions_from_config",
        return_value=_IGNORE_EXCEPTIONS,
    ):
        scoped = _matched_relative_paths(
            root, pattern=pattern, show_hidden=show_hidden, request_pattern=pattern
        )
        full = _matched_relative_paths(
            root, pattern=pattern, show_hidden=show_hidden, request_pattern=None
        )

    assert scoped == full

    # Explicit per-origin-type membership, so a vacuous "both empty" pass
    # could never hide a real regression.
    assert "pkg/normal.py" in scoped
    assert "pkg/sub/nested.py" in scoped
    assert "pkg/data/rescued.py" in scoped
    assert "pkg/node_modules/vendor.py" not in scoped
    if show_hidden:
        # show_hidden also un-prunes __pycache__ itself (ls -a-style), so the
        # walk now discovers "blocked.pyc_src.py" directly -- no
        # ignore_exceptions entry needed for it in this mode.
        assert "pkg/.hidden_dir/h.py" in scoped
        assert "pkg/__pycache__/blocked.pyc_src.py" in scoped
    else:
        assert "pkg/.hidden_dir/h.py" not in scoped
        assert "pkg/__pycache__/blocked.pyc_src.py" not in scoped
    # venv content lives outside "pkg" -- never matches this pattern either way.
    assert not any(".venv" in rel for rel in scoped)


def test_scoped_matches_forced_full_walk_for_dir_prefix_pattern(
    tmp_path: Path,
) -> None:
    """Literal directory-prefix ``pkg`` (no wildcard) must match the same way."""
    root = tmp_path / "proj"
    _build_matrix_fixture(root)
    pattern = "pkg"

    with patch(
        "code_analysis.commands.project_fs_enumerate.load_ignore_exceptions_from_config",
        return_value=_IGNORE_EXCEPTIONS,
    ):
        scoped = _matched_relative_paths(root, pattern=pattern, request_pattern=pattern)
        full = _matched_relative_paths(root, pattern=pattern, request_pattern=None)

    assert scoped == full
    assert "pkg/normal.py" in scoped
    assert "pkg/data/rescued.py" in scoped
    assert "pkg/__pycache__/blocked.pyc_src.py" not in scoped
    assert "pkg/node_modules/vendor.py" not in scoped


def test_venv_record_allowlisted_and_ignore_exceptions_unaffected_by_scoping(
    tmp_path: Path,
) -> None:
    """venv RECORD-allowlisted / ignore_exceptions origins: same result scoped vs full.

    These files live outside "pkg" and only ever surface via ``show_venv`` /
    ``include_venv_ignore_exceptions`` -- request-pattern scoping toward
    "pkg" must not disturb that (their inclusion is walk-independent), and
    they still must not match a "pkg/*" pattern filter either way.
    """
    root = tmp_path / "proj"
    _build_matrix_fixture(root)
    pattern = "pkg/*"

    with patch(
        "code_analysis.commands.project_fs_enumerate.load_ignore_exceptions_from_config",
        return_value=_IGNORE_EXCEPTIONS,
    ), patch(
        "code_analysis.commands.project_fs_enumerate.load_venv_site_packages_index_allowlist_from_config",
        return_value=["mypkg"],
    ):
        for include_venv_exc in (False, True):
            scoped = _matched_relative_paths(
                root,
                pattern=pattern,
                show_venv=True,
                include_venv_ignore_exceptions=include_venv_exc,
                request_pattern=pattern,
            )
            full = _matched_relative_paths(
                root,
                pattern=pattern,
                show_venv=True,
                include_venv_ignore_exceptions=include_venv_exc,
                request_pattern=None,
            )
            assert scoped == full
            assert not any(".venv" in rel for rel in scoped)


def test_scope_target_inside_always_pruned_dir_falls_back_to_root(
    tmp_path: Path,
) -> None:
    """A pattern naming a path under an always-ignored dir must never scope into it.

    ``os.walk`` never re-applies its own pruning rule to its own starting
    directory -- pointing it straight at "pkg/node_modules" would silently
    surface vendor files a full walk from the root would never reach (it
    prunes "node_modules" the moment it is discovered as a subdirectory).
    Condition 3a (conservativeness): the scope resolver must refuse and keep
    the project root as the walk start.
    """
    root = tmp_path / "proj"
    _build_matrix_fixture(root)
    pattern = "pkg/node_modules/*"

    resolved_root = root.resolve()
    static_prefix = static_prefix_of_listing_pattern(pattern)
    assert static_prefix == "pkg/node_modules"
    scope_root = _resolve_scope_root_for_request_pattern(
        resolved_root, static_prefix, show_hidden=False
    )
    assert scope_root == resolved_root

    scoped = _matched_relative_paths(root, pattern=pattern, request_pattern=pattern)
    full = _matched_relative_paths(root, pattern=pattern, request_pattern=None)
    assert scoped == full == []
