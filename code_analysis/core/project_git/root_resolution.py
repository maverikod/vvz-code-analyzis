"""
Git-block-facing project root resolution.

Single entry point every project-scoped git operation and the commit-on-write
behaviour use to resolve a registered project's repository root. Delegates to
code_analysis.core.project_root_path.resolve_project_root_absolute_str and
converts its ambiguous empty-string "could not resolve" result into a
distinct, explicit refusal outcome instead of acting on a guessed location.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from code_analysis.core.project_root_path import resolve_project_root_absolute_str

PROJECT_ROOT_RESOLUTION_REFUSED = "PROJECT_ROOT_RESOLUTION_REFUSED"


@dataclass(frozen=True)
class ProjectRootResolutionResult:
    """Outcome of resolving a project's repository root for the git block.

    Attributes:
        resolved_root: The absolute repository root path when resolution
            succeeded, else None.
        refused: True when resolution was refused because the underlying
            result was empty or ambiguous; False when resolved_root holds
            a valid root.
        reason: The refusal reason code when refused is True, else None.
    """

    resolved_root: Optional[str]
    refused: bool
    reason: Optional[str]


def resolve_git_project_root(
    *,
    watch_dir_id: Optional[str],
    project_id: Optional[str],
    root_path_stored: Optional[str] = None,
    project_name: Optional[str] = None,
    legacy_absolute_root: Optional[str] = None,
    database: Any,
    require_exists: bool = True,
) -> ProjectRootResolutionResult:
    """Resolve a registered project's repository root for the git block.

    The root is derived from the pair (watch_dir_id, project_id): the
    project's folder beneath the watched directory's absolute path. A bare
    absolute path supplied via root_path_stored or legacy_absolute_root is
    honoured only as a legacy form. When resolution yields an empty or
    ambiguous result, this function refuses rather than acting on a guessed
    location. The same resolved root must be used by every git operation
    and by any commit produced on write.

    :param watch_dir_id: Identifier of the watched directory whose absolute
        path anchors resolution.
    :param project_id: Identifier of the registered project whose folder
        under the watched directory is the repository root.
    :param root_path_stored: The project's stored root_path value: a
        watch-relative folder segment, or a legacy absolute path.
    :param project_name: The project's name, used as a fallback folder-name
        candidate when root_path_stored does not resolve directly.
    :param legacy_absolute_root: An optional bare absolute path accepted
        only as a legacy form when no watch-relative segment is available.
    :param database: The database handle forwarded to
        resolve_project_root_absolute_str for watch-directory and project
        lookups.
    :param require_exists: When True, both the watch directory and the
        resolved project root must exist on disk on this server instance.
    :return: A ProjectRootResolutionResult. On success, resolved_root holds
        the absolute path and refused is False. On empty or ambiguous
        resolution, resolved_root is None, refused is True, and reason is
        PROJECT_ROOT_RESOLUTION_REFUSED.
    """
    stored = (root_path_stored or "").strip()
    legacy = (legacy_absolute_root or "").strip()
    effective_stored: Optional[str] = stored or legacy or None

    resolved = resolve_project_root_absolute_str(
        project_id=project_id,
        root_path_stored=effective_stored,
        watch_dir_id=watch_dir_id,
        project_name=project_name,
        database=database,
        require_exists=require_exists,
    )
    resolved = (resolved or "").strip()

    if not resolved:
        return ProjectRootResolutionResult(
            resolved_root=None,
            refused=True,
            reason=PROJECT_ROOT_RESOLUTION_REFUSED,
        )

    return ProjectRootResolutionResult(
        resolved_root=resolved,
        refused=False,
        reason=None,
    )
