"""Create the standard directory scaffold for new projects."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Standard directories created in every new project
STANDARD_DIRS: list[str] = [
    "tests",
    "docs/plans",
    "docs/standards",
    "logs",
]
# @node-id: eca5fb43-88a2-4cfe-8a7a-5db38884fd4a


@dataclass
class ScaffoldResult:
    """Result of directory scaffolding."""

    success: bool
    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    message: str = ""


# @node-id: b9852a52-77aa-414f-bbed-2e655057d90c


class DirScaffold:
    """Creates the standard directory layout inside a new project.

    Directories are created with parents; existing dirs are silently skipped.
    Each dir gets a `.gitkeep` so it is tracked by git.
    """

    # @node-id: 30d5fa47-bcbd-4402-aab2-3e0469b49ace

    def __init__(self, project_root: Path, extra_dirs: list[str] | None = None) -> None:
        """Initialise DirScaffold.

        Args:
            project_root: Absolute path to the project root directory.
            extra_dirs: Additional relative paths to create beyond defaults.
        """
        self.project_root = Path(project_root)
        self.dirs = list(STANDARD_DIRS) + (extra_dirs or [])

    # @node-id: bec07744-40e3-4802-9366-59237ae5b0ea

    def scaffold(self) -> ScaffoldResult:
        """Create all configured directories.

        Returns:
            ScaffoldResult with lists of created / skipped / errored paths.
        """
        created: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        for rel_dir in self.dirs:
            target = self.project_root / rel_dir
            try:
                if target.exists():
                    skipped.append(rel_dir)
                    logger.debug("Directory already exists, skipping: %s", target)
                    continue
                target.mkdir(parents=True, exist_ok=True)
                # Place a .gitkeep so the empty dir is tracked
                gitkeep = target / ".gitkeep"
                if not gitkeep.exists():
                    gitkeep.touch()
                created.append(rel_dir)
                logger.info("Created directory: %s", target)
            except Exception as exc:
                msg = f"Failed to create {rel_dir}: {exc}"
                errors.append(msg)
                logger.error(msg)

        success = len(errors) == 0
        parts = []
        if created:
            parts.append(f"created {len(created)} dirs")
        if skipped:
            parts.append(f"skipped {len(skipped)} existing")
        if errors:
            parts.append(f"{len(errors)} errors")
        message = "; ".join(parts) if parts else "nothing to do"

        return ScaffoldResult(
            success=success,
            created=created,
            skipped=skipped,
            errors=errors,
            message=message,
        )
