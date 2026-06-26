"""
Unit tests for the comprehensive_analysis hard-fail contract (A-HARDFAIL, R3).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.commands.comprehensive_analysis_mcp import quality_tools as qt
from code_analysis.commands.comprehensive_analysis_mcp.batch_summary import (
    quality_findings_counts,
)


def test_requested_missing_tool_fails(monkeypatch):
    # bandit unavailable; everything else available
    """Verify test requested missing tool fails."""
    monkeypatch.setattr(qt, "is_tool_available", lambda tool: tool != "bandit")
    err = qt.probe_required_tools(
        {"check_flake8": True, "check_bandit": True, "check_black": False}
    )
    assert err is not None
    assert err.code == qt.QUALITY_TOOL_UNAVAILABLE
    assert err.details == {"tool": "bandit", "requested_check": "check_bandit"}


def test_not_requested_missing_tool_is_ignored(monkeypatch):
    # bandit unavailable but NOT requested → no error
    """Verify test not requested missing tool is ignored."""
    monkeypatch.setattr(qt, "is_tool_available", lambda tool: tool != "bandit")
    err = qt.probe_required_tools({"check_flake8": True, "check_bandit": False})
    assert err is None


def test_all_available_passes(monkeypatch):
    """Verify test all available passes."""
    monkeypatch.setattr(qt, "is_tool_available", lambda tool: True)
    err = qt.probe_required_tools(
        {"check_flake8": True, "check_mypy": True, "check_black": True}
    )
    assert err is None


def test_quality_findings_counts():
    """Verify test quality findings counts."""
    results = {
        "black_findings": [{"error_count": 3}, {"error_count": 1}],
        "isort_findings": [],
        "bandit_findings": [{"error_count": 2}],
    }
    counts = quality_findings_counts(results)
    assert counts["total_black_findings"] == 4
    assert counts["files_with_black_findings"] == 2
    assert counts["total_isort_findings"] == 0
    assert counts["files_with_isort_findings"] == 0
    assert counts["total_bandit_findings"] == 2
    assert counts["files_with_bandit_findings"] == 1
