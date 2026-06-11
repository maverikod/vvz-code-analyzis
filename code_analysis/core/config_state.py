"""
Runtime configuration validity state (re-validated on each config load).

When invalid, MCP commands are blocked except ``help`` and ``health``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional

from code_analysis.core.config_errors import (
    format_config_json_error_report,
    format_validation_error_report,
    format_validation_result_line,
)
from code_analysis.core.config_json import ConfigJSONDecodeError, load_config_json
from code_analysis.core.config_validator import CodeAnalysisConfigValidator

logger = logging.getLogger(__name__)

ALLOWED_COMMANDS_WHEN_CONFIG_INVALID: FrozenSet[str] = frozenset({"help", "health"})


@dataclass
class ConfigRuntimeState:
    """Thread-safe snapshot of the last config validation outcome."""

    valid: bool = True
    config_path: Optional[Path] = None
    error_lines: List[str] = field(default_factory=list)
    warning_lines: List[str] = field(default_factory=list)
    last_config_data: Optional[Dict[str, Any]] = None

    def summary(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "config_path": str(self.config_path) if self.config_path else None,
            "errors": list(self.error_lines),
            "warnings": list(self.warning_lines),
        }


_lock = threading.Lock()
_state = ConfigRuntimeState()


def get_config_runtime_state() -> ConfigRuntimeState:
    with _lock:
        return ConfigRuntimeState(
            valid=_state.valid,
            config_path=_state.config_path,
            error_lines=list(_state.error_lines),
            warning_lines=list(_state.warning_lines),
            last_config_data=_state.last_config_data,
        )


def is_config_valid() -> bool:
    with _lock:
        return _state.valid


def config_blocks_command(command_name: Optional[str]) -> bool:
    if is_config_valid():
        return False
    if not command_name:
        return True
    return command_name.strip().lower() not in ALLOWED_COMMANDS_WHEN_CONFIG_INVALID


def config_invalid_command_message() -> str:
    st = get_config_runtime_state()
    lines = [
        "Server is in configuration error state; only help and health are available."
    ]
    if st.error_lines:
        lines.append("Configuration errors:")
        for line in st.error_lines:
            if line.startswith("Fix the issues") or line.startswith("Validate after"):
                continue
            lines.append(f"  {line}" if line.startswith("  ") else f"  {line}")
    if st.config_path:
        lines.append(f"Config file: {st.config_path}")
    lines.append(
        "Fix config.json, then run: casmgr-config-validate --file "
        + (str(st.config_path) if st.config_path else "<config.json>")
    )
    return "\n".join(lines)


def _set_state(
    *,
    valid: bool,
    config_path: Optional[Path],
    error_lines: List[str],
    warning_lines: List[str],
    config_data: Optional[Dict[str, Any]],
) -> None:
    global _state
    with _lock:
        _state = ConfigRuntimeState(
            valid=valid,
            config_path=config_path,
            error_lines=error_lines,
            warning_lines=warning_lines,
            last_config_data=config_data,
        )


def mark_config_invalid_from_exception(
    exc: Exception,
    *,
    config_path: Optional[Path] = None,
) -> None:
    if isinstance(exc, ConfigJSONDecodeError):
        report = str(exc) or format_config_json_error_report(
            exc,
            config_path=config_path or exc.source_path,
            source_text=exc.source_text,
        )
        _set_state(
            valid=False,
            config_path=config_path or exc.source_path,
            error_lines=report.splitlines(),
            warning_lines=[],
            config_data=None,
        )
        logger.error("Configuration JSON invalid:\n%s", report)
        return

    _set_state(
        valid=False,
        config_path=config_path,
        error_lines=[str(exc)],
        warning_lines=[],
        config_data=None,
    )
    logger.error("Configuration invalid: %s", exc)


def revalidate_config_at_path(config_path: Path) -> tuple[Dict[str, Any], bool]:
    """
    Parse and semantically validate ``config.json``.

    Updates global runtime state. Returns ``(config_data, is_valid)``.
    Raises ``ConfigJSONDecodeError`` on syntax failure (state marked invalid).
    """
    path = Path(config_path).resolve()
    try:
        config_data = load_config_json(path)
    except ConfigJSONDecodeError as exc:
        mark_config_invalid_from_exception(exc, config_path=path)
        raise

    validator = CodeAnalysisConfigValidator(str(path))
    validator.config_data = config_data
    results = validator.validate_config(config_data)
    summary = validator.get_validation_summary()

    warning_lines = [
        format_validation_result_line(r) for r in results if r.level == "warning"
    ]

    if summary["is_valid"]:
        _set_state(
            valid=True,
            config_path=path,
            error_lines=[],
            warning_lines=warning_lines,
            config_data=config_data,
        )
        if warning_lines:
            logger.warning(
                "Configuration valid with %s warning(s):\n%s",
                len(warning_lines),
                "\n".join(f"  - {w}" for w in warning_lines),
            )
        return config_data, True

    report = format_validation_error_report(results, config_path=path)
    _set_state(
        valid=False,
        config_path=path,
        error_lines=report.splitlines(),
        warning_lines=warning_lines,
        config_data=config_data,
    )
    logger.error("Configuration validation failed:\n%s", report)
    return config_data, False
