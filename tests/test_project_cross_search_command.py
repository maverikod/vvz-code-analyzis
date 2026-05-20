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
from code_analysis.commands.project_cross_search_command import (
    ProjectCrossSearchCommand,
)
from code_analysis.commands.project_cross_search_core import (
    PathFilterOptions,
    apply_mode,
    build_command_audit,
    json_safe_scalar,
    merge_evidence,
    normalize_file_path,
    normalize_fulltext_hit,
    normalize_grep_hit,
    normalize_semantic_hit,
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
    assert cls.use_queue is True


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


def test_merge_three_sources_high_confidence() -> None:
    path = "code_analysis/commands/sessions/session_create_command.py"
    semantic = [_item("semantic", path, score=0.9, text="session create")]
    fulltext = [_item("fulltext", path, score=-1.2, text="class SessionCreateCommand")]
    grep = [_item("grep", path, text="session_create", line_start=10)]
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
    grep = [_item("grep", path, text="foo", line_start=1)]
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
            mode="intersection",
            semantic_limit=10,
            fulltext_limit=10,
            grep_limit=50,
        )

    assert isinstance(result, SuccessResult)
    data = result.data
    assert data["success"] is True
    assert data["summary"]["warnings"]
    assert data["summary"]["warnings"][0]["source"] == "semantic"
    assert len(data["results"]) >= 1
    assert data["results"][0]["sources"]["fulltext"] is True
    assert data["results"][0]["sources"]["grep"] is True


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
        return SuccessResult(
            data={
                "matches": [
                    {
                        "relative_path": "code_analysis/query_engine.py",
                        "line_number": 2,
                        "line": f"match for {pattern}",
                        "block_id": None,
                        "block_type": None,
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
    assert data["summary"]["warnings"] == []
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
