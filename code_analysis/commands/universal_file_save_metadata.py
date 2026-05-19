"""Extended metadata for ``universal_file_save``."""

from __future__ import annotations

from typing import Any, Dict, Type

from .command_metadata_helpers import (
    build_command_metadata,
    parameters_from_schema,
    project_file_error_cases,
    simple_success_return,
)

_EXAMPLE_PROJECT = "550e8400-e29b-41d4-a716-446655440000"


def get_universal_file_save_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return build_command_metadata(
        cls,
        detailed_description=(
            "Registry-first **full-file save** for project files. The file extension "
            "selects one of four handlers (**text**, **json**, **yaml**, **python**) "
            "before any backup, parse check, or write.\n\n"
            "**All handlers — missing paths:**\n"
            "- ``file_path`` may point to a file that does not exist yet.\n"
            "- ``create_parent_dirs`` (default **true**): create missing parent directories "
            "like ``mkdir -p`` before writing.\n"
            "- Response field ``created`` is **true** when the file was absent before this call.\n"
            "- ``dry_run`` + ``diff`` preview works for new and existing files where the "
            "handler supports diff (text, json, yaml, python).\n\n"
            "**text** (``.md``, ``.txt``, ``.rst``, ``.adoc``, …): writes ``content`` as "
            "plain text; optional ``old_code`` backup when the file already exists; updates "
            "files-table metadata after apply.\n\n"
            "**json** (``.json``): ``content`` must be valid JSON text; builds an in-memory "
            "JSON tree and saves via ``save_json_tree_to_file`` (atomic write, DB sync, "
            "optional backup on overwrite).\n\n"
            "**yaml** (``.yaml`` / ``.yml``): ``content`` must parse as YAML; writes "
            "serialized document; optional backup on overwrite; may update DB metadata when "
            "``database`` is available in the handler path.\n\n"
            "**python** (``.py`` / ``.pyi`` / ``.pyw``):\n"
            "- **New file:** same pipeline as ``cst_create_file`` "
            "(``create_tree_from_code`` + ``save_tree_to_file``).\n"
            "- **Existing file:** CST ``run_ops_mode`` (full line-span replace, validation, "
            "backup, DB sync).\n"
            "- Optional ``tree_id``, ``validate_syntax_only`` apply only to Python.\n\n"
            "Unsupported extensions (e.g. ``.toml``) → ``UNSUPPORTED_FILE_EXTENSION`` "
            "before database access.\n\n"
            "Discovery: ``code_analysis.core.file_handlers.registry`` — "
            "``get_handler_schema(handler_id, 'save')``, ``list_handler_mappings()``."
        ),
        parameters=parameters_from_schema(cls.get_schema()),
        return_value=simple_success_return(
            data_fields={
                "success": "Always true on outer success envelope.",
                "handler_id": "text | json | yaml | python (from extension)",
                "operation": "Always save.",
                "file_path": "Echo of request file_path.",
                "project_id": "Echo of request project_id.",
                "dry_run": "Preview-only when true.",
                "changed": "Whether content would change or did change.",
                "created": "True when file_path did not exist before this call.",
                "diff": "Unified diff when diff=true (handler-dependent).",
                "would_create": "In dry_run: true when the file is missing.",
                "backup_uuid": "When old_code backup was created (handler-dependent).",
                "metadata_update": "Text (and sometimes YAML) DB metadata block.",
                "save_result": "Nested write details (json/yaml/python).",
                "tree_id": "Python new-file path may return CST tree_id.",
            },
            example={
                "success": True,
                "handler_id": "text",
                "operation": "save",
                "file_path": "docs/new_page.md",
                "project_id": _EXAMPLE_PROJECT,
                "dry_run": False,
                "changed": True,
                "created": True,
            },
        ),
        usage_examples=[
            {
                "description": "Create a new Markdown file (text handler)",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "file_path": "docs/guide/new_page.md",
                    "content": "# Guide\n\nBody text.\n",
                    "create_parent_dirs": True,
                },
                "explanation": (
                    "Extension routes to text handler: mkdir -p on docs/guide/, write file, "
                    "update files-table metadata."
                ),
            },
            {
                "description": "Create a new JSON config (json handler)",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "file_path": "config/settings.json",
                    "content": '{"debug": false, "port": 8080}\n',
                },
                "explanation": (
                    "Parses content as JSON, saves via json tree pipeline; created=true."
                ),
            },
            {
                "description": "Create a new YAML file (yaml handler)",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "file_path": "deploy/service.yaml",
                    "content": "replicas: 1\nimage: app:latest\n",
                },
                "explanation": "Parses YAML, writes serialized document; parents created if needed.",
            },
            {
                "description": "Create a new Python module (python handler)",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "file_path": "src/pkg/mod.py",
                    "content": '"""Module."""\n\nVALUE = 1\n',
                },
                "explanation": (
                    "Uses cst_create_file-equivalent pipeline when the path is missing; "
                    "existing .py files use CST run_ops_mode overwrite instead."
                ),
            },
            {
                "description": "Preview any handler without writing",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "file_path": "README.md",
                    "content": "# Updated\n",
                    "dry_run": True,
                    "diff": True,
                },
                "explanation": "No backup, disk write, or DB side effects.",
            },
            {
                "description": "Require existing parent directory (all handlers)",
                "command": {
                    "project_id": _EXAMPLE_PROJECT,
                    "file_path": "existing_dir/data.txt",
                    "content": "hello\n",
                    "create_parent_dirs": False,
                },
                "explanation": "PARENT_DIR_MISSING if existing_dir/ is absent.",
            },
        ],
        error_cases={
            **project_file_error_cases(),
            "UNSUPPORTED_FILE_EXTENSION": {
                "description": "Extension not mapped for save (e.g. .toml).",
                "solution": (
                    "Use a supported suffix or a specialized command "
                    "(cst_create_file for new .py only, create_text_file for some text types)."
                ),
            },
            "PARENT_DIR_MISSING": {
                "description": (
                    "create_parent_dirs=false and a parent directory is missing "
                    "(any handler)."
                ),
                "solution": "Set create_parent_dirs to true or create parents first.",
            },
            "VALIDATION_ERROR": {
                "description": (
                    "Invalid parameters, unparseable JSON/YAML content, or Python/CST "
                    "validation failure."
                ),
            },
            "validation_failed": {
                "description": "JSON/YAML content failed parse before write.",
                "solution": "Fix content to valid JSON or YAML text.",
            },
            "BACKUP_REQUIRED": {
                "description": "Mandatory old_code backup failed before overwrite.",
            },
            "CST_CREATE_ERROR": {
                "description": "Python new-file CST tree build failed.",
            },
            "CST_SAVE_ERROR": {
                "description": "Python new-file save_tree_to_file failed.",
            },
            "CST_REPLACE_ERROR": {
                "description": "Python overwrite CST ops failed.",
            },
        },
        best_practices=[
            "Resolve project_id via list_projects; file_path is project-relative only.",
            "Pick the right tool by extension: text/json/yaml/python handlers differ.",
            "Use create_parent_dirs=true (default) for nested paths like a/b/c/file.ext.",
            "Use dry_run and diff=true to preview before apply (all handlers where supported).",
            "For new .py prefer full valid module source in content, or use cst_create_file.",
            "For new .json/.yaml send parseable serialized documents in content.",
            "Set backup=false only when you accept skipping old_code for overwrites.",
        ],
    )
