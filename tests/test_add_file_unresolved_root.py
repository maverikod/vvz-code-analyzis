"""
C-defensive: ``add_file`` must refuse to index against an unresolved project root
instead of silently collapsing ``Path("").resolve()`` to the server working
directory (/usr/lib/casmgr-server), which produced a flood of misleading
"not within project root" errors for the ``embed`` project.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from code_analysis.core.database_client.client_api_files import _ClientAPIFilesMixin


@pytest.mark.parametrize("bad_root", ["", None, "embed"])  # empty / missing / relative
def test_add_file_raises_on_unresolved_root(bad_root) -> None:
    fake = MagicMock()
    fake.get_project.return_value = SimpleNamespace(root_path=bad_root)
    with pytest.raises(ValueError, match="unresolved"):
        _ClientAPIFilesMixin.add_file(
            fake, "/some/abs/file.py", 1, 0.0, False, "proj-id"
        )


def test_add_file_passes_guard_for_absolute_root(tmp_path) -> None:
    """An absolute root_path passes the unresolved-root guard (no ValueError there)."""
    fake = MagicMock()
    fake.get_project.return_value = SimpleNamespace(root_path=str(tmp_path))
    # get_file_by_path returns None -> proceeds to insert path (mocked execute).
    fake.get_file_by_path.return_value = None
    fake.execute.return_value = {"affected_rows": 1, "data": None}
    # Should not raise the "unresolved" ValueError; any later behavior is mocked.
    try:
        _ClientAPIFilesMixin.add_file(
            fake, str(tmp_path / "pkg" / "f.py"), 1, 0.0, False, "proj-id"
        )
    except ValueError as exc:  # pragma: no cover - guard must not trip here
        assert "unresolved" not in str(exc)
