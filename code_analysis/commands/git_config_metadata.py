"""Metadata helpers for git config and identity commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

from code_analysis.commands.git_stage_metadata import PROJECT_ID_PARAM

CONFIG_SCOPE_PARAM = {
    "description": (
        "Git config scope. local reads or writes .git/config for the resolved "
        "project. global reads the service user's global config. system is "
        "read-only and available only for get/list."
    ),
    "type": "string",
    "required": False,
    "default": "local",
    "enum": ["local", "global", "system", "effective"],
    "examples": ["local", "effective"],
}


def _base_metadata(cls: Type[Any], detailed_description: str) -> Dict[str, Any]:
    """Build common command metadata."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": detailed_description,
    }


def _common_errors(action_code: str) -> Dict[str, Dict[str, str]]:
    """Return common git config error documentation."""
    return {
        "VALIDATION_ERROR": {
            "description": "Input parameters failed semantic validation.",
            "message": "The message names the invalid field.",
            "solution": "Use an allowed scope, non-empty key/value, and explicit allow_global for global writes.",
        },
        "GIT_NOT_AVAILABLE": {
            "description": "git executable is not available on the server.",
            "message": "git executable is not available.",
            "solution": "Install git or fix PATH for the service process.",
        },
        "GIT_NOT_A_REPO": {
            "description": "Resolved project root is not a git repository.",
            "message": "The project root is not a git repository.",
            "solution": "Verify project_id and repository registration.",
        },
        action_code: {
            "description": "The underlying git config command returned non-zero.",
            "message": "Includes git stderr in details.stderr.",
            "solution": "Check key spelling, scope, repository state, and service-user permissions.",
        },
    }


def get_git_config_get_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_config_get."""
    metadata = _base_metadata(
        cls,
        (
            "Read one git configuration key for a registered project. By default "
            "the command reads local repository config from .git/config. Use "
            "scope=effective to let git resolve the normal precedence chain "
            "(system, global, local, and included config). Missing keys are not "
            "treated as transport failures; the command returns configured=false "
            "with value=null so callers can decide whether to set a default.\n\n"
            "Operation flow:\n"
            "1. Resolve project_id to the repository root.\n"
            "2. Validate scope and key.\n"
            "3. Run git config with the requested scope.\n"
            "4. Return configured, value, key, and scope."
        ),
    )
    metadata.update(
        {
            "parameters": {
                "project_id": PROJECT_ID_PARAM,
                "key": {
                    "description": "Git config key to read, for example user.name or user.email.",
                    "type": "string",
                    "required": True,
                    "examples": ["user.name", "remote.origin.url"],
                },
                "scope": CONFIG_SCOPE_PARAM,
            },
            "return_value": {
                "success": {
                    "description": "Config key was read or confirmed absent.",
                    "data": {
                        "success": "Always True when git config executes normally.",
                        "configured": "True when the key exists in the selected scope/effective view.",
                        "value": "String value, or null when configured=false.",
                        "key": "Requested key.",
                        "scope": "Requested scope.",
                    },
                    "example": {
                        "success": True,
                        "configured": True,
                        "key": "user.email",
                        "scope": "local",
                        "value": "bot@example.com",
                    },
                },
                "error": {
                    "description": "Validation failed or git config could not run.",
                    "code": "VALIDATION_ERROR | GIT_CONFIG_GET_FAILED",
                    "details": "key, scope, stderr, or validation field.",
                },
            },
            "usage_examples": [
                {
                    "description": "Read local commit author name",
                    "command": {"project_id": "<uuid>", "key": "user.name"},
                    "explanation": "Checks the repository-local identity used by git_commit.",
                },
                {
                    "description": "Read effective author email",
                    "command": {
                        "project_id": "<uuid>",
                        "key": "user.email",
                        "scope": "effective",
                    },
                    "explanation": "Lets git resolve local/global/system precedence.",
                },
            ],
            "error_cases": _common_errors("GIT_CONFIG_GET_FAILED"),
            "best_practices": [
                "Prefer local scope for automation-controlled project settings.",
                "Use git_identity_get for user.name/user.email checks.",
                "Use effective scope for diagnostics, not for deciding where to write.",
            ],
        }
    )
    return metadata


def get_git_config_list_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_config_list."""
    metadata = _base_metadata(
        cls,
        (
            "List git configuration visible to a registered project. local lists "
            ".git/config only, global lists the service user's global config, "
            "system lists system config, and effective lists git's merged view. "
            "include_origin=true adds the config file origin reported by git, "
            "which is useful when diagnosing why a command sees a particular value.\n\n"
            "Operation flow:\n"
            "1. Resolve project_id to the repository root.\n"
            "2. Run git config --list with the requested scope.\n"
            "3. Parse each key/value line, preserving origin when requested.\n"
            "4. Return entries and count."
        ),
    )
    metadata.update(
        {
            "parameters": {
                "project_id": PROJECT_ID_PARAM,
                "scope": CONFIG_SCOPE_PARAM,
                "include_origin": {
                    "description": "If true, include git's origin path/scope for each returned entry.",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                    "examples": [True, False],
                },
            },
            "return_value": {
                "success": {
                    "description": "Config entries were listed.",
                    "data": {
                        "success": "Always True on success.",
                        "entries": "List of {key, value, origin?} entries.",
                        "count": "Number of entries.",
                        "scope": "Requested scope.",
                    },
                    "example": {
                        "success": True,
                        "scope": "local",
                        "count": 2,
                        "entries": [
                            {
                                "key": "user.name",
                                "value": "casmgr-smoke",
                                "origin": "file:.git/config",
                            }
                        ],
                    },
                },
                "error": {
                    "description": "Validation failed or git config --list failed.",
                    "code": "VALIDATION_ERROR | GIT_CONFIG_LIST_FAILED",
                    "details": "scope, include_origin, stderr, or validation field.",
                },
            },
            "usage_examples": [
                {
                    "description": "List local repository config",
                    "command": {"project_id": "<uuid>", "scope": "local"},
                    "explanation": "Shows project-specific settings stored in .git/config.",
                }
            ],
            "error_cases": _common_errors("GIT_CONFIG_LIST_FAILED"),
            "best_practices": [
                "Use include_origin=true when diagnosing identity or remote settings.",
                "Avoid exposing full effective config in user-facing output if secrets may be present.",
            ],
        }
    )
    return metadata


