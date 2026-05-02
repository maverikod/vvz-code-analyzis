"""
Tests for read-only batch command whitelist and validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest

from code_analysis.commands.read_only_batch_whitelist import (
    ERROR_CODE_NOT_WHITELISTED,
    READ_ONLY_BATCH_WHITELIST,
    validate_command,
)


class TestReadOnlyBatchWhitelist:
    """Tests for READ_ONLY_BATCH_WHITELIST and validate_command."""

    def test_whitelist_immutable(self) -> None:
        """Whitelist is a frozenset and must not be extended."""
        assert isinstance(READ_ONLY_BATCH_WHITELIST, frozenset)
        assert len(READ_ONLY_BATCH_WHITELIST) >= 8

    def test_whitelisted_commands_pass(self) -> None:
        """All whitelisted commands validate successfully."""
        for cmd in READ_ONLY_BATCH_WHITELIST:
            ok, err = validate_command(cmd)
            assert ok is True, f"Expected {cmd!r} to be allowed"
            assert err is None

    def test_whitelisted_command_with_whitespace_pass(self) -> None:
        """Whitelisted command name with surrounding spaces passes."""
        ok, err = validate_command("  list_code_entities  ")
        assert ok is True
        assert err is None

    def test_mutating_commands_rejected(self) -> None:
        """Mutating commands must be rejected (negative test)."""
        mutating = (
            "cst_save_tree",
            "cst_modify_tree",
            "cst_apply_buffer",
            "cst_create_file",
            "format_code",
            "delete_file",
            "update_indexes",
        )
        for cmd in mutating:
            ok, payload = validate_command(cmd)
            assert ok is False, f"Mutating command {cmd!r} must be rejected"
            assert payload is not None
            assert payload.get("error_code") == ERROR_CODE_NOT_WHITELISTED
            assert payload.get("command") == cmd
            assert "error" in payload
            assert "message" in payload

    def test_unknown_command_rejected(self) -> None:
        """Unknown command name is rejected with explicit error payload."""
        ok, payload = validate_command("unknown_command_xyz")
        assert ok is False
        assert payload is not None
        assert payload["error_code"] == ERROR_CODE_NOT_WHITELISTED
        assert payload["command"] == "unknown_command_xyz"
        assert "whitelist" in payload["message"].lower()

    def test_empty_string_rejected(self) -> None:
        """Empty command name is rejected."""
        ok, payload = validate_command("")
        assert ok is False
        assert payload is not None
        assert payload["error_code"] == ERROR_CODE_NOT_WHITELISTED

    def test_blank_string_rejected(self) -> None:
        """Blank-only command name is rejected."""
        ok, payload = validate_command("   ")
        assert ok is False
        assert payload is not None
        assert payload["error_code"] == ERROR_CODE_NOT_WHITELISTED

    def test_none_rejected(self) -> None:
        """None as command name is rejected."""
        ok, payload = validate_command(None)  # type: ignore[arg-type]
        assert ok is False
        assert payload is not None
        assert payload["error_code"] == ERROR_CODE_NOT_WHITELISTED

    def test_error_payload_shape(self) -> None:
        """Error payload has required keys for deterministic rejection."""
        ok, payload = validate_command("cst_save_tree")
        assert ok is False
        assert payload is not None
        assert set(payload.keys()) == {"error", "error_code", "command", "message"}
