"""
Tests for AnalyzeFileCommand MCP wrapper (fast path).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

from code_analysis.commands.analyze_file_command import AnalyzeFileCommand


class TestAnalyzeFileCommandFast:
    """Regression tests: analyze_file should not require external chunker by default."""

    @pytest.mark.asyncio
    async def test_execute_fast_without_chunking(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default enable_chunking=False should return quickly and succeed."""

        # Ensure adapter config has no code_analysis chunker config in this test.
        monkeypatch.setattr(
            "code_analysis.commands.analyze_file_command.get_adapter_config",
            lambda: SimpleNamespace(config_data={}),
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data").mkdir(parents=True, exist_ok=True)
            sample = root / "a.py"
            sample.write_text(
                '"""x"""\n\ndef f() -> int:\n    return 1\n', encoding="utf-8"
            )

            cmd = AnalyzeFileCommand()
            result = await cmd.execute(root_dir=str(root), file_path=str(sample))

            # SuccessResult from adapter exposes to_dict(); but in tests we can
            # just validate it behaves like SuccessResult and contains payload.
            payload = result.to_dict()
            assert payload.get("success") is True
            data = payload.get("data") or {}
            assert data.get("success") is True
            assert data.get("file_path") == str(sample.resolve())
