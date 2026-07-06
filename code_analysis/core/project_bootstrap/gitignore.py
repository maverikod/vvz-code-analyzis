"""Create and maintain the default project .gitignore."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_GITIGNORE_LINES: tuple[str, ...] = (
    "# Python",
    "__pycache__/",
    "*.py[cod]",
    "*$py.class",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".coverage",
    ".coverage.*",
    "htmlcov/",
    "",
    "# Virtual environments",
    ".venv/",
    "venv/",
    "env/",
    "",
    "# Build and packaging",
    "build/",
    "dist/",
    "*.egg-info/",
    "",
    "# Editor and OS files",
    ".idea/",
    ".vscode/",
    ".DS_Store",
    "",
    "# Logs and local configuration",
    "logs/",
    "*.log",
    ".env",
    ".env.*",
    "",
    "# code_analysis service artifacts",
    "old_code/",
    "backups/",
    "versions/",
    "trash/",
    "*.tree",
    "*.tree.*",
    ".cst/",
    ".trees/",
    "",
)


@dataclass
class GitignoreResult:
    """Result of ensuring the project .gitignore exists."""

    success: bool
    path: str
    created: bool = False
    appended: list[str] = field(default_factory=list)
    skipped: bool = False
    errors: list[str] = field(default_factory=list)


class GitignoreBootstrap:
    """Ensure a project has the default .gitignore entries."""

    def __init__(self, project_root: Path) -> None:
        """Initialise bootstrap for a project root."""
        self.project_root = Path(project_root)
        self.path = self.project_root / ".gitignore"

    def ensure(self) -> GitignoreResult:
        """Create .gitignore or append missing default entries."""
        try:
            self.project_root.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                self.path.write_text(
                    "\n".join(DEFAULT_GITIGNORE_LINES).rstrip() + "\n",
                    encoding="utf-8",
                )
                return GitignoreResult(
                    success=True,
                    path=str(self.path),
                    created=True,
                )

            original = self.path.read_text(encoding="utf-8", errors="replace")
            existing = set(original.splitlines())
            missing = [
                line
                for line in DEFAULT_GITIGNORE_LINES
                if line and line not in existing
            ]
            if not missing:
                return GitignoreResult(
                    success=True,
                    path=str(self.path),
                    skipped=True,
                )

            prefix = "" if original.endswith("\n") else "\n"
            addition = "\n# code_analysis default ignores\n" + "\n".join(missing) + "\n"
            self.path.write_text(original + prefix + addition, encoding="utf-8")
            return GitignoreResult(
                success=True,
                path=str(self.path),
                appended=missing,
            )
        except Exception as exc:
            return GitignoreResult(
                success=False,
                path=str(self.path),
                errors=[str(exc)],
            )