def get_git_identity_get_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_identity_get."""
    metadata = _base_metadata(
        cls,
        (
            "Read the git commit identity for a registered project. The command "
            "reports local and effective values for user.name and user.email, plus "
            "configured=true only when the effective identity is complete. This is "
            "the safe preflight command before git_commit: callers can detect "
            "missing identity without attempting a commit.\n\n"
            "Operation flow:\n"
            "1. Resolve project_id to the repository root.\n"
            "2. Read local user.name and user.email.\n"
            "3. Read effective user.name and user.email.\n"
            "4. Return configured status and value sources."
        ),
    )
    metadata.update(
        {
            "parameters": {"project_id": PROJECT_ID_PARAM},
            "return_value": {
                "success": {
                    "description": "Identity information was read.",
                    "data": {
                        "success": "Always True on success.",
                        "configured": "True when effective name and email are both non-empty.",
                        "local": "Local identity values from .git/config.",
                        "effective": "Effective values resolved by git config.",
                    },
                    "example": {
                        "success": True,
                        "configured": True,
                        "local": {
                            "name": "casmgr-smoke",
                            "email": "casmgr-smoke@localhost",
                        },
                        "effective": {
                            "name": "casmgr-smoke",
                            "email": "casmgr-smoke@localhost",
                        },
                    },
                },
                "error": {
                    "description": "Repository resolution or git config execution failed.",
                    "code": "GIT_CONFIG_GET_FAILED",
                    "details": "stderr or repository availability details.",
                },
            },
            "usage_examples": [
                {
                    "description": "Check whether git_commit can create author metadata",
                    "command": {"project_id": "<uuid>"},
                    "explanation": "If configured=false, call git_identity_set with local scope.",
                }
            ],
            "error_cases": _common_errors("GIT_CONFIG_GET_FAILED"),
            "best_practices": [
                "Run before git_commit in newly registered repositories.",
                "Prefer git_identity_set over raw git_config_set for user.name/user.email.",
            ],
        }
    )
    return metadata


def get_git_identity_set_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_identity_set."""
    metadata = _base_metadata(
        cls,
        (
            "Set the git commit identity for a registered project. The default and "
            "recommended scope is local, which writes only to this repository's "
            ".git/config. Global writes are blocked unless scope=global and "
            "allow_global=true are both supplied. The command returns previous and "
            "new local/effective values so an agent can prove what changed.\n\n"
            "Operation flow:\n"
            "1. Resolve project_id to the repository root.\n"
            "2. Validate non-empty name and minimally valid email.\n"
            "3. Reject global writes unless allow_global=true.\n"
            "4. Read previous identity.\n"
            "5. Set user.name and user.email in the selected scope.\n"
            "6. Read and return the new identity."
        ),
    )
    metadata.update(
        {
            "parameters": {
                "project_id": PROJECT_ID_PARAM,
                "name": {
                    "description": "Git author/committer display name to store in config.",
                    "type": "string",
                    "required": True,
                    "examples": ["casmgr-smoke", "Automation Bot"],
                },
                "email": {
                    "description": "Git author/committer email to store in config.",
                    "type": "string",
                    "required": True,
                    "examples": ["casmgr-smoke@localhost", "bot@example.com"],
                },
                "scope": {
                    **CONFIG_SCOPE_PARAM,
                    "default": "local",
                    "enum": ["local", "global"],
                },
                "allow_global": {
                    "description": "Required true when scope=global. Ignored for local writes.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                    "examples": [False, True],
                },
            },
            "return_value": {
                "success": {
                    "description": "Identity values were written.",
                    "data": {
                        "success": "Always True on success.",
                        "scope": "Scope written.",
                        "previous": "Identity before the write.",
                        "current": "Identity after the write.",
                    },
                    "example": {
                        "success": True,
                        "scope": "local",
                        "previous": {"configured": False},
                        "current": {
                            "configured": True,
                            "local": {
                                "name": "casmgr-smoke",
                                "email": "casmgr-smoke@localhost",
                            },
                        },
                    },
                },
                "error": {
                    "description": "Validation failed or git config write failed.",
                    "code": "VALIDATION_ERROR | GIT_CONFIG_SET_FAILED",
                    "details": "field, scope, stderr, or repository availability details.",
                },
            },
            "usage_examples": [
                {
                    "description": "Set repository-local automation identity",
                    "command": {
                        "project_id": "<uuid>",
                        "name": "casmgr-smoke",
                        "email": "casmgr-smoke@localhost",
                    },
                    "explanation": "Writes only .git/config for the selected project.",
                }
            ],
            "error_cases": _common_errors("GIT_CONFIG_SET_FAILED"),
            "best_practices": [
                "Use local scope unless the user explicitly requests a global service-user identity.",
                "Run git_identity_get after setting identity when reporting operational evidence.",
                "Use a recognizable automation identity for smoke commits.",
            ],
        }
    )
    return metadata
