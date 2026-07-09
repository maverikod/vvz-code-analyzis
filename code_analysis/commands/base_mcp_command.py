"""
Base class for MCP commands with common functionality.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult

from ..core.database_client.client import DatabaseClient
from ..core.database_client.exceptions import (
    ConnectionError as DBConnectionError,
)
from ..core.database_client.transient import (
    CATEGORY_RPC_CONNECT_REFUSED,
    MAX_ATTEMPTS,
    MAX_TOTAL_ELAPSED_SECONDS,
    compute_retry_delay,
    is_rpc_connect_refused,
)
from ..core.constants import DEFAULT_DB_DRIVER_SOCKET_DIR
from ..core.exceptions import (
    CodeAnalysisError,
    DatabaseError,
    ValidationError,
)
from ..core.storage_paths import (
    StoragePaths,
    load_raw_config,
    resolve_search_sessions_root,
    resolve_storage_paths,
)
from ..core.shared_database import get_shared_database
from .base_mcp_command_open_db import ensure_database_integrity
from .base_mcp_command_resolve_path import resolve_file_path_from_project

logger = logging.getLogger(__name__)


def _get_socket_path_from_db_path(db_path: Path) -> str:
    """Get socket path for database driver from database path.

    Args:
        db_path: Path to database file

    Returns:
        Socket path string
    """
    db_name = db_path.stem
    socket_dir = Path(DEFAULT_DB_DRIVER_SOCKET_DIR)
    socket_dir.mkdir(parents=True, exist_ok=True)
    return str(socket_dir / f"{db_name}_driver.sock")


class BaseMCPCommand(Command):
    """
    Base class for MCP commands with common functionality.

    Provides:
    - Database connection management
    - Project ID resolution
    - Standardized error handling
    - Common validation methods

    Command description contract (``mcp-proxy-adapter`` >= 8.10.19):
    - ``get_schema()`` — machine-readable input JSON Schema for validation and help.
    - ``metadata()`` — extended AI/docs fields; merged by the adapter into help payloads.
      Do not duplicate schema fields inside ``metadata()``; see
      ``docs/standards/METADATA_SCHEMA_STANDARD.md``.

    Notes:
        This base class also includes a SQLite physical integrity check.
        If the database file is corrupted (e.g. "database disk image is malformed"),
        it is backed up and recreated automatically.
    """

    @classmethod
    async def run(cls, **kwargs: Any) -> Any:
        """Run the command off the main event loop to keep the server responsive.

        The adapter dispatcher awaits ``run()`` directly on the single server
        event loop (the same loop that sends the proxy heartbeat). Command bodies
        do synchronous blocking work (DB RPC, ``flock``, ``subprocess``, LibCST),
        so executing them inline freezes the loop and the heartbeat, causing the
        proxy to deregister the server. We relocate the inherited adapter
        ``run()`` — which validates params and converts every exception into a
        result object — onto a bounded worker-thread pool, and only await the
        bridged future here so the main loop stays free.

        ``use_queue=True`` commands already run in a separate worker process and
        never reach here; they are handled inline defensively. Offload can be
        disabled via config/env (escape hatch) — then we fall back to inline.
        """
        from ..core.command_offload import offload_command_run, offload_enabled

        if getattr(cls, "use_queue", False) or not offload_enabled():
            return await super().run(**kwargs)
        return await offload_command_run(super().run, kwargs)

    @staticmethod
    def _ensure_database_integrity(db_path: Path) -> Dict[str, Any]:
        """Ensure SQLite physical integrity; delegates to open_db module."""
        return ensure_database_integrity(db_path)

    @staticmethod
    def _open_database_from_config(auto_analyze: bool = False) -> DatabaseClient:
        """Return the shared long-lived database client (no per-command open)."""
        return get_shared_database()

    def _open_database(
        self: "BaseMCPCommand",
        root_dir: Optional[str] = None,
        auto_analyze: bool = False,
    ) -> DatabaseClient:
        """Open database via universal entrypoint only (config-based). root_dir is ignored; no path selection."""
        return BaseMCPCommand._open_database_from_config(auto_analyze=auto_analyze)

    @staticmethod
    def _get_project_id_by_root_path(
        db: DatabaseClient, root_path: str
    ) -> Optional[str]:
        """Get project ID by resolved absolute root path (for internal use e.g. project_creation)."""
        from code_analysis.core.project_root_path import (
            find_project_id_by_resolved_absolute_root,
        )

        return find_project_id_by_resolved_absolute_root(db, root_path)

    @staticmethod
    def _get_project_id(
        db: DatabaseClient, root_path: Path, project_id: Optional[str] = None
    ) -> Optional[str]:
        """Resolve or create project ID. Prefer passing project_id and using _resolve_project_root.

        When creating a new project, resolves watch_dir_id from the DB so that
        projects.root_path stores only the project folder name (segment), not an
        absolute path. This keeps the canonical 3-component scheme consistent:
        watch_dir_paths.absolute_path / projects.name / files.relative_path.
        """
        from code_analysis.core.project_root_path import (
            persist_projects_root_path_stored_value,
        )

        def _resolve_watch_dir_id(abs_root: Path) -> Optional[str]:
            """Return watch_dir_id whose absolute_path is the direct parent of abs_root."""
            try:
                return db.resolve_watch_dir_id_for_project_root(abs_root)
            except Exception:
                return None

        if project_id:
            project = db.get_project(project_id)
            if project:
                return project_id
            existing = BaseMCPCommand._get_project_id_by_root_path(db, str(root_path))
            if existing and existing != project_id:
                raise ValidationError(
                    "Project root is already registered with a different project_id",
                    field="project_id",
                    details={
                        "root_path": str(root_path),
                        "existing_project_id": existing,
                        "provided_project_id": project_id,
                    },
                )
            project_name = root_path.name
            watch_dir_id = _resolve_watch_dir_id(root_path)
            root_stored = persist_projects_root_path_stored_value(
                project_root_absolute=root_path,
                watch_dir_id=watch_dir_id,
                database=db,
            )
            db.insert_project_row(
                project_id,
                root_stored,
                project_name,
                watch_dir_id=watch_dir_id,
            )
            return project_id
        existing_id = BaseMCPCommand._get_project_id_by_root_path(db, str(root_path))
        if existing_id:
            return existing_id
        new_id = str(uuid.uuid4())
        watch_dir_id = _resolve_watch_dir_id(root_path)
        root_stored = persist_projects_root_path_stored_value(
            project_root_absolute=root_path,
            watch_dir_id=watch_dir_id,
            database=db,
        )
        db.insert_project_row(
            new_id,
            root_stored,
            root_path.name,
            watch_dir_id=watch_dir_id,
        )
        return new_id

    @staticmethod
    def _resolve_config_path() -> Path:
        """
        Resolve active server config path.

        Priority:
        - mcp_proxy_adapter global config (cfg.config_path)
        - cwd/config.json
        """

        try:
            from mcp_proxy_adapter.config import get_config

            cfg = get_config()
            cfg_path = getattr(cfg, "config_path", None)
            if isinstance(cfg_path, str) and cfg_path.strip():
                return Path(cfg_path).expanduser().resolve()
        except Exception:
            pass

        return (Path.cwd() / "config.json").resolve()

    @staticmethod
    def _get_raw_config() -> Dict[str, Any]:
        """
        Load raw config dict from active server config path.

        Returns:
            Full config dict (e.g. for code_analysis.git_commit_on_write).
        """
        config_path = BaseMCPCommand._resolve_config_path()
        return load_raw_config(config_path)

    @staticmethod
    def _get_shared_storage() -> StoragePaths:
        """
        Resolve shared storage paths from application config (one DB for all projects).

        Returns:
            StoragePaths with db_path, backup_dir, etc. from server config.
        """
        config_path = BaseMCPCommand._resolve_config_path()
        config_data = load_raw_config(config_path)
        return resolve_storage_paths(config_data=config_data, config_path=config_path)

    @staticmethod
    def _get_search_sessions_root() -> Path:
        """Writable on-disk root for paginated search session directories."""
        config_path = BaseMCPCommand._resolve_config_path()
        config_data = load_raw_config(config_path)
        return resolve_search_sessions_root(
            config_data=config_data,
            config_path=config_path,
        )

    @staticmethod
    def _validate_project_id_exists(project_id: str) -> None:
        """
        Validate that project_id exists in the database. Use before queuing or heavy work.

        Args:
            project_id: Project UUID to check.

        Raises:
            ValidationError: If project_id is empty or project not found in database.
            DBConnectionError: If transient RPC connect-refused persists after retries
                (same policy as ``cst_save_tree`` execute).
        """
        if not project_id or not isinstance(project_id, str):
            raise ValidationError(
                "project_id is required",
                field="project_id",
                details={},
            )
        project_id = project_id.strip()
        if not project_id:
            raise ValidationError(
                "project_id is required",
                field="project_id",
                details={},
            )
        t_retry_start = time.perf_counter()
        for attempt in range(1, MAX_ATTEMPTS + 1):
            db = BaseMCPCommand._open_database_from_config()
            try:
                try:
                    project = db.get_project(project_id)
                except DBConnectionError as e:
                    if not is_rpc_connect_refused(e):
                        raise
                    elapsed = time.perf_counter() - t_retry_start
                    if attempt >= MAX_ATTEMPTS or elapsed >= MAX_TOTAL_ELAPSED_SECONDS:
                        logger.error(
                            "_validate_project_id_exists retry exhausted "
                            "category=%s attempts=%s elapsed_sec=%.2f",
                            CATEGORY_RPC_CONNECT_REFUSED,
                            attempt,
                            elapsed,
                        )
                        raise
                    delay = compute_retry_delay(attempt)
                    logger.warning(
                        "_validate_project_id_exists transient connect refused "
                        "attempt=%s/%s category=%s next_delay_sec=%.2f",
                        attempt,
                        MAX_ATTEMPTS,
                        CATEGORY_RPC_CONNECT_REFUSED,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                if not project:
                    hint = ""
                    if "-" not in project_id or len(project_id) < 36:
                        hint = (
                            " Use list_projects to get the project id (UUID), or read "
                            "projectid in the project root."
                        )
                    raise ValidationError(
                        f"Project with ID {project_id!r} not found in database.{hint}",
                        field="project_id",
                        details={"project_id": project_id},
                    )
                return
            finally:
                db.disconnect()

    @staticmethod
    def _validate_watch_dir_id_exists(watch_dir_id: str) -> None:
        """
        Validate that watch_dir_id exists in the database. Use before create_project or list_projects filter.

        Args:
            watch_dir_id: Watch directory UUID to check.

        Raises:
            ValidationError: If watch_dir_id is empty or watch dir not found in database.
        """
        if not watch_dir_id or not isinstance(watch_dir_id, str):
            raise ValidationError(
                "watch_dir_id is required",
                field="watch_dir_id",
                details={},
            )
        watch_dir_id = watch_dir_id.strip()
        if not watch_dir_id:
            raise ValidationError(
                "watch_dir_id is required",
                field="watch_dir_id",
                details={},
            )
        db = BaseMCPCommand._open_database_from_config()
        try:
            if not db.watch_dir_exists(watch_dir_id):
                rows = []
            else:
                rows = [{"id": watch_dir_id}]
            if not rows:
                hint = " Use list_watch_dirs to get watch directory IDs."
                raise ValidationError(
                    f"Watch directory with ID {watch_dir_id!r} not found in database.{hint}",
                    field="watch_dir_id",
                    details={"watch_dir_id": watch_dir_id},
                )
        finally:
            db.disconnect()

    @staticmethod
    def _resolve_project_root(project_id: str) -> Path:
        """
        Resolve project root directory from project_id (database only).

        Uses ``projects.root_path`` (watch-relative segment or legacy absolute) plus
        ``watch_dir_paths.absolute_path``. Falls back to ``watch_dir / projects.name``.
        Never treats an empty or relative path as the server working directory.

        Args:
            project_id: Project ID (UUID4). Root path is resolved from projects table.

        Returns:
            Resolved absolute Path to project root.

        Raises:
            ValidationError: If project_id not provided or project not found.
        """
        from ..core.exceptions import ValidationError
        from ..core.project_root_path import resolve_project_root_absolute_str

        if not project_id:
            raise ValidationError(
                "project_id is required",
                field="project_id",
                details={},
            )
        db = BaseMCPCommand._open_database_from_config()
        try:
            rows = db.select("projects", where={"id": project_id})
            if not rows:
                hint = ""
                if "-" not in project_id or len(project_id) < 36:
                    hint = " Use list_projects to get the project id (UUID), or read projectid in the project root."
                raise ValidationError(
                    f"Project with ID {project_id!r} not found in database.{hint}",
                    field="project_id",
                    details={"project_id": project_id},
                )
            row = dict(rows[0])
            abs_str = resolve_project_root_absolute_str(
                project_id=project_id,
                root_path_stored=str(row.get("root_path") or ""),
                watch_dir_id=(
                    str(row["watch_dir_id"])
                    if row.get("watch_dir_id") is not None
                    else None
                ),
                project_name=str(row.get("name") or "").strip() or None,
                database=db,
                require_exists=True,
            ).strip()
            if not abs_str or not Path(abs_str).is_absolute():
                raise ValidationError(
                    f"Cannot resolve absolute project root for project_id {project_id!r}",
                    field="project_id",
                    details={
                        "project_id": project_id,
                        "stored_root_path": row.get("root_path"),
                        "watch_dir_id": row.get("watch_dir_id"),
                        "name": row.get("name"),
                    },
                )
            root = Path(abs_str).resolve()
            if not root.is_dir():
                raise ValidationError(
                    f"Project root path does not exist: {root}",
                    field="project_id",
                    details={"project_id": project_id, "root_path": str(root)},
                )
            return root
        finally:
            db.disconnect()

    @staticmethod
    def _validate_file_path(file_path: str, root_path: Path) -> Path:
        """
        Validate and resolve file path relative to root.

        Args:
            file_path: File path (absolute or relative)
            root_path: Project root path

        Returns:
            Resolved Path object

        Raises:
            ValidationError: If file path is invalid
        """
        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.is_absolute():
                file_path_obj = root_path / file_path_obj

            if not file_path_obj.exists():
                raise ValidationError(
                    f"File does not exist: {file_path}",
                    field="file_path",
                    details={"file_path": file_path, "resolved": str(file_path_obj)},
                )

            if not file_path_obj.is_file():
                raise ValidationError(
                    f"Path is not a file: {file_path}",
                    field="file_path",
                    details={"file_path": file_path, "resolved": str(file_path_obj)},
                )

            return file_path_obj
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(
                f"Invalid file path: {str(e)}",
                field="file_path",
                details={"file_path": file_path, "error": str(e)},
            ) from e

    @staticmethod
    def _resolve_file_path_from_project(
        database: DatabaseClient,
        project_id: str,
        relative_file_path: str,
        *,
        require_exists: bool = True,
    ) -> Path:
        """Resolve absolute file path from project_id and relative path."""
        return resolve_file_path_from_project(
            database,
            project_id,
            relative_file_path,
            require_exists=require_exists,
        )

    def _handle_error(
        self: "BaseMCPCommand",
        error: Exception,
        error_code: str,
        operation: Optional[str] = None,
    ) -> ErrorResult:
        """
        Handle exception and convert to ErrorResult.

        Args:
            self: Command instance.
            error: Exception that occurred
            error_code: Error code for the result
            operation: Optional operation name for logging

        Returns:
            ErrorResult with error information
        """
        operation_str = f" ({operation})" if operation else ""
        logger.exception(f"Command failed{operation_str}: {error}")

        if isinstance(error, CodeAnalysisError):
            details = error.details.copy()
            details["error_type"] = type(error).__name__
            if hasattr(error, "operation") and error.operation:
                details["operation"] = error.operation
            if hasattr(error, "field") and error.field:
                details["field"] = error.field

            return ErrorResult(
                message=error.message,
                code=error.code or error_code,  # type: ignore[arg-type]
                details=details,
            )

        return ErrorResult(
            message=str(error),
            code=error_code,  # type: ignore[arg-type]
            details={"error_type": type(error).__name__, "error": str(error)},
        )

    @classmethod
    def _get_base_schema_properties(cls: type["BaseMCPCommand"]) -> Dict[str, Any]:
        """
        Get base schema properties common to most commands.

        Args:
            cls: Command class.

        Returns:
            Dictionary with common schema properties
        """
        return {
            "project_id": {
                "type": "string",
                "description": "Project UUID (from create_project or list_projects). Required for commands that operate on a project.",
            },
        }

    @staticmethod
    def _try_validate_schema_value(
        value: Any,
        prop: Dict[str, Any],
        *,
        field: str,
        command_name: str,
    ) -> bool:
        """Return True when *value* satisfies *prop*; False on ValidationError."""
        try:
            BaseMCPCommand._validate_schema_value(
                value,
                prop,
                field=field,
                command_name=command_name,
            )
            return True
        except ValidationError:
            return False

    @staticmethod
    def _validate_schema_value(
        value: Any,
        prop: Dict[str, Any],
        *,
        field: str,
        command_name: str,
    ) -> None:
        """
        Validate one value against a JSON Schema property (shallow subset).

        Supports type, enum, minimum/maximum, minItems/maxItems, simple
        array ``items`` schemas (single object with ``type`` only), and
        ``oneOf`` / ``anyOf`` unions when no top-level ``type`` is set.
        """
        expected_type = prop.get("type")
        one_of = prop.get("oneOf")
        any_of = prop.get("anyOf")
        if expected_type is None and (one_of or any_of):
            branches: list[Dict[str, Any]] = []
            union_label = ""
            if isinstance(one_of, list):
                branches = [b for b in one_of if isinstance(b, dict)]
                union_label = "oneOf"
            elif isinstance(any_of, list):
                branches = [b for b in any_of if isinstance(b, dict)]
                union_label = "anyOf"
            if not branches:
                raise ValidationError(
                    f"{command_name}: parameter {field!r} has empty {union_label}",
                    field=field,
                    details={union_label: one_of or any_of},
                )
            match_count = sum(
                1
                for branch in branches
                if BaseMCPCommand._try_validate_schema_value(
                    value,
                    branch,
                    field=field,
                    command_name=command_name,
                )
            )
            if union_label == "anyOf":
                if match_count < 1:
                    raise ValidationError(
                        f"{command_name}: parameter {field!r} must match at least "
                        f"one branch of anyOf, got {type(value).__name__}",
                        field=field,
                        details={"anyOf": any_of},
                    )
            elif match_count < 1:
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must match one branch "
                    f"of oneOf, got {type(value).__name__}",
                    field=field,
                    details={"oneOf": one_of},
                )
            if "enum" in prop and value is not None and value not in prop["enum"]:
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be one of {prop['enum']!r}, got {value!r}",
                    field=field,
                    details={"enum": prop["enum"]},
                )
            return

        expected_type = prop.get("type")
        if expected_type == "string":
            if not isinstance(value, str):
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be string, got {type(value).__name__}",
                    field=field,
                    details={},
                )
        elif expected_type == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be integer, got {type(value).__name__}",
                    field=field,
                    details={},
                )
            if "minimum" in prop and value < prop["minimum"]:
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be >= {prop['minimum']}, got {value}",
                    field=field,
                    details={"minimum": prop["minimum"], "value": value},
                )
            if "maximum" in prop and value > prop["maximum"]:
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be <= {prop['maximum']}, got {value}",
                    field=field,
                    details={"maximum": prop["maximum"], "value": value},
                )
        elif expected_type == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be number, got {type(value).__name__}",
                    field=field,
                    details={},
                )
            if "minimum" in prop and value < prop["minimum"]:
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be >= {prop['minimum']}, got {value}",
                    field=field,
                    details={"minimum": prop["minimum"], "value": value},
                )
            if "maximum" in prop and value > prop["maximum"]:
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be <= {prop['maximum']}, got {value}",
                    field=field,
                    details={"maximum": prop["maximum"], "value": value},
                )
        elif expected_type == "boolean":
            if not isinstance(value, bool):
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be boolean, got {type(value).__name__}",
                    field=field,
                    details={},
                )
        elif expected_type == "array":
            if not isinstance(value, list):
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be array, got {type(value).__name__}",
                    field=field,
                    details={},
                )
            if "minItems" in prop and len(value) < prop["minItems"]:
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must have at least "
                    f"{prop['minItems']} items, got {len(value)}",
                    field=field,
                    details={"minItems": prop["minItems"], "actual": len(value)},
                )
            if "maxItems" in prop and len(value) > prop["maxItems"]:
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must have at most "
                    f"{prop['maxItems']} items, got {len(value)}",
                    field=field,
                    details={"maxItems": prop["maxItems"], "actual": len(value)},
                )
            items_schema = prop.get("items")
            if isinstance(items_schema, dict) and "type" in items_schema:
                for index, item in enumerate(value):
                    if item is None:
                        continue
                    BaseMCPCommand._validate_schema_value(
                        item,
                        items_schema,
                        field=f"{field}[{index}]",
                        command_name=command_name,
                    )
        elif expected_type == "object":
            if not isinstance(value, dict):
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be object, got {type(value).__name__}",
                    field=field,
                    details={},
                )
        if "enum" in prop and value is not None:
            if value not in prop["enum"]:
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be one of {prop['enum']!r}, got {value!r}",
                    field=field,
                    details={"enum": prop["enum"]},
                )

    @staticmethod
    def validate_params_against_schema(
        params: Dict[str, Any],
        schema: Dict[str, Any],
        command_name: str = "command",
    ) -> None:
        """
        Validate that all present parameters conform to the command schema.
        Required/optional only control presence; if a param is present it must match type/enum.

        Args:
            params: Incoming parameters dict (e.g. from MCP request).
            schema: JSON Schema object with "properties" and optionally "additionalProperties".
            command_name: Name of the command for error messages.

        Raises:
            ValidationError: If any key is disallowed or any value fails type/enum check.
        """
        if not isinstance(params, dict):
            raise ValidationError(
                f"{command_name}: params must be a dict, got {type(params).__name__}",
                field="params",
                details={},
            )
        props = schema.get("properties") or {}
        additional_ok = schema.get("additionalProperties", False)
        required_set = set(schema.get("required") or [])
        for key, value in params.items():
            if key not in props:
                if not additional_ok:
                    raise ValidationError(
                        f"{command_name}: unknown parameter {key!r}. "
                        "Only schema-defined properties are allowed.",
                        field=key,
                        details={"allowed": list(props.keys())},
                    )
                continue
            if value is None:
                continue
            BaseMCPCommand._validate_schema_value(
                value,
                props[key],
                field=key,
                command_name=command_name,
            )
        # Required keys presence check
        for key in required_set:
            if key not in params or params[key] is None:
                raise ValidationError(
                    f"{command_name}: required parameter {key!r} is missing",
                    field=key,
                    details={},
                )

    def validate_params(
        self: "BaseMCPCommand", params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate parameters against command schema. Override to add identifier checks.

        Call this before queuing so invalid project_id (and other IDs) are rejected
        immediately instead of after job start. When schema has additionalProperties
        False, unknown keys raise ValidationError.

        Args:
            params: Incoming parameters dict.

        Returns:
            Validated params (unchanged when validation succeeds).

        Raises:
            ValidationError: If params fail schema or identifier validation.
        """
        schema = self.get_schema()
        params = {k: v for k, v in params.items() if k != "context"}
        BaseMCPCommand.validate_params_against_schema(
            params, schema, command_name=getattr(self, "name", "command")
        )
        return params
