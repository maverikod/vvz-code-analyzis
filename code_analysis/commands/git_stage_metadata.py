"""Metadata helpers for git staging, commit, and restore commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

PROJECT_ID_PARAM = {
    "description": (
        "Project UUID. Use list_projects to discover valid project_id values. "
        "The command resolves this project to its registered repository root."
    ),
    "type": "string",
    "required": True,
    "examples": ["44a8ce88-b467-42a8-b874-033562b89bd0"],
}

PATHS_PARAM = {
    "description": (
        "Optional list of literal project-relative pathspecs passed after '--'. "
        "Use paths for targeted operations and avoid repository-wide changes."
    ),
    "type": "array",
    "required": False,
    "items": "string pathspec",
    "examples": [["README.md"], ["code_analysis/commands/git_stage_commands.py"]],
}


def _base_metadata(cls: Type[Any], detailed_description: str) -> Dict[str, Any]:
    """Build metadata fields shared by git working-tree commands."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": detailed_description,
    }


def get_git_add_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_add."""
    metadata = _base_metadata(
        cls,
        (
            "Stage changes in the git index for a registered project. This command "
            "is equivalent to 'git add' and is queued because it mutates repository "
            "state. It never commits by itself; use git_status to inspect staged "
            "entries and git_commit to create a commit.\n\n"
            "Operation flow:\n"
            "1. Resolve project_id to the project root.\n"
            "2. Verify that git is installed and the root is a git repository.\n"
            "3. Validate that exactly one staging mode is requested: explicit paths, "
            "all=true, or update=true.\n"
            "4. Run git add with pathspecs after '--' when paths are provided.\n"
            "5. Return the staging mode and git output.\n\n"
            "Safety notes:\n"
            "- paths stages only the selected pathspecs.\n"
            "- all=true stages additions, modifications, and deletions in the whole repo.\n"
            "- update=true stages modifications and deletions for tracked files only."
        ),
    )
    metadata.update(
        {
            "parameters": {
                "project_id": PROJECT_ID_PARAM,
                "paths": PATHS_PARAM,
                "all": {
                    "description": (
                        "Stage all changes in the repository, including untracked "
                        "files and deletions. Mutually exclusive with update=true."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                    "examples": [True, False],
                },
                "update": {
                    "description": (
                        "Stage only modifications and deletions for already tracked "
                        "files. Does not stage new untracked files."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                    "examples": [True, False],
                },
            },
            "return_value": {
                "success": {
                    "description": "Requested changes were staged.",
                    "data": {
                        "success": "Always True on success.",
                        "paths": "Pathspecs used for targeted staging.",
                        "all": "Whether repository-wide staging was used.",
                        "update": "Whether tracked-file update staging was used.",
                        "output": "stdout from git add, usually empty.",
                    },
                    "example": {
                        "success": True,
                        "paths": ["README.md"],
                        "all": False,
                        "update": False,
                        "output": "",
                    },
                },
                "error": {
                    "description": "Validation failed or git add returned non-zero.",
                    "code": "VALIDATION_ERROR | GIT_NOT_AVAILABLE | GIT_NOT_A_REPO | GIT_ADD_FAILED",
                    "details": "field, paths, all, update, stderr, or repository root.",
                },
            },
            "usage_examples": [
                {
                    "description": "Stage one file",
                    "command": {"project_id": "<uuid>", "paths": ["README.md"]},
                    "explanation": "Use for precise commits where only selected files should enter the index.",
                },
                {
                    "description": "Stage every changed file",
                    "command": {"project_id": "<uuid>", "all": True},
                    "explanation": "Equivalent to git add --all. Inspect with git_status before committing.",
                },
                {
                    "description": "Stage tracked updates only",
                    "command": {"project_id": "<uuid>", "update": True},
                    "explanation": "Equivalent to git add --update; leaves new untracked files unstaged.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "No staging target was provided, or all/update were both true.",
                    "message": "Provide paths, all=true, or update=true.",
                    "solution": "Pick one staging mode and retry.",
                },
                "GIT_ADD_FAILED": {
                    "description": "git add returned a non-zero exit code.",
                    "message": "Includes git stderr in details.stderr.",
                    "solution": "Check pathspecs, repository permissions, and git status.",
                },
            },
            "best_practices": [
                "Prefer explicit paths for small commits.",
                "Call git_status after git_add to confirm staged entries.",
                "Avoid all=true when unrelated local changes may be present.",
            ],
        }
    )
    return metadata


def get_git_commit_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_commit."""
    metadata = _base_metadata(
        cls,
        (
            "Create a commit from staged changes in a registered project. The command "
            "does not stage files automatically; call git_add first. It is queued "
            "because it mutates repository history. On success it returns the short "
            "HEAD commit hash after the commit.\n\n"
            "Operation flow:\n"
            "1. Resolve project_id and verify git repository availability.\n"
            "2. Validate that message is not empty.\n"
            "3. Run git commit -m <message>, optionally with --amend or --allow-empty.\n"
            "4. Resolve the new HEAD short hash with git rev-parse --short HEAD.\n"
            "5. Return commit metadata and git output."
        ),
    )
    metadata.update(
        {
            "parameters": {
                "project_id": PROJECT_ID_PARAM,
                "message": {
                    "description": "Commit message passed to git commit -m. Must not be empty.",
                    "type": "string",
                    "required": True,
                    "examples": ["Add branch management commands"],
                },
                "amend": {
                    "description": "If true, amend the current HEAD commit instead of creating a new commit.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                    "examples": [True, False],
                },
                "allow_empty": {
                    "description": "If true, allow creating a commit with no staged changes.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                    "examples": [True, False],
                },
            },
            "return_value": {
                "success": {
                    "description": "Commit was created or amended.",
                    "data": {
                        "success": "Always True on success.",
                        "commit": "Short hash of HEAD after the operation.",
                        "amend": "Whether --amend was used.",
                        "allow_empty": "Whether --allow-empty was used.",
                        "output": "stdout from git commit.",
                    },
                    "example": {
                        "success": True,
                        "commit": "c9b36e0a",
                        "amend": False,
                        "allow_empty": False,
                        "output": "[main c9b36e0] Add commands",
                    },
                },
                "error": {
                    "description": "Validation failed, git commit failed, or HEAD hash could not be read.",
                    "code": "VALIDATION_ERROR | GIT_COMMIT_FAILED | GIT_COMMIT_HASH_FAILED",
                    "details": "amend, allow_empty, stderr, or validation field.",
                },
            },
            "usage_examples": [
                {
                    "description": "Commit staged changes",
                    "command": {
                        "project_id": "<uuid>",
                        "message": "Add git worktree commands",
                    },
                    "explanation": "Creates a normal commit from whatever is already staged.",
                },
                {
                    "description": "Amend the last commit",
                    "command": {
                        "project_id": "<uuid>",
                        "message": "Add git worktree commands",
                        "amend": True,
                    },
                    "explanation": "Replaces HEAD with a new commit containing staged changes.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "The commit message is empty.",
                    "message": "Commit message must not be empty.",
                    "solution": "Provide a non-empty message.",
                },
                "GIT_COMMIT_FAILED": {
                    "description": "git commit returned non-zero, commonly because nothing is staged.",
                    "message": "Includes git stderr in details.stderr.",
                    "solution": "Run git_status/git_add, or set allow_empty=true when intentional.",
                },
            },
            "best_practices": [
                "Inspect git_status before committing.",
                "Use focused staging with git_add paths for reviewable commits.",
                "Use amend only when rewriting the latest local commit is intended.",
            ],
        }
    )
    return metadata


