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
