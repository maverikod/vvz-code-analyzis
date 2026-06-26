"""
MCP command exposing the installed casmgr-server Info manual.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
import gzip
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .command_metadata_helpers import (
    build_command_metadata,
    parameters_from_schema,
)

INFO_NODES = [
    "Top",
    "Overview",
    "Release build",
    "Installation",
    "Config generator",
    "Config reference",
    "Secrets",
    "mTLS",
    "Admin commands",
    "PostgreSQL container",
    "Ports and co-existence with dev",
    "Systemd",
    "Environment",
    "Upgrade and removal",
    "Troubleshooting",
]

INFO_PATH_CANDIDATES = [
    Path("/usr/share/info/casmgr-server.info"),
    Path("/usr/share/info/casmgr-server.info.gz"),
    Path("/usr/local/share/info/casmgr-server.info"),
    Path("/usr/local/share/info/casmgr-server.info.gz"),
    Path("/usr/lib/casmgr-server/packaging/info/casmgr-server.info"),
    Path.cwd() / "packaging" / "info" / "casmgr-server.info",
]

TEXI_PATH_CANDIDATES = [
    Path("/usr/share/doc/casmgr-server/casmgr-server.texi"),
    Path.cwd() / "packaging" / "info" / "casmgr-server.texi",
]

DOCKER_IMAGE_PATH_CANDIDATES = [
    Path("/usr/share/casmgr/docker-image"),
    Path("/var/casmgr/docker-image"),
    Path.cwd() / "debian" / "casmgr-docker-image",
]


def _first_existing_path(candidates: List[Path]) -> Optional[Path]:
    """Return the first readable file from a candidate list."""
    for path in candidates:
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def _read_text_file(path: Path) -> str:
    """Read UTF-8 text with replacement for any invalid bytes."""
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    return path.read_text(encoding="utf-8", errors="replace")


def _path_metadata(path: Optional[Path]) -> Dict[str, Any]:
    """Return path, mtime, and size metadata for a file when available."""
    if path is None:
        return {"path": None, "mtime": None, "size_bytes": None}
    try:
        stat = path.stat()
    except OSError:
        return {"path": str(path), "mtime": None, "size_bytes": None}
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    return {"path": str(path), "mtime": mtime, "size_bytes": stat.st_size}


def _safe_distribution_version(name: str) -> str:
    """Return installed Python distribution version or ``unknown``."""
    try:
        return metadata.version(name)
    except Exception:
        return "unknown"


def _read_first_line(candidates: List[Path]) -> Optional[str]:
    """Read the first non-empty line from the first existing candidate file."""
    path = _first_existing_path(candidates)
    if path is None:
        return None
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            text = line.strip()
            if text:
                return text
    except OSError:
        return None
    return None


def _strip_info_control_lines(text: str) -> str:
    """Remove generated Info navigation/control noise from node content."""
    lines: List[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("\x1f"):
            continue
        if line.startswith("File: ") and " Node: " in line:
            continue
        if line.strip() == "\x1f":
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _parse_info_nodes(text: str) -> Dict[str, str]:
    """Parse generated Info file text into a mapping of node name to content."""
    matches = list(re.finditer(r"^File: .+?,\s+Node:\s+([^,\n]+).*?$", text, re.M))
    nodes: Dict[str, str] = {}
    for idx, match in enumerate(matches):
        node = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        content = _strip_info_control_lines(text[start:end])
        if content:
            nodes[node] = content
    return nodes


def _clean_texi(text: str) -> str:
    """Convert a small Texinfo subset into readable plain text."""
    replacements = {
        "@code{": "`",
        "@file{": "`",
        "@strong{": "",
        "@ref{": "",
    }
    cleaned = text
    for src, dst in replacements.items():
        cleaned = cleaned.replace(src, dst)
    cleaned = cleaned.replace("}", "`")
    cleaned = re.sub(r"^@(?:chapter|section|heading)\s+", "", cleaned, flags=re.M)
    cleaned = re.sub(
        r"^@(?:node|menu|end menu|itemize|enumerate|table).*?$", "", cleaned, flags=re.M
    )
    cleaned = re.sub(
        r"^@(?:end itemize|end enumerate|end table|bye).*?$", "", cleaned, flags=re.M
    )
    cleaned = re.sub(r"^@item\s+", "- ", cleaned, flags=re.M)
    cleaned = cleaned.replace("@example", "```").replace("@end example", "```")
    cleaned = cleaned.replace("@verbatim", "```").replace("@end verbatim", "```")
    return "\n".join(line.rstrip() for line in cleaned.splitlines()).strip()


def _parse_texi_nodes(text: str) -> Dict[str, str]:
    """Parse source Texinfo into a mapping of node name to approximate plain text."""
    matches = list(re.finditer(r"^@node\s+(.+?)(?:,\s*.*)?$", text, re.M))
    nodes: Dict[str, str] = {}
    for idx, match in enumerate(matches):
        node = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        content = _clean_texi(text[start:end])
        if content:
            nodes[node] = content
    return nodes


def _load_manual_nodes() -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Load manual nodes from installed Info file, falling back to source Texinfo."""
    info_path = _first_existing_path(INFO_PATH_CANDIDATES)
    if info_path is not None:
        text = _read_text_file(info_path)
        nodes = _parse_info_nodes(text)
        if nodes:
            return nodes, {"format": "info", **_path_metadata(info_path)}

    texi_path = _first_existing_path(TEXI_PATH_CANDIDATES)
    if texi_path is not None:
        text = _read_text_file(texi_path)
        nodes = _parse_texi_nodes(text)
        if nodes:
            return nodes, {"format": "texinfo", **_path_metadata(texi_path)}

    return {}, {"format": None, "path": None, "mtime": None, "size_bytes": None}


