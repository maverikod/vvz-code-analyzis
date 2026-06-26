"""Unit tests for PreviewReference builder and serialization."""

from __future__ import annotations

import json

import pytest

from code_analysis.core.search_session.preview_reference import (
    PreviewReference,
    build_preview_reference,
    preview_reference_to_dict,
)


def test_build_preview_reference_with_stable_node_id() -> None:
    """Verify test build preview reference with stable node id."""
    ref = build_preview_reference(
        file_path="src/app.py",
        node_id="550e8400-e29b-41d4-a716-446655440000",
        stable_id_verified=True,
    )
    assert ref.file_path == "src/app.py"
    assert ref.node_id == "550e8400-e29b-41d4-a716-446655440000"
    assert ref.selector is None
    assert ref.draft_session_id is None


def test_build_preview_reference_with_selector_only() -> None:
    """Verify test build preview reference with selector only."""
    ref = build_preview_reference(
        file_path="data/config.json",
        node_id=None,
        selector="$.features[0].name",
        stable_id_verified=False,
    )
    assert ref.selector == "$.features[0].name"
    assert ref.node_id is None


def test_build_preview_reference_rejects_unstable_node_id() -> None:
    """Verify test build preview reference rejects unstable node id."""
    with pytest.raises(ValueError, match="UNSTABLE_NODE_ID"):
        build_preview_reference(
            file_path="src/app.py",
            node_id="ephemeral-node-1",
            stable_id_verified=False,
        )


def test_build_preview_reference_requires_node_id_or_selector() -> None:
    """Verify test build preview reference requires node id or selector."""
    with pytest.raises(ValueError, match="node_id or selector"):
        build_preview_reference(
            file_path="src/app.py",
            node_id=None,
            selector=None,
            stable_id_verified=True,
        )


def test_preview_reference_to_dict_serializes_stable_ref() -> None:
    """Verify test preview reference to dict serializes stable ref."""
    ref = PreviewReference(
        file_path="docs/readme.md",
        node_id="6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        selector=None,
        draft_session_id="draft-session-42",
    )
    payload = preview_reference_to_dict(ref)
    assert payload == {
        "file_path": "docs/readme.md",
        "node_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        "draft_session_id": "draft-session-42",
    }
    json.dumps(payload)


def test_preview_reference_to_dict_omits_null_fields() -> None:
    """Verify test preview reference to dict omits null fields."""
    ref = build_preview_reference(
        file_path="cfg/settings.yaml",
        node_id=None,
        selector="root.items[2]",
        stable_id_verified=True,
    )
    payload = preview_reference_to_dict(ref)
    assert "node_id" not in payload
    assert "draft_session_id" not in payload
    assert payload["selector"] == "root.items[2]"
