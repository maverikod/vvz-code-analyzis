"""
Integration tests for analyze_complexity, find_duplicates, comprehensive_analysis, semantic_search.

Verifies command execution and correctness of response structure and logic.
Requires: project root as cwd, config.json with code_analysis.db, vast_srv project registered.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

# Ensure project root is on path when running tests
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# vast_srv project_id from test_data/vast_srv/projectid
VAST_SRV_PROJECT_ID = "c86dded6-6f93-4fb0-be54-b6d7b739eeb9"


@pytest.fixture(scope="module")
def project_id():
    """Use vast_srv project ID; ensure project is registered in DB when tests run from repo root."""
    return VAST_SRV_PROJECT_ID


@pytest.fixture(scope="module")
def ensure_cwd():
    """Ensure tests run with repo root as cwd so config.json and data/ are found."""
    orig = os.getcwd()
    if Path(orig).resolve() != REPO_ROOT:
        os.chdir(REPO_ROOT)
    yield REPO_ROOT
    os.chdir(orig)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_analyze_complexity_structure_and_correctness(ensure_cwd, project_id):
    """analyze_complexity: success, results have correct structure and min_complexity filter."""
    from code_analysis.commands.analyze_complexity_mcp import (
        AnalyzeComplexityMCPCommand,
    )

    cmd = AnalyzeComplexityMCPCommand()
    # Single file to keep test fast; min_complexity=1 to get any results
    result = await cmd.execute(
        project_id=project_id,
        file_path="ai_admin/__main__.py",
        min_complexity=1,
    )
    assert isinstance(result, SuccessResult), getattr(result, "message", str(result))
    data = result.data
    assert "results" in data
    assert "total_count" in data
    assert "min_complexity" in data
    assert data["min_complexity"] == 1
    assert isinstance(data["results"], list)
    for item in data["results"]:
        assert "file_path" in item
        assert "function_name" in item
        assert "complexity" in item
        assert "line" in item
        assert "type" in item
        assert item["type"] in ("function", "method")
        assert item["complexity"] >= data["min_complexity"]
    # Must be sorted by complexity descending
    comps = [r["complexity"] for r in data["results"]]
    assert comps == sorted(comps, reverse=True)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_analyze_complexity_min_filter(ensure_cwd, project_id):
    """analyze_complexity: only returns items with complexity >= min_complexity."""
    from code_analysis.commands.analyze_complexity_mcp import (
        AnalyzeComplexityMCPCommand,
    )

    cmd = AnalyzeComplexityMCPCommand()
    result = await cmd.execute(
        project_id=project_id,
        file_path="ai_admin/__main__.py",
        min_complexity=100,
    )
    assert isinstance(result, SuccessResult)
    assert result.data["min_complexity"] == 100
    assert result.data["total_count"] == 0
    assert result.data["results"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_duplicates_structure_and_correctness(ensure_cwd, project_id):
    """find_duplicates: success, duplicate_groups have similarity and occurrences."""
    from code_analysis.commands.find_duplicates_mcp import FindDuplicatesMCPCommand

    cmd = FindDuplicatesMCPCommand()
    result = await cmd.execute(
        project_id=project_id,
        file_path="ai_admin/__main__.py",
        min_lines=2,
        min_similarity=0.5,
        use_semantic=False,
    )
    assert isinstance(result, SuccessResult), getattr(result, "message", str(result))
    data = result.data
    assert "duplicate_groups" in data
    assert "total_groups" in data
    assert "total_occurrences" in data
    assert "min_lines" in data
    assert "min_similarity" in data
    assert isinstance(data["duplicate_groups"], list)
    assert data["total_groups"] == len(data["duplicate_groups"])
    for group in data["duplicate_groups"]:
        assert "similarity" in group
        assert "occurrences" in group
        assert 0 <= group["similarity"] <= 1
        assert isinstance(group["occurrences"], list)
        for occ in group["occurrences"]:
            assert "file_path" in occ or "path" in str(occ)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_duplicates_with_semantic(ensure_cwd, project_id):
    """find_duplicates with use_semantic=True: success and valid structure (or fallback to AST)."""
    from code_analysis.commands.find_duplicates_mcp import FindDuplicatesMCPCommand

    cmd = FindDuplicatesMCPCommand()
    result = await cmd.execute(
        project_id=project_id,
        file_path="ai_admin/server.py",
        min_lines=4,
        min_similarity=0.6,
        use_semantic=True,
        semantic_threshold=0.75,
    )
    assert isinstance(result, SuccessResult), getattr(result, "message", str(result))
    data = result.data
    assert "duplicate_groups" in data
    assert "total_groups" in data
    assert "min_similarity" in data
    assert isinstance(data["duplicate_groups"], list)
    for group in data["duplicate_groups"]:
        assert "similarity" in group
        assert "occurrences" in group
        assert 0 <= group["similarity"] <= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_comprehensive_analysis_structure(ensure_cwd, project_id):
    """comprehensive_analysis: success, result has summary and expected list keys."""
    from code_analysis.commands.comprehensive_analysis_mcp import (
        ComprehensiveAnalysisMCPCommand,
    )

    cmd = ComprehensiveAnalysisMCPCommand()
    result = await cmd.execute(
        project_id=project_id,
        file_path="ai_admin/__main__.py",
        check_placeholders=True,
        check_stubs=True,
        check_duplicates=False,
        check_flake8=False,
        check_mypy=False,
    )
    if isinstance(result, ErrorResult):
        pytest.skip(
            f"comprehensive_analysis failed (e.g. DB client): {getattr(result, 'message', result)}"
        )
    assert isinstance(result, SuccessResult), getattr(result, "message", str(result))
    data = result.data
    assert "summary" in data
    assert "placeholders" in data
    assert "stubs" in data
    assert "empty_methods" in data
    assert "imports_not_at_top" in data
    assert "duplicates" in data
    assert "missing_docstrings" in data
    assert isinstance(data["summary"], dict)
    assert isinstance(data["placeholders"], list)
    assert isinstance(data["stubs"], list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_semantic_search_structure_and_scores(ensure_cwd, project_id):
    """semantic_search: if successful, results have score and valid range; allow no-index."""
    from code_analysis.commands.semantic_search_mcp import SemanticSearchMCPCommand

    cmd = SemanticSearchMCPCommand()
    result = await cmd.execute(
        project_id=project_id,
        query="configuration or settings",
        limit=5,
        min_score=0.2,
    )
    # May fail if FAISS index not built for project
    if isinstance(result, ErrorResult):
        pytest.skip(
            f"semantic_search not available: {getattr(result, 'message', result)}"
        )
    data = result.data
    assert "results" in data
    assert "query" in data
    assert "count" in data
    assert isinstance(data["results"], list)
    for hit in data["results"]:
        assert "score" in hit
        assert 0 <= hit["score"] <= 1
        assert "file_path" in hit or "chunk_uuid" in hit


@pytest.mark.integration
@pytest.mark.asyncio
async def test_semantic_search_limit_respected(ensure_cwd, project_id):
    """semantic_search: count <= limit when index exists."""
    from code_analysis.commands.semantic_search_mcp import SemanticSearchMCPCommand

    cmd = SemanticSearchMCPCommand()
    result = await cmd.execute(
        project_id=project_id,
        query="test",
        limit=2,
    )
    if isinstance(result, ErrorResult):
        pytest.skip(
            f"semantic_search not available: {getattr(result, 'message', result)}"
        )
    assert result.data["count"] <= 2