def _resolve_node(nodes: Dict[str, str], node: Optional[str]) -> Optional[str]:
    """Resolve a requested node by exact or case-insensitive name."""
    if not node:
        return None
    if node in nodes:
        return node
    needle = node.strip().casefold()
    for candidate in nodes:
        if candidate.casefold() == needle:
            return candidate
    return None


def _search_nodes(nodes: Dict[str, str], section: str) -> List[str]:
    """Return node names whose title or content matches a section query."""
    needle = section.strip().casefold()
    if not needle:
        return []
    return [
        name
        for name, content in nodes.items()
        if needle in name.casefold() or needle in content.casefold()
    ]


def _truncate(text: str, max_chars: int) -> Tuple[str, bool]:
    """Return text clipped to max_chars and whether clipping happened."""
    if len(text) <= max_chars:
        return text, False
    return text[: max(0, max_chars)].rstrip() + "\n\n[truncated]", True


def _runtime_package_info(source: Dict[str, Any]) -> Dict[str, Any]:
    """Collect runtime package metadata displayed with every info response."""
    return {
        "package": "casmgr-server",
        "python_distribution": "code-analysis",
        "version": _safe_distribution_version("code-analysis"),
        "docker_image": _read_first_line(DOCKER_IMAGE_PATH_CANDIDATES),
        "manual": source,
    }


def _error_result(
    *,
    message: str,
    code: str,
    details: Optional[Dict[str, Any]] = None,
) -> ErrorResult:
    """Build ErrorResult while preserving project string error-code convention."""
    return ErrorResult(message=message, code=cast(Any, code), details=details)


