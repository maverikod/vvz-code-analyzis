#!/usr/bin/env python3
"""
Synchronize dependency minimum versions from root pyproject.toml.

The canonical values live in ``[tool.code-analysis.dependency-versions]``.
This script mirrors them into packaging metadata, compatibility checks, and
operator-facing docs that need literal dependency specs.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DependencyVersions:
    """Dependency versions used by release metadata."""

    mcp_proxy_adapter: str
    queuemgr: str

    @classmethod
    def from_pyproject(cls, pyproject_path: Path) -> "DependencyVersions":
        """Load canonical dependency versions from pyproject.toml."""
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        try:
            versions = data["tool"]["code-analysis"]["dependency-versions"]
            return cls(
                mcp_proxy_adapter=str(versions["mcp-proxy-adapter"]),
                queuemgr=str(versions["queuemgr"]),
            )
        except KeyError as exc:
            raise RuntimeError(
                "pyproject.toml must define "
                "[tool.code-analysis.dependency-versions] with "
                "mcp-proxy-adapter and queuemgr"
            ) from exc


def _replace(pattern: str, replacement: str, text: str, path: Path) -> str:
    """Replace a required pattern exactly once or more."""
    updated, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count == 0:
        raise RuntimeError(f"Pattern not found in {path}: {pattern}")
    return updated


def _replace_optional(pattern: str, replacement: str, text: str) -> tuple[str, int]:
    """Replace a pattern when present and return the replacement count."""
    return re.subn(pattern, replacement, text, flags=re.MULTILINE)


def _write_if_changed(path: Path, text: str, check: bool) -> bool:
    """Write text unless check mode is active; return whether it changed."""
    old = path.read_text(encoding="utf-8")
    if old == text:
        return False
    if not check:
        path.write_text(text, encoding="utf-8")
    return True


def _sync_file(path: Path, versions: DependencyVersions, check: bool) -> bool:
    """Synchronize one known file."""
    text = path.read_text(encoding="utf-8")
    rel = path.as_posix()
    mpa_spec = f"mcp-proxy-adapter>={versions.mcp_proxy_adapter}"
    qm_spec = f"queuemgr>={versions.queuemgr}"

    if rel.endswith("pyproject.toml"):
        text = _replace(r'"mcp-proxy-adapter>=([^"]+)"', f'"{mpa_spec}"', text, path)
        if path.name == "pyproject.toml" and path.parent.name != "client":
            text = _replace(r'"queuemgr>=([^"]+)"', f'"{qm_spec}"', text, path)
    elif path.name == "requirements.txt":
        text = _replace(r"^mcp-proxy-adapter>=.+$", mpa_spec, text, path)
        text = _replace(r"^queuemgr>=.+$", qm_spec, text, path)
    elif path.name == "dependency_compat.py":
        text = _replace(
            r'^MIN_MCP_PROXY_ADAPTER_VERSION = "[^"]+"$',
            f'MIN_MCP_PROXY_ADAPTER_VERSION = "{versions.mcp_proxy_adapter}"',
            text,
            path,
        )
        text = _replace(
            r'^MIN_QUEUEMGR_VERSION = "[^"]+"$',
            f'MIN_QUEUEMGR_VERSION = "{versions.queuemgr}"',
            text,
            path,
        )
    else:
        count_total = 0
        text, count = _replace_optional(
            r"(`+mcp-proxy-adapter`+)\s*>=\s*[0-9][0-9A-Za-z.+-]*",
            rf"\1 >= {versions.mcp_proxy_adapter}",
            text,
        )
        count_total += count
        text, count = _replace_optional(
            r"mcp-proxy-adapter>=([0-9][0-9A-Za-z.+-]*)",
            mpa_spec,
            text,
        )
        count_total += count
        text, count = _replace_optional(
            r"mcp-proxy-adapter >= ([0-9][0-9A-Za-z.+-]*)",
            f"mcp-proxy-adapter >= {versions.mcp_proxy_adapter}",
            text,
        )
        count_total += count
        if count_total == 0:
            raise RuntimeError(f"No mcp-proxy-adapter version literal found in {path}")

    return _write_if_changed(path, text, check=check)


def target_files(root: Path) -> list[Path]:
    """Return files whose literal dependency versions are generated."""
    return [
        root / "pyproject.toml",
        root / "requirements.txt",
        root / "client" / "pyproject.toml",
        root / "code_analysis" / "core" / "dependency_compat.py",
        root / "code_analysis" / "commands" / "base_mcp_command.py",
        root / "code_analysis" / "main_server_presentation.py",
        root / "docs" / "AI_TOOL_USAGE_RULES.md",
        root / "docs" / "agents" / "project_overlay.md",
        root / "docs" / "METADATA_SCHEMA_STANDARD.md",
        root / "docs" / "standards" / "METADATA_SCHEMA_STANDARD.md",
    ]


def sync_dependency_versions(root: Path, check: bool = False) -> list[Path]:
    """Synchronize dependency versions and return changed files."""
    versions = DependencyVersions.from_pyproject(root / "pyproject.toml")
    changed: list[Path] = []
    for path in target_files(root):
        if _sync_file(path, versions, check=check):
            changed.append(path)
    return changed


def main() -> int:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated dependency versions are out of sync",
    )
    args = parser.parse_args()
    root = args.repo_root.resolve()
    changed = sync_dependency_versions(root, check=args.check)
    if args.check and changed:
        for path in changed:
            print(f"OUT OF SYNC: {path.relative_to(root)}", file=sys.stderr)
        return 1
    if changed:
        for path in changed:
            print(f"Updated: {path.relative_to(root)}")
    else:
        print("Dependency versions already synchronized.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
