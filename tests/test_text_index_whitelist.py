"""
Tests for the non-Python text-index whitelist (bugs 688d2d01 / 13945588 /
597ea8c5 / a51769dc / fe1cf739).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest

from code_analysis.core.text_index_whitelist import (
    TEXT_INDEX_MAX_BYTES,
    is_text_index_eligible,
    looks_binary,
)


@pytest.mark.parametrize(
    "relative_path",
    [
        "pyproject.toml",
        "docker/build.sh",
        ".gitignore",
        "sub/.gitignore",
        "notes.md",
        "README.md",
        "config.yaml",
        "config.yml",
        "data.json",
        "setup.cfg",
        "tox.ini",
        "notes.txt",
    ],
)
def test_accepted_extensions(relative_path: str) -> None:
    """Every whitelisted extension/dotfile is eligible."""
    assert is_text_index_eligible(relative_path) is True


@pytest.mark.parametrize(
    "relative_path",
    [
        "module.py",
        "pkg/__init__.py",
        "image.png",
        "archive.tar.gz",
        "binary.so",
        "no_extension_not_gitignore",
        ".bashrc",  # extensionless dotfile, but not .gitignore
        ".env",
    ],
)
def test_rejected_extensions(relative_path: str) -> None:
    """Python sources and anything off the whitelist are rejected."""
    assert is_text_index_eligible(relative_path) is False


def test_gitignore_eligible_regardless_of_directory_depth() -> None:
    """.gitignore is eligible at any depth, matched by basename only."""
    assert is_text_index_eligible(".gitignore") is True
    assert is_text_index_eligible("a/b/c/.gitignore") is True


def test_extension_match_is_case_insensitive() -> None:
    """Suffix matching lowercases before comparing."""
    assert is_text_index_eligible("PYPROJECT.TOML") is True
    assert is_text_index_eligible("Script.SH") is True


def test_looks_binary_detects_nul_byte() -> None:
    """A NUL byte anywhere in the sample marks content as binary."""
    assert looks_binary(b"plain ascii text") is False
    assert looks_binary(b"") is False
    assert looks_binary(b"abc\x00def") is True


def test_max_bytes_is_one_mebibyte() -> None:
    """Size bound matches the documented 1 MiB rationale (see module docstring)."""
    assert TEXT_INDEX_MAX_BYTES == 1_048_576
