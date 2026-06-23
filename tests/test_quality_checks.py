"""
Unit tests for black/isort/bandit drift & security check helpers.

Tool execution is monkeypatched so these don't depend on installed binaries.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import subprocess
from pathlib import Path

from code_analysis.core.code_quality import drift_checks, security


def _proc(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_black_clean(monkeypatch):
    monkeypatch.setattr(drift_checks, "run_quality_tool", lambda *a, **k: _proc(0))
    ok, msg, errs = drift_checks.check_with_black(Path("x.py"))
    assert ok is True and errs == []


def test_black_would_reformat(monkeypatch):
    monkeypatch.setattr(
        drift_checks,
        "run_quality_tool",
        lambda *a, **k: _proc(1, stdout="--- a\n+++ b\n", stderr="would reformat x.py"),
    )
    ok, msg, errs = drift_checks.check_with_black(Path("x.py"))
    assert ok is False
    assert any("would reformat" in e for e in errs)


def test_black_not_installed(monkeypatch):
    monkeypatch.setattr(
        drift_checks,
        "run_quality_tool",
        lambda *a, **k: _proc(1, "", "No module named black"),
    )
    ok, msg, errs = drift_checks.check_with_black(Path("x.py"))
    assert ok is False and msg == "Black not installed"


def test_isort_drift(monkeypatch):
    monkeypatch.setattr(
        drift_checks,
        "run_quality_tool",
        lambda *a, **k: _proc(1, stdout="diff", stderr="ERROR: x.py Imports are incorrectly sorted."),
    )
    ok, msg, errs = drift_checks.check_with_isort(Path("x.py"))
    assert ok is False and errs


def test_bandit_no_findings(monkeypatch):
    payload = json.dumps({"results": []})
    monkeypatch.setattr(security, "run_quality_tool", lambda *a, **k: _proc(0, stdout=payload))
    ok, msg, errs = security.check_with_bandit(Path("x.py"))
    assert ok is True and errs == []


def test_bandit_findings(monkeypatch):
    payload = json.dumps(
        {
            "results": [
                {
                    "line_number": 10,
                    "test_id": "B602",
                    "issue_severity": "HIGH",
                    "issue_confidence": "HIGH",
                    "issue_text": "subprocess with shell=True",
                }
            ]
        }
    )
    monkeypatch.setattr(security, "run_quality_tool", lambda *a, **k: _proc(1, stdout=payload))
    ok, msg, errs = security.check_with_bandit(Path("x.py"))
    assert ok is False
    assert "B602" in errs[0] and "HIGH" in errs[0]


def test_bandit_not_installed(monkeypatch):
    monkeypatch.setattr(
        security, "run_quality_tool", lambda *a, **k: _proc(1, "", "No module named bandit")
    )
    ok, msg, errs = security.check_with_bandit(Path("x.py"))
    assert ok is False and msg == "Bandit not installed"


def test_bandit_bad_json(monkeypatch):
    monkeypatch.setattr(
        security, "run_quality_tool", lambda *a, **k: _proc(2, "not json", "boom")
    )
    ok, msg, errs = security.check_with_bandit(Path("x.py"))
    assert ok is False
