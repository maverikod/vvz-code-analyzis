"""
Atomic file replacement that keeps the target's permissions.

Bug 92e6d693: the CST write path stages new content in a
``tempfile.mkstemp`` file and then ``os.replace``s it over the target.
``os.replace`` is a rename: the target ends up with the SOURCE inode, and
therefore the SOURCE's permission bits. ``mkstemp`` always creates ``0600``,
so overwriting an already-indexed ``.py`` file silently stripped group and
other read access. The server owns the file, so nothing server-side noticed;
every other reader broke -- a sandbox import raised PermissionError, and a
build or a web server reading the same tree would fail the same way.

The same hazard exists wherever a staged file is renamed over a real one,
even when the staging file is created with a normal umask: a target that was
deliberately ``0755`` (an executable script) or ``0640`` silently becomes
whatever the staging file happened to be.

:func:`replace_preserving_mode` closes that: it copies the target's current
permission bits onto the staging file before the rename, so a save changes
content and nothing else.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)

# Applied only when the target does not exist yet, i.e. the staged file
# becomes a brand-new file. Matches what the create paths already produce on
# the deployed server (0644) rather than the 0600 a mkstemp file carries.
DEFAULT_NEW_FILE_MODE = 0o644


def replace_preserving_mode(
    source: Union[str, Path],
    target: Union[str, Path],
    *,
    default_mode: int = DEFAULT_NEW_FILE_MODE,
) -> None:
    """Rename ``source`` onto ``target``, keeping ``target``'s permission bits.

    Args:
        source: Staged file to move into place.
        target: Destination path; its current permissions win when it exists.
        default_mode: Permissions applied when ``target`` does not exist yet.

    Raises:
        OSError: If the rename itself fails. A failure to read or apply the
            permission bits is logged and does not block the replacement --
            losing the write would be worse than losing the mode.
    """
    source_path = Path(source)
    target_path = Path(target)

    desired_mode = default_mode
    try:
        desired_mode = stat.S_IMODE(target_path.stat().st_mode)
    except FileNotFoundError:
        pass
    except OSError as exc:  # noqa: BLE001 - never block the write on a stat
        logger.warning(
            "Could not read current mode of %s (%s); applying %o to the "
            "replacement instead",
            target_path,
            exc,
            desired_mode,
        )

    try:
        os.chmod(source_path, desired_mode)
    except OSError as exc:  # noqa: BLE001 - never block the write on a chmod
        logger.warning(
            "Could not set mode %o on %s (%s); the replacement may not keep "
            "the target's permissions",
            desired_mode,
            source_path,
            exc,
        )

    os.replace(str(source_path), str(target_path))
