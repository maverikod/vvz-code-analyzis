"""Metadata helpers for git stash commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

from code_analysis.commands.git_stage_metadata import PATHS_PARAM, PROJECT_ID_PARAM


def _base_metadata(cls: Type[Any], detailed_description: str) -> Dict[str, Any]:
    """Build metadata fields shared by stash commands."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": detailed_description,
    }


def _stash_ref_param(required: bool = False) -> Dict[str, Any]:
    """Return metadata for a stash ref parameter."""
    return {
        "description": (
            "Stash reference to operate on, such as stash@{0}. Defaults to the "
            "most recent stash. Use git_stash_list to discover available refs."
        ),
        "type": "string",
        "required": required,
        "default": "stash@{0}",
        "examples": ["stash@{0}", "stash@{1}"],
    }


def _common_stash_errors(action_code: str) -> Dict[str, Dict[str, str]]:
    """Return common stash error documentation."""
    return {
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
            "description": "The underlying git stash command returned non-zero.",
            "message": "Includes git stderr in details.stderr.",
            "solution": "Inspect stash refs, working-tree state, and conflicts.",
        },
    }


def get_git_stash_list_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_stash_list."""
    metadata = _base_metadata(
        cls,
        (
            "List stash entries for a registered project's git repository. This is "
            "read-only and returns refs in the same order as git stash list, newest "
            "first. Each entry contains the stash ref and the summary string emitted "
            "by git, including branch/context and message. Use this command before "
            "apply or drop operations so an agent can choose the correct stash ref "
            "without guessing. The command does not inspect stash diffs or file "
            "contents; it only exposes the stash catalogue. Remember that stash refs "
            "are positional: after dropping stash@{0}, the previous stash@{1} becomes "
            "stash@{0}.\n\n"
            "Operation flow:\n"
            "1. Resolve project_id to the repository root.\n"
            "2. Verify git availability and repository validity.\n"
            "3. Run git stash list --date=iso.\n"
            "4. Parse each line into {ref, summary}.\n"
            "5. Return entries and count."
        ),
    )
    metadata.update(
        {
            "parameters": {"project_id": PROJECT_ID_PARAM},
            "return_value": {
                "success": {
                    "description": "Stash entries were listed.",
                    "data": {
                        "success": "Always True on success.",
                        "entries": "List of {ref, summary} entries.",
                        "count": "Number of stash entries.",
                    },
                    "example": {
                        "success": True,
                        "entries": [
                            {"ref": "stash@{0}", "summary": "On main: before rebase"}
                        ],
                        "count": 1,
                    },
                },
                "error": {
                    "description": "git stash list failed.",
                    "code": "GIT_STASH_LIST_FAILED",
                    "details": "stderr or repository availability details.",
                },
            },
            "usage_examples": [
                {
                    "description": "List available stashes",
                    "command": {"project_id": "<uuid>"},
                    "explanation": "Use before git_stash_apply or git_stash_drop to choose a ref.",
                }
            ],
            "error_cases": _common_stash_errors("GIT_STASH_LIST_FAILED"),
            "best_practices": [
                "Call git_stash_list before applying or dropping a non-default stash.",
                "Treat stash refs as volatile: stash@{1} may change after dropping stash@{0}.",
            ],
        }
    )
    return metadata


def get_git_stash_push_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_stash_push."""
    metadata = _base_metadata(
        cls,
        (
            "Save current working-tree changes to the git stash. This command is "
            "queued because it mutates repository state. By default git stashes "
            "tracked modifications only; include_untracked=true also captures "
            "untracked files. paths limits the stash to selected pathspecs.\n\n"
            "Operation flow:\n"
            "1. Resolve project_id and verify git repository availability.\n"
            "2. Build git stash push options from message, include_untracked, keep_index, and paths.\n"
            "3. Run git stash push, placing pathspecs after '--' when provided.\n"
            "4. Return git output describing whether a stash was saved."
        ),
    )
    metadata.update(
        {
            "parameters": {
                "project_id": PROJECT_ID_PARAM,
                "message": {
                    "description": "Optional stash message passed with -m for later identification.",
                    "type": "string",
                    "required": False,
                    "examples": ["before rebase", "save local experiment"],
                },
                "paths": PATHS_PARAM,
                "include_untracked": {
                    "description": "If true, include untracked files in the stash.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                    "examples": [True, False],
                },
                "keep_index": {
                    "description": "If true, keep staged changes in the index after stashing.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                    "examples": [True, False],
                },
            },
            "return_value": {
                "success": {
                    "description": "Stash push completed. Git may report that no changes were saved.",
                    "data": {
                        "success": "Always True when git exits with zero.",
                        "paths": "Pathspecs included in the stash.",
                        "include_untracked": "Whether untracked files were included.",
                        "keep_index": "Whether staged changes were left in the index.",
                        "output": "stdout from git stash push.",
                    },
                    "example": {
                        "success": True,
                        "paths": [],
                        "include_untracked": False,
                        "keep_index": False,
                        "output": "Saved working directory and index state On main: before rebase",
                    },
                },
                "error": {
                    "description": "git stash push failed.",
                    "code": "GIT_STASH_PUSH_FAILED",
                    "details": "paths, include_untracked, keep_index, stderr.",
                },
            },
            "usage_examples": [
                {
                    "description": "Stash tracked changes with a message",
                    "command": {"project_id": "<uuid>", "message": "before rebase"},
                    "explanation": "Saves tracked changes and restores the worktree.",
                },
                {
                    "description": "Stash selected files including untracked ones",
                    "command": {
                        "project_id": "<uuid>",
                        "paths": ["README.md", "notes.txt"],
                        "include_untracked": True,
                    },
                    "explanation": "Limits the stash to the listed pathspecs.",
                },
            ],
            "error_cases": _common_stash_errors("GIT_STASH_PUSH_FAILED"),
            "best_practices": [
                "Use a message for stashes that may live longer than a few minutes.",
                "Run git_status before and after stashing to confirm what changed.",
                "Use paths to avoid hiding unrelated work.",
            ],
        }
    )
    return metadata