def get_git_restore_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_restore."""
    metadata = _base_metadata(
        cls,
        (
            "Restore files in the worktree and/or unstage files from the index. "
            "This command is equivalent to git restore with explicit --worktree and "
            "--staged flags. It is destructive for worktree changes when worktree=true "
            "because uncommitted file content can be discarded.\n\n"
            "Operation flow:\n"
            "1. Resolve project_id and verify git repository availability.\n"
            "2. Validate paths or all=true is provided.\n"
            "3. Validate at least one target is selected: staged or worktree.\n"
            "4. Run git restore with '--' before pathspecs, or '.' for all=true.\n"
            "5. Return the restore target and pathspecs."
        ),
    )
    metadata.update(
        {
            "parameters": {
                "project_id": PROJECT_ID_PARAM,
                "paths": PATHS_PARAM,
                "all": {
                    "description": "Restore all files under the repository root by passing '.' after '--'.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                    "examples": [True, False],
                },
                "staged": {
                    "description": "If true, restore the index, equivalent to git restore --staged.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                    "examples": [True, False],
                },
                "worktree": {
                    "description": (
                        "If true, restore worktree files, equivalent to git restore --worktree. "
                        "Default true; may discard uncommitted content."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": True,
                    "examples": [True, False],
                },
            },
            "return_value": {
                "success": {
                    "description": "Selected index/worktree paths were restored.",
                    "data": {
                        "success": "Always True on success.",
                        "paths": "Pathspecs restored, empty when all=true.",
                        "all": "Whether all files were targeted.",
                        "staged": "Whether index state was restored.",
                        "worktree": "Whether worktree files were restored.",
                        "output": "stdout from git restore, usually empty.",
                    },
                    "example": {
                        "success": True,
                        "paths": ["README.md"],
                        "all": False,
                        "staged": True,
                        "worktree": False,
                        "output": "",
                    },
                },
                "error": {
                    "description": "Validation failed or git restore returned non-zero.",
                    "code": "VALIDATION_ERROR | GIT_RESTORE_FAILED",
                    "details": "paths, all, staged, worktree, stderr, or validation field.",
                },
            },
            "usage_examples": [
                {
                    "description": "Unstage one file and keep its worktree changes",
                    "command": {
                        "project_id": "<uuid>",
                        "paths": ["README.md"],
                        "staged": True,
                        "worktree": False,
                    },
                    "explanation": "Equivalent to git restore --staged -- README.md.",
                },
                {
                    "description": "Discard one file's worktree changes",
                    "command": {"project_id": "<uuid>", "paths": ["README.md"]},
                    "explanation": "Restores README.md in the worktree from HEAD.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "No path target or no restore target was selected.",
                    "message": "Provide paths or all=true; staged or worktree must be true.",
                    "solution": "Pass explicit paths or all=true and choose staged/worktree behavior.",
                },
                "GIT_RESTORE_FAILED": {
                    "description": "git restore returned a non-zero exit code.",
                    "message": "Includes git stderr in details.stderr.",
                    "solution": "Check pathspecs and current repository state.",
                },
            },
            "best_practices": [
                "Use git_status before restore to avoid discarding the wrong file.",
                "Use staged=true, worktree=false when you only want to unstage.",
                "Avoid all=true unless the full repository cleanup is intentional.",
            ],
        }
    )
    return metadata
