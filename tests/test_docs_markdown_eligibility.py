"""Table-driven tests for Markdown docs indexing eligibility."""

from __future__ import annotations

import pytest

from code_analysis.core.docs_indexing_defaults import default_docs_indexing_dict
from code_analysis.core.docs_indexing_eligibility import (
    REASON_DISABLED,
    REASON_EXCLUDED,
    REASON_FILE_DELETED,
    REASON_FILE_MISSING,
    REASON_NOT_ALLOWED_DOCS_SUFFIX,
    REASON_NOT_INCLUDED,
    REASON_PATH_TRAVERSAL,
    is_docs_markdown_eligible,
)


def _enabled_full_config():
    """Return enabled full config."""
    d = default_docs_indexing_dict()
    d["enabled"] = True
    return d


@pytest.mark.parametrize(
    "docs_indexing,rel,file_exists,is_deleted,eligible,reasons_sub",
    [
        (_enabled_full_config(), "docs/guide.md", True, False, True, ()),
        (_enabled_full_config(), "docs/sub/guide.md", True, False, True, ()),
        (_enabled_full_config(), "docs/schema.json", True, False, True, ()),
        (_enabled_full_config(), "docs/config.yaml", True, False, True, ()),
        (_enabled_full_config(), "docs/legacy.yml", True, False, True, ()),
        (_enabled_full_config(), "README.md", True, False, True, ()),
        (
            _enabled_full_config(),
            "docs/plans/task.md",
            True,
            False,
            False,
            (REASON_EXCLUDED,),
        ),
        (
            _enabled_full_config(),
            "docs/guide.md",
            False,
            False,
            False,
            (REASON_FILE_MISSING,),
        ),
        (
            _enabled_full_config(),
            "docs/guide.md",
            True,
            True,
            False,
            (REASON_FILE_DELETED,),
        ),
        (
            _enabled_full_config(),
            "src/nope.md",
            True,
            False,
            False,
            (REASON_NOT_INCLUDED,),
        ),
        (
            _enabled_full_config(),
            "docs/guide.txt",
            True,
            False,
            False,
            (REASON_NOT_ALLOWED_DOCS_SUFFIX,),
        ),
        (
            _enabled_full_config(),
            "../etc/passwd.md",
            True,
            False,
            False,
            (REASON_PATH_TRAVERSAL,),
        ),
        (None, "docs/guide.md", True, False, False, (REASON_DISABLED,)),
        (
            default_docs_indexing_dict(),
            "docs/guide.md",
            True,
            False,
            False,
            (REASON_DISABLED,),
        ),
    ],
)
def test_is_docs_markdown_eligible_table(
    docs_indexing,
    rel: str,
    file_exists: bool,
    is_deleted: bool,
    eligible: bool,
    reasons_sub: tuple[str, ...],
) -> None:
    """Verify test is docs markdown eligible table."""
    v = is_docs_markdown_eligible(
        docs_indexing=docs_indexing,
        relative_path=rel,
        file_exists=file_exists,
        is_deleted=is_deleted,
    )
    assert v.eligible is eligible
    assert v.reasons == reasons_sub


def test_exclude_beats_include_same_path() -> None:
    """Verify test exclude beats include same path."""
    cfg = _enabled_full_config()
    cfg["include"] = ["docs/**/*.md", "docs/*.md", "README.md", "docs/plans/**"]
    cfg["exclude"] = ["docs/plans/**"]
    v = is_docs_markdown_eligible(
        docs_indexing=cfg,
        relative_path="docs/plans/x.md",
    )
    assert v.eligible is False
    assert REASON_EXCLUDED in v.reasons


def test_vectorize_does_not_affect_eligibility() -> None:
    """Verify test vectorize does not affect eligibility."""
    cfg = _enabled_full_config()
    cfg["vectorize"] = True
    v = is_docs_markdown_eligible(
        docs_indexing=cfg,
        relative_path="docs/guide.md",
    )
    assert v.eligible is True


def test_out_of_scope_not_under_roots_and_not_lifted_by_include() -> None:
    """Verify test out of scope not under roots and not lifted by include."""
    cfg = _enabled_full_config()
    cfg["roots"] = ["docs"]
    cfg["include"] = ["docs/*.md", "docs/**/*.md", "README.md"]
    cfg["exclude"] = []
    v = is_docs_markdown_eligible(
        docs_indexing=cfg,
        relative_path="other/tree.md",
    )
    assert v.eligible is False
    assert REASON_NOT_INCLUDED in v.reasons


def test_broad_include_outside_roots_with_star_md() -> None:
    """Verify test broad include outside roots with star md."""
    cfg = _enabled_full_config()
    cfg["roots"] = ["docs"]
    cfg["include"] = ["**/*.md"]
    cfg["exclude"] = []
    v = is_docs_markdown_eligible(
        docs_indexing=cfg,
        relative_path="src/foo.md",
    )
    assert v.eligible is True


def test_docs_relative_path_from_row_path_joins_project_root(tmp_path):
    """Indexer must not resolve project-relative DB paths against process cwd."""
    from code_analysis.core.indexing_worker_pkg.processing import (
        _docs_relative_path_from_row_path,
    )

    proj = tmp_path / "proj"
    (proj / "docs" / "plans" / "sub").mkdir(parents=True)
    md = proj / "docs" / "plans" / "sub" / "x.md"
    md.write_text("# t\n", encoding="utf-8")
    rel = _docs_relative_path_from_row_path(
        path="docs/plans/sub/x.md",
        project_root=proj,
    )
    assert rel == "docs/plans/sub/x.md"


def test_docs_relative_path_from_row_path_absolute_under_root(tmp_path):
    """Verify test docs relative path from row path absolute under root."""
    from code_analysis.core.indexing_worker_pkg.processing import (
        _docs_relative_path_from_row_path,
    )

    proj = tmp_path / "proj"
    (proj / "a").mkdir(parents=True)
    f = proj / "a" / "b.md"
    f.write_text("x", encoding="utf-8")
    rel = _docs_relative_path_from_row_path(path=str(f), project_root=proj)
    assert rel == "a/b.md"
