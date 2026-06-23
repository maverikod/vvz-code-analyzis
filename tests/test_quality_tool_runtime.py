"""
Unit tests for the code-quality tool runtime (interpreter resolution + probe).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import subprocess
import sys

from code_analysis.core.code_quality import tool_runtime as tr


def test_tool_command_uses_server_interpreter():
    cmd = tr.tool_command("flake8", "--version")
    assert cmd[0] == sys.executable
    assert cmd[1:] == ["-m", "flake8", "--version"]


def test_module_missing_detection():
    assert tr.module_missing("/x/python: No module named flake8", "flake8") is True
    assert tr.module_missing("No module named 'mypy'", "mypy") is True
    assert tr.module_missing("some other error", "black") is False
    assert tr.module_missing("", "isort") is False


def _fake_proc(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_is_tool_available_true_and_cached(monkeypatch):
    tr.reset_availability_cache()
    calls = {"n": 0}

    def fake_run(tool, args, *, timeout=60):
        calls["n"] += 1
        return _fake_proc(returncode=0, stdout="black, 24.0")

    monkeypatch.setattr(tr, "run_quality_tool", fake_run)
    assert tr.is_tool_available("black") is True
    assert tr.is_tool_available("black") is True  # cached
    assert calls["n"] == 1


def test_is_tool_available_false_when_module_missing(monkeypatch):
    tr.reset_availability_cache()
    monkeypatch.setattr(
        tr,
        "run_quality_tool",
        lambda tool, args, *, timeout=60: _fake_proc(1, "", "No module named bandit"),
    )
    assert tr.is_tool_available("bandit") is False


def test_is_tool_available_false_on_oserror(monkeypatch):
    tr.reset_availability_cache()

    def boom(tool, args, *, timeout=60):
        raise OSError("nope")

    monkeypatch.setattr(tr, "run_quality_tool", boom)
    assert tr.is_tool_available("mypy") is False


def test_tool_version_parses_varied_banners(monkeypatch):
    tr.reset_availability_cache()
    banners = {
        "flake8": "7.3.0 (mccabe: 0.7.0) CPython 3.12",
        "mypy": "mypy 1.20.2 (compiled: yes)",
        "black": "python -m black, 25.12.0 (compiled: yes)",
        "isort": "\n      isort\n                    VERSION 6.1.0\n",
        "bandit": "__main__.py 1.9.4",
    }

    def fake_run(tool, args, *, timeout=60):
        return _fake_proc(returncode=0, stdout=banners[tool])

    monkeypatch.setattr(tr, "run_quality_tool", fake_run)
    assert tr.tool_version("flake8") == "7.3.0"
    assert tr.tool_version("mypy") == "1.20.2"
    assert tr.tool_version("black") == "25.12.0"
    assert tr.tool_version("isort") == "6.1.0"
    assert tr.tool_version("bandit") == "1.9.4"


def test_quality_tool_report_shape(monkeypatch):
    tr.reset_availability_cache()

    def fake_run(tool, args, *, timeout=60):
        if tool == "bandit":
            return _fake_proc(1, "", "No module named bandit")
        return _fake_proc(0, stdout=f"{tool} 1.2.3")

    monkeypatch.setattr(tr, "run_quality_tool", fake_run)
    report = tr.quality_tool_report()
    assert set(report) == set(tr.QUALITY_TOOL_MODULES)
    assert report["flake8"] == {"available": True, "version": "1.2.3"}
    assert report["bandit"] == {"available": False, "version": None}
