"""
Tests for code_analysis.core.file_handlers.registry (config-driven routing).

Routing expectations are checked against ``list_handler_mappings()`` and helpers
exported from ``code_analysis.core.file_handlers.registry`` — extension tables
are not duplicated in this module.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

import pytest

from code_analysis.core.file_handlers.registry import (
    HANDLER_JSON,
    HANDLER_PYTHON,
    HANDLER_TEXT,
    HANDLER_YAML,
    OPERATIONS,
    RegistryError,
    get_handler_schema,
    list_handler_mappings,
    resolve_handler,
    validate_supported,
)


def _rows() -> List[Dict[str, str]]:
    """Single discovery path for parametrization (sorted for stable IDs)."""
    return sorted(list_handler_mappings(), key=lambda r: (r["handler_id"], r["suffix"]))


@pytest.mark.parametrize(
    "row",
    _rows(),
    ids=lambda r: f"{r['suffix']}->{r['handler_id']}",
)
def test_resolve_handler_matches_list_handler_mappings(row: Dict[str, str]) -> None:
    """Verify test resolve handler matches list handler mappings."""
    suffix, handler_id = row["suffix"], row["handler_id"]
    for op in sorted(OPERATIONS):
        assert resolve_handler(f"dir/file{suffix}", op) == handler_id
        assert resolve_handler(f"dir/FiLe{suffix.upper()}", op) == handler_id


def test_handler_suffix_groups_match_product_contract() -> None:
    """Public mapping groups match the supported text/json/yaml/python suffix sets.

    .toml/.sh/.cfg/.ini and the extensionless ".gitignore" dotfile were added
    to HANDLER_TEXT alongside bugs 688d2d01 / 13945588 / 597ea8c5 (AI Editor
    could not create or save these files at all -- "No handler for suffix").
    """
    groups: Dict[str, set[str]] = defaultdict(set)
    for r in list_handler_mappings():
        groups[r["handler_id"]].add(r["suffix"])
    by_id = {k: frozenset(v) for k, v in groups.items()}

    assert by_id[HANDLER_TEXT] == frozenset(
        {
            ".md",
            ".txt",
            ".rst",
            ".adoc",
            ".jsonl",
            ".ndjson",
            ".toml",
            ".sh",
            ".cfg",
            ".ini",
            ".gitignore",
        }
    )
    assert by_id[HANDLER_JSON] == frozenset({".json"})
    assert by_id[HANDLER_YAML] == frozenset({".yaml", ".yml"})
    assert by_id[HANDLER_PYTHON] == frozenset({".py", ".pyi", ".pyw"})


def test_unknown_suffix_fails_closed() -> None:
    """Verify test unknown suffix fails closed."""
    with pytest.raises(RegistryError) as exc:
        resolve_handler("file.unknown", "read")
    err = exc.value
    assert err.code == "UNSUPPORTED_FILE_EXTENSION"
    assert err.details["file_path"] == "file.unknown"
    assert err.details["suffix"] == ".unknown"


def test_pyproject_toml_resolves_to_text_handler() -> None:
    """Bug 688d2d01: pyproject.toml must route to the plain-text handler, not reject."""
    assert resolve_handler("pyproject.toml", "read") == HANDLER_TEXT
    assert resolve_handler("pyproject.toml", "save") == HANDLER_TEXT


def test_gitignore_extensionless_dotfile_resolves_to_text_handler() -> None:
    """Bug 597ea8c5: .gitignore (no pathlib suffix) must route to the text handler."""
    assert resolve_handler(".gitignore", "read") == HANDLER_TEXT
    assert resolve_handler("sub/.gitignore", "save") == HANDLER_TEXT


def test_missing_suffix_fails_before_handler_resolution() -> None:
    """A genuinely unrecognized extensionless path (not the .gitignore whitelist) still fails closed."""
    with pytest.raises(RegistryError) as exc:
        validate_supported("README", "read")
    assert exc.value.code == "UNSUPPORTED_FILE_EXTENSION"
    assert exc.value.details["suffix"] == ""


def test_unsupported_operation_error_details() -> None:
    """Verify test unsupported operation error details."""
    with pytest.raises(RegistryError) as exc:
        validate_supported("README.md", "patch")
    err = exc.value
    assert err.code == "UNSUPPORTED_FILE_OPERATION"
    assert err.details["file_path"] == "README.md"
    assert err.details["handler_id"] == ""


def test_get_handler_schema_text_read() -> None:
    """Verify test get handler schema text read."""
    schema = get_handler_schema(HANDLER_TEXT, "read")
    assert schema["type"] == "object"
    assert "properties" in schema


def test_unsupported_suffix_not_listed_in_discovery() -> None:
    """A genuinely unsupported suffix (not on the text/json/yaml/python whitelists) is absent."""
    known = {r["suffix"] for r in list_handler_mappings()}
    assert ".xml" not in known
