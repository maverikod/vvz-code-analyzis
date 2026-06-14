"""
Config load, validation, storage, and app_config merge for main entry point.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Tuple

from mcp_proxy_adapter.core.config.simple_config import SimpleConfig

from code_analysis.core.config_json import (
    ConfigJSONDecodeError,
    install_comment_json_for_mcp_adapter,
)
from code_analysis.core.storage_paths import (
    ensure_storage_dirs,
    resolve_storage_paths,
)
from code_analysis.core.server_log_dir import (
    append_server_startup_log,
    server_log_dir_from_config_data,
)
from code_analysis.main_server_presentation import sync_registration_presentation


def load_config_and_validate(
    args: Any,
) -> Tuple[Path, dict[str, Any]]:
    """
    Load config file and validate. Exits on error.
    Returns (config_path, full_config).
    """
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (Path.cwd() / config_path).resolve()
    if not config_path.exists():
        append_server_startup_log(
            Path.cwd() / "logs",
            f"config: file not found: {config_path}",
        )
        print(f"❌ Configuration file not found: {config_path}", file=sys.stderr)
        print(
            "   Generate one with: casmgr-config-generate --protocol https --with-proxy",
            file=sys.stderr,
        )
        sys.exit(1)

    from code_analysis.core.env_loader import load_dotenv_near_config

    load_dotenv_near_config(config_path)
    install_comment_json_for_mcp_adapter()

    from code_analysis.core.config_errors import print_config_error
    from code_analysis.core.config_state import (
        get_config_runtime_state,
        revalidate_config_at_path,
    )

    try:
        full_config, is_valid = revalidate_config_at_path(config_path)
    except ConfigJSONDecodeError as e:
        try:
            log_dir = server_log_dir_from_config_data({}, config_path)
        except Exception:
            log_dir = Path.cwd() / "logs"
        append_server_startup_log(log_dir, f"config: JSON parse error: {e}")
        print_config_error(str(e))
        sys.exit(1)
    except Exception as e:
        append_server_startup_log(
            Path.cwd() / "logs",
            f"config: read error for {config_path}: {e}",
        )
        print(f"❌ Failed to read configuration file: {e}", file=sys.stderr)
        sys.exit(1)

    log_dir = server_log_dir_from_config_data(full_config, config_path)
    append_server_startup_log(
        log_dir,
        f"config: loaded {config_path} valid={is_valid}",
    )

    if not is_valid:
        st = get_config_runtime_state()
        print_config_error("\n".join(st.error_lines))
        print(
            "\n⚠️  Starting in configuration error state "
            "(only help and health commands will work until config is fixed).",
            file=sys.stderr,
        )

    return (config_path, full_config)


def resolve_server_bind(
    *,
    args: Any,
    settings: Any,
    config_host: str,
    config_port: int,
) -> Tuple[str, int]:
    """
    Resolve Hypercorn bind host/port.

    Priority: CLI ``--host`` / ``--port`` > ``CODE_ANALYSIS_SERVER_*`` env >
    ``server.host`` / ``server.port`` from config.  Do not use
    ``settings.get("server_port")`` here — it always falls back to the dev
    constant (15000) and ignores config.json.
    """
    host = config_host
    port = config_port

    overrides = getattr(settings, "_cli_overrides", {}) or {}
    if "server_host" in overrides and not args.host:
        host = overrides["server_host"]
    if "server_port" in overrides and args.port is None:
        port = overrides["server_port"]

    if args.host:
        host = args.host
    if args.port is not None:
        port = args.port

    return host, int(port)


def ensure_storage_and_load_app_config(
    config_path: Path,
    full_config: dict[str, Any],
    args: Any,
) -> Tuple[dict[str, Any], SimpleConfig, str, int]:
    """
    Ensure storage dirs, load SimpleConfig, merge app_config, resolve server host/port.
    Exits on error. Returns (app_config, simple_config, server_host, server_port).
    """
    try:
        storage_paths = resolve_storage_paths(
            config_data=full_config,
            config_path=config_path.resolve(),
        )
        ensure_storage_dirs(storage_paths)
    except Exception as e:
        append_server_startup_log(
            server_log_dir_from_config_data(full_config, config_path),
            f"storage: prepare failed: {e}",
        )
        print(f"❌ Failed to prepare storage directories: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        simple_config = SimpleConfig(str(config_path))
        model = simple_config.load()
    except Exception as e:
        append_server_startup_log(
            server_log_dir_from_config_data(full_config, config_path),
            f"config: SimpleConfig load failed: {e}",
        )
        print(f"❌ Failed to load configuration: {e}", file=sys.stderr)
        sys.exit(1)

    if args.host:
        simple_config.model.server.host = args.host
    if args.port:
        simple_config.model.server.port = args.port

    from code_analysis.core.settings_manager import get_settings

    settings = get_settings()
    server_host, server_port = resolve_server_bind(
        args=args,
        settings=settings,
        config_host=simple_config.model.server.host,
        config_port=int(simple_config.model.server.port),
    )

    app_config = simple_config.to_dict()
    _merge_config_sections(app_config, full_config)
    sync_registration_presentation(app_config)

    return (app_config, simple_config, server_host, server_port)


def _merge_config_sections(
    app_config: dict[str, Any],
    full_config: dict[str, Any],
) -> None:
    """Merge top-level and ``registration`` keys from raw JSON into app_config."""
    for key, value in full_config.items():
        if key == "registration":
            continue
        if key not in app_config:
            app_config[key] = value

    src_reg = full_config.get("registration")
    if not isinstance(src_reg, dict):
        return
    dst_reg = app_config.get("registration")
    if not isinstance(dst_reg, dict):
        app_config["registration"] = dict(src_reg)
        return
    for reg_key, reg_value in src_reg.items():
        dst_reg[reg_key] = reg_value


def apply_global_config(
    config_path: Path,
    simple_config: SimpleConfig,
    app_config: dict[str, Any],
) -> None:
    """Update global config instance used by adapter internals."""
    from mcp_proxy_adapter.config import get_config

    cfg = get_config()
    cfg.config_path = str(config_path)
    setattr(cfg, "model", simple_config.model)
    cfg.config_data = app_config
    if hasattr(cfg, "feature_manager"):
        cfg.feature_manager.config_data = cfg.config_data

    sync_registration_presentation(cfg.config_data)

    if app_config.get("enable_qa_mcp_hooks") is True:
        if not (os.environ.get("CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS") or "").strip():
            os.environ["CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS"] = "1"
