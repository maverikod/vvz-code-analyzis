"""Tests for registration.instance_uuid install-time fix."""

from __future__ import annotations

from pathlib import Path

import pytest

from code_analysis.core.config_instance_uuid import (
    ensure_instance_uuid_in_config,
    needs_instance_uuid_fix,
    registration_instance_uuid_value,
    replace_instance_uuid_in_text,
)
from code_analysis.core.config_validator.helpers import is_valid_uuid4


def test_needs_fix_for_placeholder_and_invalid() -> None:
    assert needs_instance_uuid_fix(
        {"registration": {"instance_uuid": "REPLACE_ON_INSTALL"}}
    )
    assert needs_instance_uuid_fix({"registration": {"instance_uuid": "not-a-uuid"}})
    assert needs_instance_uuid_fix({"registration": {}})
    assert not needs_instance_uuid_fix(
        {"registration": {"instance_uuid": "550e8400-e29b-41d4-a716-446655440000"}}
    )


def test_replace_preserves_comments() -> None:
    text = (
        "{\n"
        "  # server identity\n"
        '  "registration": {\n'
        '    "instance_uuid": "REPLACE_ON_INSTALL"\n'
        "  }\n"
        "}\n"
    )
    new_text, replaced = replace_instance_uuid_in_text(
        text, "550e8400-e29b-41d4-a716-446655440000"
    )
    assert replaced
    assert "# server identity" in new_text
    assert "REPLACE_ON_INSTALL" not in new_text
    assert "550e8400-e29b-41d4-a716-446655440000" in new_text


def test_ensure_instance_uuid_in_config(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        "{\n"
        '  "registration": {\n'
        '    "instance_uuid": "REPLACE_ON_INSTALL"\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    new_uuid = ensure_instance_uuid_in_config(config)
    assert new_uuid is not None
    assert is_valid_uuid4(new_uuid)
    saved = config.read_text(encoding="utf-8")
    assert new_uuid in saved
    assert ensure_instance_uuid_in_config(config) is None


def test_ensure_instance_uuid_dry_run(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        '{"registration": {"instance_uuid": "bad"}}\n',
        encoding="utf-8",
    )
    new_uuid = ensure_instance_uuid_in_config(config, dry_run=True)
    assert new_uuid is not None
    assert is_valid_uuid4(new_uuid)
    assert (
        config.read_text(encoding="utf-8")
        == '{"registration": {"instance_uuid": "bad"}}\n'
    )


def test_registration_instance_uuid_value_nested() -> None:
    assert registration_instance_uuid_value({}) == ""
    assert registration_instance_uuid_value({"registration": "x"}) == ""
    assert (
        registration_instance_uuid_value({"registration": {"instance_uuid": "  abc  "}})
        == "abc"
    )


@pytest.mark.parametrize(
    "invalid",
    [
        "",
        "REPLACE_ON_INSTALL",
        "00000000-0000-0000-0000-000000000000",
        "550e8400-e29b-41d4-a716-446655440000-extra",
    ],
)
def test_invalid_uuid4_values(invalid: str) -> None:
    assert needs_instance_uuid_fix({"registration": {"instance_uuid": invalid}})


def test_valid_uuid4_not_replaced(tmp_path: Path) -> None:
    valid = "550e8400-e29b-41d4-a716-446655440000"
    config = tmp_path / "config.json"
    config.write_text(
        f'{{"registration": {{"instance_uuid": "{valid}"}}}}\n',
        encoding="utf-8",
    )
    assert ensure_instance_uuid_in_config(config) is None
    assert valid in config.read_text(encoding="utf-8")