class InfoCommand(Command):
    """Expose casmgr-server deployment manual sections from the installed Info file."""

    name = "info"
    version = "1.0.0"
    descr = "Show casmgr-server package information and deployment manual sections"
    category = "system"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return JSON schema for info command parameters."""
        return {
            "type": "object",
            "description": (
                "Read the installed casmgr-server Info manual. Data is loaded at "
                "runtime from /usr/share/info/casmgr-server.info when available."
            ),
            "properties": {
                "node": {
                    "type": "string",
                    "description": (
                        "Optional Info node/chapter name to return. Use format='nodes' "
                        "to list available values."
                    ),
                    "enum": INFO_NODES,
                },
                "section": {
                    "type": "string",
                    "description": (
                        "Optional case-insensitive search string. Returns matching nodes."
                    ),
                },
                "format": {
                    "type": "string",
                    "description": (
                        "Output mode: summary, one node/content result, or node list."
                    ),
                    "enum": ["summary", "text", "nodes"],
                    "default": "summary",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters of manual text to return.",
                    "default": 20000,
                    "minimum": 1000,
                    "maximum": 100000,
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: type["InfoCommand"]) -> Dict[str, Any]:
        """Return detailed command metadata for help."""
        return cast(
            Dict[str, Any],
            build_command_metadata(
                cls,
                detailed_description=(
                    "The info command exposes the same deployment and operations manual "
                    "installed by the Debian package as `info casmgr-server`. It reads "
                    "`/usr/share/info/casmgr-server.info` at execution time, so package "
                    "upgrades immediately update command output. The response also includes "
                    "the runtime Python package version, pinned PostgreSQL Docker image, "
                    "manual source path, file mtime, and available Info nodes. Use this "
                    "command to inspect installation, config, secrets, mTLS, admin commands, "
                    "systemd, upgrade/removal, and troubleshooting guidance through MCP."
                ),
                parameters=parameters_from_schema(cls.get_schema()),
                usage_examples=[
                    {
                        "description": "Show package and manual overview",
                        "command": {},
                        "explanation": "Returns package metadata, available nodes, and overview text.",
                    },
                    {
                        "description": "List available Info nodes",
                        "command": {"format": "nodes"},
                        "explanation": "Use one of these values as node.",
                    },
                    {
                        "description": "Read installation guidance",
                        "command": {"node": "Installation", "format": "text"},
                        "explanation": "Returns the Installation node from the installed Info manual.",
                    },
                    {
                        "description": "Search troubleshooting topics",
                        "command": {"section": "PostgreSQL", "max_chars": 12000},
                        "explanation": "Returns nodes whose title or content mention PostgreSQL.",
                    },
                ],
                error_cases={
                    "INFO_NOT_FOUND": {
                        "description": "No installed Info manual or source fallback was found.",
                        "solution": "Reinstall or reconfigure the casmgr-server Debian package.",
                    },
                    "INFO_NODE_NOT_FOUND": {
                        "description": "Requested node does not exist in the manual.",
                        "solution": "Call info with format='nodes' and retry with a listed node.",
                    },
                    "VALIDATION_ERROR": {
                        "description": "Invalid parameter type, enum value, or max_chars range.",
                        "solution": "Use get_schema/help and retry with valid parameters.",
                    },
                },
                return_value={
                    "success": {
                        "description": "Manual information was loaded.",
                        "data": {
                            "package": "Runtime package version, Docker image, and manual source metadata.",
                            "nodes": "Available Info nodes.",
                            "items": "Selected manual node contents.",
                            "truncated": "True when text was clipped by max_chars.",
                        },
                        "example": {
                            "package": {
                                "package": "casmgr-server",
                                "version": "1.6.6",
                                "docker_image": "vasilyvz/casmgr-postgres:1.6.6",
                            },
                            "nodes": ["Top", "Overview", "Installation"],
                            "items": [{"node": "Installation", "text": "..."}],
                        },
                    },
                    "error": {
                        "description": "Command failed.",
                        "code": "INFO_NOT_FOUND | INFO_NODE_NOT_FOUND | VALIDATION_ERROR",
                        "message": "Human-readable error message.",
                    },
                },
                best_practices=[
                    "Use format='nodes' first when you need an exact chapter name.",
                    "Use node='Troubleshooting' for operational failures after deploy.",
                    "Check package.manual.mtime to confirm the command is reading the installed manual.",
                    "Use health after info when validating a live server deployment.",
                ],
            ),
        )

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate schema and command-specific constraints."""
        params = super().validate_params(params)
        max_chars = int(params.get("max_chars", 20000) or 20000)
        if max_chars < 1000 or max_chars > 100000:
            raise ValueError("max_chars must be between 1000 and 100000")
        if params.get("node") and params.get("section"):
            raise ValueError("Use either node or section, not both")
        return params

    async def execute(self, **kwargs: Any) -> SuccessResult | ErrorResult:
        """Return package/manual information from installed casmgr Info docs."""
        params: Dict[str, Any] = {
            "node": kwargs.pop("node", None),
            "section": kwargs.pop("section", None),
            "format": kwargs.pop("format", "summary"),
            "max_chars": kwargs.pop("max_chars", 20000),
        }
        params.update({k: v for k, v in kwargs.items() if k != "context"})
        try:
            self.validate_params(params)
        except Exception as exc:
            return _error_result(message=str(exc), code="VALIDATION_ERROR")

        node = params.get("node")
        section = params.get("section")
        output_format = str(params.get("format") or "summary")
        max_chars = int(params.get("max_chars") or 20000)

        nodes, source = _load_manual_nodes()
        package = _runtime_package_info(source)
        if not nodes:
            return _error_result(
                message="casmgr-server Info manual not found",
                code="INFO_NOT_FOUND",
                details={"searched": [str(p) for p in INFO_PATH_CANDIDATES]},
            )

        if output_format == "nodes":
            return SuccessResult(
                data={
                    "package": package,
                    "nodes": list(nodes.keys()),
                    "items": [],
                    "truncated": False,
                }
            )

        selected: List[str]
        if node:
            resolved = _resolve_node(nodes, str(node))
            if resolved is None:
                return _error_result(
                    message=f"Info node not found: {node}",
                    code="INFO_NODE_NOT_FOUND",
                    details={"nodes": list(nodes.keys())},
                )
            selected = [resolved]
        elif section:
            selected = _search_nodes(nodes, str(section))
        elif output_format == "text":
            selected = ["Top"] if "Top" in nodes else [next(iter(nodes))]
        else:
            selected = [
                n for n in ("Top", "Overview", "Installation", "Systemd") if n in nodes
            ]

        items: List[Dict[str, str]] = []
        budget_remaining = max_chars
        truncated = False
        for name in selected:
            text = nodes.get(name, "")
            clipped, was_truncated = _truncate(text, budget_remaining)
            items.append({"node": name, "text": clipped})
            truncated = truncated or was_truncated
            budget_remaining -= len(clipped)
            if budget_remaining <= 0:
                truncated = truncated or len(selected) > len(items)
                break

        return SuccessResult(
            data={
                "package": package,
                "nodes": list(nodes.keys()),
                "items": items,
                "matched_nodes": selected,
                "truncated": truncated,
            }
        )
