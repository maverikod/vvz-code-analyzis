"""
Project-scoped git capability package boundary.

This package implements the project-scoped git capability block: commands
that operate on the filesystem working tree of a registered project via
subprocess git. It is parallel to and independent of the pre-existing
edit-session git facility (commands named session_git_status,
session_git_log, session_git_diff, session_git_show, session_git_revert),
which instead operates on a temporary per-edit-session repository
identified by an edit session. The two facilities are independent: this
package neither replaces nor alters the edit-session git facility, and the
edit-session git facility is untouched by anything in this package.

This module intentionally exports nothing yet: the concrete command modules
of this package are authored by other tactical steps of the git-spec plan
and are added to __all__ when they land.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

__all__: list = []