def get_git_stash_apply_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_stash_apply."""
    metadata = _base_metadata(
        cls,
        (
            "Apply a stash entry to the current working tree without dropping it. "
            "This is queued because it may modify files and the index. Conflicts are "
            "reported by git as command failure and the working tree may need manual "
            "resolution with follow-up commands. Prefer apply over pop in automated "
            "workflows because the stash remains available after success or conflict. "
            "Use index=true only when the stash was created with staged changes and "
            "the caller explicitly wants to restore the index state as well as file "
            "content. The command does not switch branches and does not verify that "
            "the target branch matches the branch where the stash was created.\n\n"
            "Operation flow:\n"
            "1. Resolve project_id and verify git repository availability.\n"
            "2. Validate ref is not empty.\n"
            "3. Run git stash apply, optionally with --index.\n"
            "4. Return git output."
        ),
    )
    metadata.update(
        {
            "parameters": {
                "project_id": PROJECT_ID_PARAM,
                "ref": _stash_ref_param(required=False),
                "index": {
                    "description": "If true, try to restore the staged/index state from the stash.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                    "examples": [True, False],
                },
            },
            "return_value": {
                "success": {
                    "description": "Stash entry was applied and retained.",
                    "data": {
                        "success": "Always True on success.",
                        "ref": "Stash ref applied.",
                        "index": "Whether --index was used.",
                        "output": "stdout from git stash apply.",
                    },
                    "example": {
                        "success": True,
                        "ref": "stash@{0}",
                        "index": False,
                        "output": "",
                    },
                },
                "error": {
                    "description": "Validation failed or git stash apply returned non-zero.",
                    "code": "VALIDATION_ERROR | GIT_STASH_APPLY_FAILED",
                    "details": "ref, index, stderr, or validation field.",
                },
            },
            "usage_examples": [
                {
                    "description": "Apply the newest stash",
                    "command": {"project_id": "<uuid>"},
                    "explanation": "Applies stash@{0}; the stash remains in the stash list.",
                },
                {
                    "description": "Apply a specific stash and restore index state",
                    "command": {
                        "project_id": "<uuid>",
                        "ref": "stash@{1}",
                        "index": True,
                    },
                    "explanation": "Use when the stash captured staged changes that should be restored.",
                },
            ],
            "error_cases": {
                **_common_stash_errors("GIT_STASH_APPLY_FAILED"),
                "VALIDATION_ERROR": {
                    "description": "Stash ref is empty.",
                    "message": "Stash ref must not be empty.",
                    "solution": "Pass a valid ref such as stash@{0}.",
                },
            },
            "best_practices": [
                "Call git_status before applying a stash to avoid overwriting work.",
                "Prefer apply over pop because the stash remains available after conflicts.",
                "Use git_stash_drop only after verifying the applied changes.",
            ],
        }
    )
    return metadata


def get_git_stash_drop_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_stash_drop."""
    metadata = _base_metadata(
        cls,
        (
            "Drop a stash entry from the stash list. This command is destructive: "
            "after success the dropped stash ref is no longer available through git "
            "stash list. It is queued because it mutates repository state. Use this "
            "only after git_stash_list and, ideally, after git_stash_apply plus "
            "git_status confirm the changes are present where expected. The command "
            "does not apply the stash before dropping it and does not create a backup. "
            "Because stash refs are positional, dropping one entry renumbers older "
            "entries; agents should refresh git_stash_list before any second drop.\n\n"
            "Operation flow:\n"
            "1. Resolve project_id and verify git repository availability.\n"
            "2. Validate ref is not empty.\n"
            "3. Run git stash drop <ref>.\n"
            "4. Return git output."
        ),
    )
    metadata.update(
        {
            "parameters": {"project_id": PROJECT_ID_PARAM, "ref": _stash_ref_param()},
            "return_value": {
                "success": {
                    "description": "Stash entry was dropped.",
                    "data": {
                        "success": "Always True on success.",
                        "ref": "Stash ref dropped.",
                        "output": "stdout from git stash drop.",
                    },
                    "example": {
                        "success": True,
                        "ref": "stash@{0}",
                        "output": "Dropped stash@{0}",
                    },
                },
                "error": {
                    "description": "Validation failed or git stash drop returned non-zero.",
                    "code": "VALIDATION_ERROR | GIT_STASH_DROP_FAILED",
                    "details": "ref, stderr, or validation field.",
                },
            },
            "usage_examples": [
                {
                    "description": "Drop the newest stash",
                    "command": {"project_id": "<uuid>"},
                    "explanation": "Removes stash@{0}; run git_stash_list first if unsure.",
                },
                {
                    "description": "Drop a specific stash",
                    "command": {"project_id": "<uuid>", "ref": "stash@{1}"},
                    "explanation": "Use the ref returned by git_stash_list.",
                },
            ],
            "error_cases": {
                **_common_stash_errors("GIT_STASH_DROP_FAILED"),
                "VALIDATION_ERROR": {
                    "description": "Stash ref is empty.",
                    "message": "Stash ref must not be empty.",
                    "solution": "Pass a valid ref such as stash@{0}.",
                },
            },
            "best_practices": [
                "Run git_stash_list immediately before dropping because refs shift.",
                "Apply and verify a stash before dropping it.",
                "Avoid dropping another user's or automation-created stash without context.",
            ],
        }
    )
    return metadata
