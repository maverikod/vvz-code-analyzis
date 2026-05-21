"""
Unit tests for project_cross_search merge/scoring and command wiring.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
import pytest_asyncio
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.hooks import hooks
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

import code_analysis.hooks  # noqa: F401
from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.command_metadata_helpers import REQUIRED_METADATA_KEYS
from code_analysis.commands.fs_grep_budget import GREP_HARD_TIMEOUT
from code_analysis.commands.project_cross_search_command import (
    ProjectCrossSearchCommand,
)
from code_analysis.core.exceptions import ValidationError
from code_analysis.commands.project_cross_search_core import (
    GREP_LINE_ONLY_IGNORED,
    PathFilterOptions,
    apply_mode,
    build_command_audit,
    is_structural_grep_evidence,
    json_safe_scalar,
    merge_evidence,
    normalize_file_path,
    normalize_fulltext_hit,
    normalize_grep_hit,
    normalize_semantic_hit,
    partition_grep_for_cross_search,
)

_XPATH_REGRESSION_GREP_PATTERNS: tuple[str, ...] = (
    "xpath",
    "XPath",
    "selector",
    "path expression",
    "node_path",
    "query_engine",
    "session_id",
    "draft",
    "TreeSession",
    "node_id",
    "find_node",
)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _register_commands() -> None:
    hooks.execute_custom_commands_hooks(registry)


def test_project_cross_search_registered() -> None:
    cls = registry.get_command("project_cross_search")
    assert cls is ProjectCrossSearchCommand
    assert cls.category == "search"
    assert cls.use_queue is False
    props = cls.get_schema()["properties"]
    assert props["auto_queue_on_inline_timeout"]["default"] is True


def test_validate_params_preserves_zero_semantic_and_fulltext_limits() -> None:
    cmd = ProjectCrossSearchCommand()
    out = cmd.validate_params(
        {
            "project_id": "p",
            "query": "needle",
            "semantic_limit": 0,
            "fulltext_limit": 0,
            "grep_limit": 0,
        }
    )
    assert out["semantic_limit"] == 0
    assert out["fulltext_limit"] == 0
    assert out["grep_limit"] == 0


def test_validate_params_rejects_fast_text_only_with_structural_grep() -> None:
    cmd = ProjectCrossSearchCommand()
    with pytest.raises(ValidationError, match="fast_text_only"):
        cmd.validate_params(
            {
                "project_id": "p",
                "query": "needle",
                "require_structural_grep": True,
                "fast_text_only": True,
            }
        )


def test_project_cross_search_schema_exposes_fast_text_only() -> None:
    props = ProjectCrossSearchCommand.get_schema().get("properties") or {}
    assert "fast_text_only" in props
    assert "grep_hard_timeout_seconds" in props


def test_project_cross_search_metadata_meets_standard() -> None:
    cls = ProjectCrossSearchCommand
    meta = cls.metadata()
    for key in REQUIRED_METADATA_KEYS:
        assert key in meta, f"missing metadata key {key!r}"
    assert meta.get("usage_examples")
    schema_props = set((cls.get_schema().get("properties") or {}).keys())
    assert set(meta.get("parameters") or {}) <= schema_props


def _item(source: str, file_path: str, **extra: object) -> dict:
    base = {
        "source": source,
        "file_path": file_path,
        "line_start": extra.get("line_start"),
        "line_end": extra.get("line_end"),
        "score": extra.get("score"),
        "text": extra.get("text"),
        "entity_type": extra.get("entity_type"),
        "entity_name": extra.get("entity_name"),
        "metadata": extra.get("metadata") or {},
    }
    return base


def _structural_grep_item(file_path: str, *, node_ref: str = "stable-id-1") -> dict:
    return _item(
        "grep_unindexed",
        file_path,
        text="session_create",
        line_start=10,
        line_end=12,
        metadata={
            "enrichment_status": "enriched",
            "preview": {
                "command": "universal_file_preview",
                "file_path": file_path,
                "node_ref": node_ref,
            },
            "node_ref": node_ref,
            "selector": node_ref,
            "start_line": 10,
            "end_line": 12,
        },
    )


def test_merge_three_sources_high_confidence() -> None:
    path = "code_analysis/commands/sessions/session_create_command.py"
    semantic = [_item("semantic", path, score=0.9, text="session create")]
    fulltext = [_item("fulltext", path, score=-1.2, text="class SessionCreateCommand")]
    grep = [_structural_grep_item(path)]
    _, results, _ = merge_evidence(
        semantic,
        fulltext,
        grep,
        path_filters=PathFilterOptions(),
        mode="union",
        limit=20,
    )
    assert len(results) == 1
    row = results[0]
    assert row["evidence_score"] == 3
    assert row["confidence"] == "high"
    assert row["sources"] == {"semantic": True, "fulltext": True, "grep": True}


def test_merge_two_sources_medium_confidence() -> None:
    path = "code_analysis/foo.py"
    fulltext = [_item("fulltext", path, score=-0.5)]
    grep = [_structural_grep_item(path)]
    _, results, _ = merge_evidence(
        [],
        fulltext,
        grep,
        path_filters=PathFilterOptions(),
        mode="union",
        limit=20,
    )
    assert len(results) == 1
    assert results[0]["evidence_score"] == 2
    assert results[0]["confidence"] == "medium"


def test_strict_mode_filters_non_3of3() -> None:
    candidates = [
        {
            "evidence_score": 1,
            "sources": {"semantic": True, "fulltext": False, "grep": False},
        },
        {
            "evidence_score": 2,
            "sources": {"semantic": True, "fulltext": True, "grep": False},
        },
        {
            "evidence_score": 3,
            "sources": {"semantic": True, "fulltext": True, "grep": True},
        },
    ]
    out = apply_mode(candidates, "strict")
    assert len(out) == 1
    assert out[0]["evidence_score"] == 3


def test_intersection_mode_filters_single_source() -> None:
    candidates = [
        {
            "evidence_score": 1,
            "sources": {"semantic": True, "fulltext": False, "grep": False},
        },
        {
            "evidence_score": 2,
            "sources": {"semantic": True, "fulltext": True, "grep": False},
        },
    ]
    out = apply_mode(candidates, "intersection")
    assert len(out) == 1
    assert out[0]["evidence_score"] == 2


def test_command_audit_detects_session_guard() -> None:
    path = "code_analysis/commands/sessions/session_open_file_command.py"
    grep_evidence = [
        _item(
            "grep",
            path,
            text="touch_or_error(session_id)",
            line_start=40,
        ),
        _item(
            "grep",
            path,
            text='return ErrorResult(code="SESSION_NOT_FOUND")',
            line_start=55,
        ),
        _item(
            "grep",
            path,
            text="enforce_security_policy(",
            line_start=60,
        ),
    ]
    audit = build_command_audit(path, grep_evidence)
    assert audit["calls_touch_or_error"] is True
    assert audit["returns_SESSION_NOT_FOUND"] is True
    assert audit["calls_enforce_security_policy"] is True
    assert audit["command_name"] == "session_open_file"


def test_normalize_semantic_hit_json_serializes_numpy_scalars() -> None:
    hit = normalize_semantic_hit(
        {
            "file_path": "code_analysis/foo.py",
            "score": np.float32(0.91),
            "distance": np.float64(0.12),
            "line": 10,
            "text": "xpath selector",
        },
        Path("/tmp/proj"),
    )
    json.dumps(hit)
    _, results, _ = merge_evidence(
        [hit],
        [],
        [],
        path_filters=PathFilterOptions(file_pattern="code_analysis"),
        mode="union",
        limit=50,
    )
    json.dumps(results)


def test_normalize_fulltext_hit_accepts_decimal_bm25() -> None:
    hit = normalize_fulltext_hit(
        {
            "file_path": "code_analysis/bar.py",
            "content": "selector path",
            "bm25_score": Decimal("-1.25"),
        },
        None,
    )
    assert isinstance(hit["score"], float)
    json.dumps(hit)


def test_line_only_grep_ignored_in_merge() -> None:
    path = "code_analysis/foo.py"
    line_only = [_item("grep_unindexed", path, text="foo", line_start=1)]
    structural = [_structural_grep_item(path)]
    _, results, counts = merge_evidence(
        [],
        [],
        line_only + structural,
        path_filters=PathFilterOptions(),
        mode="union",
        limit=20,
    )
    assert counts["grep"] == 1
    assert counts["grep_line_only_ignored"] == 1
    assert results[0]["sources"]["grep"] is True
    assert len(results[0]["evidence"]["grep"]) == 1
    assert is_structural_grep_evidence(results[0]["evidence"]["grep"][0])


def test_partition_grep_for_cross_search() -> None:
    path = "a.py"
    hits = [
        _item("grep_unindexed", path, text="x"),
        _structural_grep_item(path),
    ]
    structural, line_only, n = partition_grep_for_cross_search(hits)
    assert n == 1
    assert len(structural) == 1
    assert len(line_only) == 1


def test_normalize_grep_hit_tolerates_missing_fields() -> None:
    hit = normalize_grep_hit({}, "xpath", None)
    assert hit["file_path"] == ""
    assert hit["line_start"] is None
    assert hit["metadata"]["pattern"] == "xpath"


def test_path_normalization_absolute_to_project_relative(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    abs_path = project_root / "src" / "module.py"
    abs_path.parent.mkdir()
    abs_path.write_text("x", encoding="utf-8")
    hit = normalize_fulltext_hit(
        {"file_path": str(abs_path), "content": "x", "bm25_score": -1.0},
        project_root,
    )
    assert hit["file_path"] == "src/module.py"
    assert normalize_file_path("src/module.py", project_root) == "src/module.py"


@pytest.mark.asyncio
async def test_execute_partial_success_with_warnings(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    (project_root / "foo.py").write_text("session_create\n", encoding="utf-8")

    mock_db = MagicMock()
    mock_db.full_text_search.return_value = [
        {
            "entity_type": "function",
            "entity_name": "session_create",
            "content": "def session_create(): pass",
            "docstring": None,
            "file_path": "foo.py",
            "bm25_score": -0.8,
        }
    ]
    mock_db.disconnect.return_value = None

    sem_err = ErrorResult(message="no vectors", code="PGVECTOR_INDEX_EMPTY")

    with (
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=project_root
        ),
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch(
            "code_analysis.commands.project_cross_search_command.SemanticSearchMCPCommand"
        ) as sem_cls,
        patch(
            "code_analysis.commands.project_cross_search_command.FsGrepCommand"
        ) as grep_cls,
    ):
        sem_inst = sem_cls.return_value
        sem_inst.execute = AsyncMock(return_value=sem_err)

        grep_inst = grep_cls.return_value
        grep_inst.execute = AsyncMock(
            return_value=SuccessResult(
                data={
                    "matches": [
                        {
                            "relative_path": "foo.py",
                            "line_number": 1,
                            "line": "session_create",
                            "block_id": None,
                            "block_type": None,
                        }
                    ]
                }
            )
        )

        cmd = ProjectCrossSearchCommand()
        result = await cmd.execute(
            project_id="test-proj",
            query="session_create",
            grep_patterns=["session_create"],
            mode="union",
            semantic_limit=10,
            fulltext_limit=10,
            grep_limit=50,
            require_structural_grep=True,
        )

    assert isinstance(result, SuccessResult)
    data = result.data
    assert data["success"] is True
    assert data["summary"]["warnings"]
    assert data["summary"]["warnings"][0]["source"] == "semantic"
    warn_codes = [w.get("code") for w in data["summary"]["warnings"]]
    assert GREP_LINE_ONLY_IGNORED in warn_codes
    assert len(data["results"]) >= 1
    assert data["results"][0]["sources"]["fulltext"] is True
    assert data["results"][0]["sources"]["grep"] is False
    assert data["results"][0]["evidence_score"] == 1


@pytest.mark.asyncio
async def test_execute_all_sources_fail(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()

    with (
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=project_root
        ),
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            side_effect=RuntimeError("db down"),
        ),
        patch(
            "code_analysis.commands.project_cross_search_command.SemanticSearchMCPCommand"
        ) as sem_cls,
        patch(
            "code_analysis.commands.project_cross_search_command.FsGrepCommand"
        ) as grep_cls,
    ):
        sem_inst = sem_cls.return_value
        sem_inst.execute = AsyncMock(
            return_value=ErrorResult(message="semantic fail", code="SEMANTIC_ERROR")
        )
        grep_inst = grep_cls.return_value
        grep_inst.execute = AsyncMock(
            return_value=ErrorResult(message="grep fail", code="GREP_ERROR")
        )

        cmd = ProjectCrossSearchCommand()
        result = await cmd.execute(
            project_id="test-proj",
            query="session_create",
            grep_patterns=["session_create"],
        )

    assert isinstance(result, ErrorResult)
    assert result.code == "CROSS_SEARCH_ERROR"


@pytest.mark.asyncio
async def test_execute_xpath_regression_grep_patterns_json_safe(
    tmp_path: Path,
) -> None:
    """Regression: XPath/selector audit params must not 500 on NumPy FTS metadata."""
    project_root = tmp_path / "proj"
    (project_root / "code_analysis").mkdir(parents=True)
    target = project_root / "code_analysis" / "query_engine.py"
    target.write_text(
        "class TreeSession:\n    def find_node(self, node_path, selector):\n        pass\n",
        encoding="utf-8",
    )

    mock_db = MagicMock()
    mock_db.full_text_search.return_value = [
        {
            "entity_type": "class",
            "entity_name": "TreeSession",
            "content": "xpath selector path expression",
            "docstring": None,
            "file_path": "code_analysis/query_engine.py",
            "bm25_score": Decimal("-0.42"),
        }
    ]
    mock_db.disconnect.return_value = None

    sem_ok = SuccessResult(
        data={
            "results": [
                {
                    "file_path": "code_analysis/query_engine.py",
                    "score": np.float32(0.88),
                    "distance": np.float64(0.05),
                    "line": 1,
                    "text": "TreeSession xpath",
                    "chunk_type": "class",
                }
            ]
        }
    )

    async def _grep_side_effect(**kwargs: object) -> SuccessResult:
        pattern = str(kwargs.get("pattern") or "")
        rel = "code_analysis/query_engine.py"
        node_ref = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        return SuccessResult(
            data={
                "matches": [
                    {
                        "relative_path": rel,
                        "line_number": 2,
                        "line": f"match for {pattern}",
                        "source": "grep_unindexed",
                        "grep_source": "disk",
                        "enrichment_status": "enriched",
                        "block_id": node_ref,
                        "node_ref": node_ref,
                        "selector": node_ref,
                        "start_line": 2,
                        "end_line": 2,
                        "preview": {
                            "command": "universal_file_preview",
                            "file_path": rel,
                            "node_ref": node_ref,
                        },
                    }
                ]
            }
        )

    with (
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=project_root
        ),
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch(
            "code_analysis.commands.project_cross_search_command.SemanticSearchMCPCommand"
        ) as sem_cls,
        patch(
            "code_analysis.commands.project_cross_search_command.FsGrepCommand"
        ) as grep_cls,
    ):
        sem_cls.return_value.execute = AsyncMock(return_value=sem_ok)
        grep_inst = grep_cls.return_value
        grep_inst.execute = AsyncMock(side_effect=_grep_side_effect)

        cmd = ProjectCrossSearchCommand()
        result = await cmd.execute(
            project_id="test-proj",
            query=(
                "XPath like query engine selector path expression tree node query "
                "without database current edit session draft"
            ),
            grep_patterns=list(_XPATH_REGRESSION_GREP_PATTERNS),
            mode="union",
            file_pattern="code_analysis",
            limit=50,
            semantic_limit=0,
            fulltext_limit=0,
        )

    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    assert not isinstance(result, ErrorResult)
    data = result.data
    assert data["success"] is True
    json.dumps(data)
    assert data["execution_mode"] in ("sync", "queued_recommended", "queued")
    assert "grep_budget" in data
    assert "warnings" in data
    assert len(data["results"]) >= 1
    grep_inst.execute.assert_awaited()
    # xpath/XPath dedupe case-insensitively in build_grep_pattern_list
    assert grep_inst.execute.await_count == 10
    assert len(data["search_plan"]["grep_patterns"]) == 10


def test_json_safe_scalar_coerces_numpy() -> None:
    assert json_safe_scalar(np.float32(0.5)) == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_execute_grep_only_xpath_sync_bounded(tmp_path: Path) -> None:
    """Grep-only XPath audit completes in sync with budget fields (no hang/500)."""
    project_root = tmp_path / "proj"
    pkg = project_root / "code_analysis"
    pkg.mkdir(parents=True)
    (pkg / "query_engine.py").write_text(
        "class TreeSession:\n    def find_node(self, xpath, selector):\n        pass\n",
        encoding="utf-8",
    )
    for i in range(5):
        (pkg / f"module_{i}.py").write_text(f"xpath = {i}\n", encoding="utf-8")

    with patch.object(
        BaseMCPCommand, "_resolve_project_root", return_value=project_root
    ):
        cmd = ProjectCrossSearchCommand()
        result = await cmd.execute(
            project_id="test-proj",
            query="xpath selector path expression",
            grep_patterns=["xpath"],
            file_pattern="code_analysis",
            semantic_limit=0,
            fulltext_limit=0,
            grep_limit=20,
            limit=10,
        )

    assert isinstance(result, (SuccessResult, ErrorResult))
    if isinstance(result, SuccessResult):
        data = result.data
        json.dumps(data)
        assert data["execution_mode"] in ("sync", "queued_recommended")
        assert data["grep_budget"]["limits"]["mode"] == "sync"
        assert data["grep_budget"]["usage"]["patterns_total"] >= 1
    else:
        assert result.code in ("CROSS_SEARCH_ERROR", "GREP_BUDGET_EXCEEDED")


@pytest.mark.asyncio
async def test_execute_queued_context_uses_full_grep_budget(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    (project_root / "code_analysis").mkdir(parents=True)
    (project_root / "code_analysis" / "a.py").write_text(
        "session_create\n", encoding="utf-8"
    )

    tracker = MagicMock()

    with (
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=project_root
        ),
        patch(
            "code_analysis.commands.project_cross_search_command.SemanticSearchMCPCommand"
        ) as sem_cls,
        patch(
            "code_analysis.commands.project_cross_search_command.FsGrepCommand"
        ) as grep_cls,
    ):
        sem_cls.return_value.execute = AsyncMock(
            return_value=SuccessResult(data={"results": []})
        )
        grep_cls.return_value.execute = AsyncMock(
            return_value=SuccessResult(
                data={
                    "matches": [
                        {
                            "relative_path": "code_analysis/a.py",
                            "line_number": 1,
                            "line": "session_create",
                            "block_id": None,
                            "block_type": None,
                        }
                    ],
                    "match_count": 1,
                    "files_scanned": 1,
                    "budget_exceeded": False,
                }
            )
        )
        cmd = ProjectCrossSearchCommand()
        result = await cmd.execute(
            project_id="test-proj",
            query="session_create",
            grep_patterns=["session_create"],
            semantic_limit=0,
            fulltext_limit=0,
            context={"progress_tracker": tracker},
        )

    assert isinstance(result, SuccessResult)
    assert result.data["execution_mode"] == "queued"
    assert result.data["grep_budget"]["limits"]["mode"] == "full"


@pytest.mark.asyncio
async def test_grep_budget_exceeded_warning_propagated(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    (project_root / "code_analysis").mkdir(parents=True)
    (project_root / "code_analysis" / "a.py").write_text("xpath\n", encoding="utf-8")

    async def _grep_budget_hit(**_kwargs: object) -> SuccessResult:
        return SuccessResult(
            data={
                "matches": [],
                "match_count": 0,
                "files_scanned": 150,
                "budget_exceeded": True,
                "budget_reason": "max_files_scanned",
            }
        )

    with (
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=project_root
        ),
        patch(
            "code_analysis.commands.project_cross_search_command.FsGrepCommand"
        ) as grep_cls,
    ):
        grep_cls.return_value.execute = AsyncMock(side_effect=_grep_budget_hit)
        cmd = ProjectCrossSearchCommand()
        result = await cmd.execute(
            project_id="test-proj",
            query="xpath",
            grep_patterns=["xpath"],
            file_pattern="code_analysis",
            semantic_limit=0,
            fulltext_limit=0,
        )

    assert isinstance(result, SuccessResult)
    codes = {w.get("code") for w in result.data.get("warnings") or []}
    assert "GREP_BUDGET_EXCEEDED" in codes
    assert result.data["execution_mode"] == "queued_recommended"
    assert result.data["grep_budget"]["usage"]["exceeded"] is True


@pytest.mark.asyncio
async def test_many_grep_patterns_marks_queued_recommended(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    (project_root / "code_analysis").mkdir(parents=True)
    (project_root / "code_analysis" / "a.py").write_text("x\n", encoding="utf-8")

    with (
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=project_root
        ),
        patch(
            "code_analysis.commands.project_cross_search_command.FsGrepCommand"
        ) as grep_cls,
    ):
        grep_cls.return_value.execute = AsyncMock(
            return_value=SuccessResult(
                data={"matches": [], "match_count": 0, "files_scanned": 1}
            )
        )
        cmd = ProjectCrossSearchCommand()
        patterns = [f"p{i}" for i in range(8)]
        result = await cmd.execute(
            project_id="test-proj",
            query="audit",
            grep_patterns=patterns,
            semantic_limit=0,
            fulltext_limit=0,
        )

    assert isinstance(result, SuccessResult)
    assert result.data["execution_mode"] == "queued_recommended"
    assert result.data.get("use_queue_recommended") is True


@pytest.mark.asyncio
async def test_cross_search_ignores_line_only_grep(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    (project_root / "mod.py").write_text("CSTQuery\n", encoding="utf-8")

    with (
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=project_root
        ),
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            side_effect=RuntimeError("no db"),
        ),
        patch(
            "code_analysis.commands.project_cross_search_command.SemanticSearchMCPCommand"
        ) as sem_cls,
        patch(
            "code_analysis.commands.project_cross_search_command.FsGrepCommand"
        ) as grep_cls,
    ):
        sem_cls.return_value.execute = AsyncMock(
            return_value=SuccessResult(data={"results": []})
        )
        grep_cls.return_value.execute = AsyncMock(
            return_value=SuccessResult(
                data={
                    "matches": [
                        {
                            "relative_path": "mod.py",
                            "line_number": 1,
                            "line": "CSTQuery",
                            "source": "grep_unindexed",
                            "grep_source": "disk",
                            "enrichment_status": "skipped_fast_text_only",
                        }
                    ]
                }
            )
        )
        result = await ProjectCrossSearchCommand().execute(
            project_id="test-proj",
            query="CSTQuery",
            grep_patterns=["CSTQuery"],
            semantic_limit=0,
            fulltext_limit=0,
            grep_limit=10,
            require_structural_grep=True,
        )

    assert isinstance(result, SuccessResult)
    codes = [w.get("code") for w in result.data.get("warnings") or []]
    assert GREP_LINE_ONLY_IGNORED in codes
    assert result.data["summary"]["source_counts"]["grep"] == 0
    assert not result.data["results"]


@pytest.mark.asyncio
async def test_cross_search_counts_structural_grep(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    rel = "code_analysis/mod.py"
    (project_root / "code_analysis").mkdir(parents=True)
    (project_root / rel).write_text("def f():\n    CSTQuery\n", encoding="utf-8")

    node_ref = "11111111-2222-4333-8444-555555555555"
    with (
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=project_root
        ),
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            side_effect=RuntimeError("no db"),
        ),
        patch(
            "code_analysis.commands.project_cross_search_command.SemanticSearchMCPCommand"
        ) as sem_cls,
        patch(
            "code_analysis.commands.project_cross_search_command.FsGrepCommand"
        ) as grep_cls,
    ):
        sem_cls.return_value.execute = AsyncMock(
            return_value=SuccessResult(data={"results": []})
        )
        grep_cls.return_value.execute = AsyncMock(
            return_value=SuccessResult(
                data={
                    "matches": [
                        {
                            "relative_path": rel,
                            "line_number": 2,
                            "line": "    CSTQuery",
                            "source": "grep_unindexed",
                            "grep_source": "disk",
                            "enrichment_status": "enriched",
                            "block_id": node_ref,
                            "node_ref": node_ref,
                            "selector": node_ref,
                            "start_line": 1,
                            "end_line": 2,
                            "preview": {
                                "command": "universal_file_preview",
                                "file_path": rel,
                                "node_ref": node_ref,
                            },
                        }
                    ]
                }
            )
        )
        result = await ProjectCrossSearchCommand().execute(
            project_id="test-proj",
            query="CSTQuery",
            grep_patterns=["CSTQuery"],
            mode="union",
            semantic_limit=0,
            fulltext_limit=0,
            grep_limit=10,
            require_structural_grep=True,
        )

    assert isinstance(result, SuccessResult)
    assert result.data["summary"]["source_counts"]["grep"] == 1
    assert len(result.data["results"]) >= 1
    row = result.data["results"][0]
    assert row["sources"]["grep"] is True
    assert row["evidence_score"] == 1
    grep_ev = row["evidence"]["grep"][0]
    assert grep_ev["metadata"]["preview"]
    assert grep_ev["metadata"]["node_ref"] == node_ref
    assert grep_ev["metadata"]["enrichment_status"] == "enriched"


@pytest.mark.asyncio
async def test_execute_search_plan_preserves_zero_limits(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True)
    (project_root / "a.py").write_text("needle\n", encoding="utf-8")

    node_ref = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"

    async def _semantic_must_not_run(**_kwargs: object) -> SuccessResult:
        raise AssertionError("semantic phase must be skipped when semantic_limit=0")

    with (
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=project_root
        ),
        patch(
            "code_analysis.commands.project_cross_search_command.SemanticSearchMCPCommand"
        ) as sem_cls,
        patch(
            "code_analysis.commands.project_cross_search_command.SearchCommand"
        ) as ft_cls,
        patch(
            "code_analysis.commands.project_cross_search_command.FsGrepCommand"
        ) as grep_cls,
    ):
        sem_cls.return_value.execute = AsyncMock(side_effect=_semantic_must_not_run)
        ft_cls.side_effect = AssertionError(
            "fulltext phase must be skipped when fulltext_limit=0"
        )
        grep_cls.return_value.execute = AsyncMock(
            return_value=SuccessResult(
                data={
                    "matches": [
                        {
                            "relative_path": "a.py",
                            "line_number": 1,
                            "line": "needle",
                            "source": "grep_unindexed",
                            "enrichment_status": "enriched",
                            "node_ref": node_ref,
                            "selector": node_ref,
                            "preview": {
                                "command": "universal_file_preview",
                                "file_path": "a.py",
                                "node_ref": node_ref,
                            },
                        }
                    ],
                    "match_count": 1,
                    "files_scanned": 1,
                }
            )
        )
        result = await ProjectCrossSearchCommand().execute(
            project_id="test-proj",
            query="needle",
            grep_patterns=["needle"],
            semantic_limit=0,
            fulltext_limit=0,
            mode="union",
        )

    assert isinstance(result, SuccessResult)
    plan = result.data["search_plan"]
    assert plan["semantic_limit"] == 0
    assert plan["fulltext_limit"] == 0
    assert result.data["summary"]["source_counts"]["semantic"] == 0
    assert result.data["summary"]["source_counts"]["fulltext"] == 0
    assert result.data["summary"]["source_counts"]["grep"] >= 1


@pytest.mark.asyncio
async def test_cross_search_partial_success_when_grep_hard_timeout(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True)
    (project_root / "a.py").write_text("needle\n", encoding="utf-8")

    sem_hit = {
        "file_path": "a.py",
        "score": 0.9,
        "text": "needle",
        "line": 1,
    }

    async def _grep_hard_timeout(**_kwargs: object) -> ErrorResult:
        return ErrorResult(
            message="fs_grep exceeded hard timeout and was stopped.",
            code=GREP_HARD_TIMEOUT,
            details={"hard_timeout_seconds": 1},
        )

    with (
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=project_root
        ),
        patch(
            "code_analysis.commands.project_cross_search_command.SemanticSearchMCPCommand"
        ) as sem_cls,
        patch(
            "code_analysis.commands.project_cross_search_command.FsGrepCommand"
        ) as grep_cls,
    ):
        sem_cls.return_value.execute = AsyncMock(
            return_value=SuccessResult(data={"results": [sem_hit]})
        )
        grep_cls.return_value.execute = AsyncMock(side_effect=_grep_hard_timeout)
        result = await ProjectCrossSearchCommand().execute(
            project_id="test-proj",
            query="needle",
            grep_patterns=["needle"],
            semantic_limit=5,
            fulltext_limit=0,
            grep_hard_timeout_seconds=1,
        )

    assert isinstance(result, SuccessResult)
    codes = {w.get("code") for w in result.data.get("warnings") or []}
    assert GREP_HARD_TIMEOUT in codes
    assert result.data["summary"]["source_counts"]["grep"] == 0
    assert result.data["summary"]["source_counts"]["semantic"] >= 1


@pytest.mark.asyncio
async def test_cross_search_error_when_only_grep_hard_timeout(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True)
    (project_root / "a.py").write_text("needle\n", encoding="utf-8")

    async def _grep_hard_timeout(**_kwargs: object) -> ErrorResult:
        return ErrorResult(
            message="fs_grep exceeded hard timeout and was stopped.",
            code=GREP_HARD_TIMEOUT,
        )

    with (
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=project_root
        ),
        patch(
            "code_analysis.commands.project_cross_search_command.FsGrepCommand"
        ) as grep_cls,
    ):
        grep_cls.return_value.execute = AsyncMock(side_effect=_grep_hard_timeout)
        result = await ProjectCrossSearchCommand().execute(
            project_id="test-proj",
            query="needle",
            grep_patterns=["needle"],
            semantic_limit=0,
            fulltext_limit=0,
            grep_hard_timeout_seconds=1,
        )

    assert isinstance(result, ErrorResult)
    assert result.code == "CROSS_SEARCH_ERROR"
    assert any(
        w.get("code") == GREP_HARD_TIMEOUT
        for w in (result.details or {}).get("warnings") or []
    )
