"""
Hard-fail contract for comprehensive_analysis quality checks (A-HARDFAIL).

Replaces silent degradation: when a check is REQUESTED but its tool cannot be
imported/run from the server interpreter, the command must fail fast with a
structured error instead of returning a bogus "clean" result. Availability is
probed once, up front, before any file iteration.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult

from ...core.code_quality import is_tool_available

# Maps a requested check flag → the tool that must be available for it.
CHECK_TO_TOOL = {
    "check_flake8": "flake8",
    "check_mypy": "mypy",
    "check_black": "black",
    "check_isort": "isort",
    "check_bandit": "bandit",
}

QUALITY_TOOL_UNAVAILABLE = "QUALITY_TOOL_UNAVAILABLE"


def probe_required_tools(requested: Dict[str, bool]) -> Optional[ErrorResult]:
    """Fail fast if any requested quality check's tool is unavailable.

    Args:
        requested: mapping of ``check_<tool>`` flag → whether it was requested.

    Returns:
        An ``ErrorResult`` (code ``QUALITY_TOOL_UNAVAILABLE``) for the first
        missing tool, or ``None`` when every requested tool is available. Checks
        that are not requested are never probed (their tool's absence is
        irrelevant).
    """
    for check_flag, tool in CHECK_TO_TOOL.items():
        if not requested.get(check_flag):
            continue
        if not is_tool_available(tool):
            return ErrorResult(
                message=(
                    f"Quality tool {tool!r} is required by {check_flag!r} but is not "
                    f"importable from the server interpreter. It must be present in "
                    f"the server image/venv. Rebuild with the quality-tools manifest, "
                    f"or set {check_flag}=false to skip this check."
                ),
                code=QUALITY_TOOL_UNAVAILABLE,
                details={"tool": tool, "requested_check": check_flag},
            )
    return None
