"""Metadata helpers for advanced git history and tag commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

from code_analysis.commands.git_stage_metadata import PROJECT_ID_PARAM


def _base_metadata(cls: Type[Any], detailed_description: str) -> Dict[str, Any]:
    """Build metadata fields shared by advanced git commands."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": detailed_description,
    }


def _ref_param(description: str, required: bool = True) -> Dict[str, Any]:
    """Return a metadata record for a git ref parameter."""
    return {
        "description": description,
        "type": "string",
        "required": required,
        "examples": ["main", "origin/main", "v1.6.29", "HEAD~1"],
    }


def _bool_param(
    description: str,
    default: bool = False,
    required: bool = False,
) -> Dict[str, Any]:
    """Return a metadata record for a boolean parameter."""
    return {
        "description": description,
        "type": "boolean",
        "required": required,
        "default": default,
        "examples": [True, False],
    }


def _standard_return(command: str, output_name: str = "output") -> Dict[str, Any]:
    """Return common success/error metadata for git-mutating commands."""
    return {
        "success": {
            "description": f"{command} completed successfully.",
            "data": {
                "success": "Always True on success.",
                output_name: f"stdout from {command}, trimmed.",
                "stderr": f"stderr from {command}, trimmed when git reports progress there.",
            },
            "example": {"success": True, output_name: "", "stderr": ""},
        },
        "error": {
            "description": (
                "Validation failed, git is unavailable, the project is not a git "
                f"repository, or {command} returned a non-zero exit code."
            ),
            "code": (
                "VALIDATION_ERROR | GIT_NOT_AVAILABLE | GIT_NOT_A_REPO | "
                "GIT_*_FAILED | GIT_*_TIMEOUT"
            ),
            "details": "Validation field, git stderr, selected refs, mode, or paths.",
        },
    }


def get_git_reset_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_reset."""
    metadata = _base_metadata(
        cls,
        (
            "Move HEAD and/or reset index/worktree state for a registered project's "
            "git repository. This command wraps git reset. It supports soft, mixed, "
            "and hard reset modes plus path-limited mixed resets. Because reset can "
            "rewrite local repository state, the command is queued and validates the "
            "dangerous hard mode with an explicit confirm_hard flag.\n\n"
            "Operation flow:\n"
            "1. Resolve project_id to the registered project root.\n"
            "2. Verify git is installed and the root is a repository.\n"
            "3. Validate mode, target ref, and optional pathspecs.\n"
            "4. Reject hard resets unless confirm_hard=true.\n"
            "5. Run git reset with '--' before pathspecs when path-limited.\n"
            "6. Return selected mode, target, paths, stdout, and stderr.\n\n"
            "Safety notes: soft resets move HEAD only; mixed resets update the index; "
            "hard resets update HEAD, index, and worktree and may discard uncommitted "
            "content."
        ),
    )
    metadata.update(
        {
            "parameters": {
                "project_id": PROJECT_ID_PARAM,
                "mode": {
                    "description": "Reset mode: soft, mixed, or hard. Defaults to mixed.",
                    "type": "string",
                    "required": False,
                    "default": "mixed",
                    "enum": ["soft", "mixed", "hard"],
                    "examples": ["mixed", "soft", "hard"],
                },
                "target": _ref_param(
                    "Commit-ish to reset to. Defaults to HEAD.", required=False
                ),
                "paths": {
                    "description": (
                        "Optional pathspecs for a path-limited mixed reset. Not allowed "
                        "with soft or hard mode."
                    ),
                    "type": "array",
                    "required": False,
                    "items": "string pathspec",
                    "examples": [["README.md"], ["src/app.py"]],
                },
                "confirm_hard": _bool_param(
                    "Required true when mode=hard to confirm destructive worktree reset."
                ),
            },
            "return_value": _standard_return("git reset"),
            "usage_examples": [
                {
                    "description": "Unstage one file",
                    "command": {
                        "project_id": "<uuid>",
                        "mode": "mixed",
                        "paths": ["README.md"],
                    },
                    "explanation": "Equivalent to git reset -- README.md.",
                },
                {
                    "description": "Move HEAD back but keep changes staged",
                    "command": {
                        "project_id": "<uuid>",
                        "mode": "soft",
                        "target": "HEAD~1",
                    },
                    "explanation": "Useful when the last local commit should be redone.",
                },
                {
                    "description": "Hard reset to upstream",
                    "command": {
                        "project_id": "<uuid>",
                        "mode": "hard",
                        "target": "origin/main",
                        "confirm_hard": True,
                    },
                    "explanation": "Destructive: discards local tracked-file changes.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "Invalid mode, unsafe hard reset, or paths with non-mixed mode.",
                    "message": "Hard reset requires confirm_hard=true.",
                    "solution": "Choose the correct mode and set confirm_hard only when intended.",
                },
                "GIT_RESET_FAILED": {
                    "description": "git reset returned non-zero.",
                    "message": "details.stderr contains git's diagnostic.",
                    "solution": "Check target ref, pathspecs, and repository state.",
                },
            },
            "best_practices": [
                "Run git_status before reset.",
                "Prefer path-limited mixed reset for unstaging files.",
                "Use hard reset only after checking that no valuable worktree changes exist.",
            ],
        }
    )
    return metadata


def get_git_clean_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_clean."""
    metadata = _base_metadata(
        cls,
        (
            "Remove untracked files from a registered git repository by wrapping git "
            "clean. The command is destructive when dry_run=false, so dry_run defaults "
            "to true and actual deletion requires confirm=true. It can include "
            "directories and choose how ignored files are handled.\n\n"
            "Operation flow:\n"
            "1. Resolve project_id and validate repository availability.\n"
            "2. Build git clean flags: -n for dry-run, -f for deletion, -d for dirs.\n"
            "3. Add ignored-file mode: none, matching (-x), or only ignored (-X).\n"
            "4. Append pathspecs after '--' when provided.\n"
            "5. Return stdout/stderr and whether deletion was only simulated."
        ),
    )
    metadata.update(
        {
            "parameters": {
                "project_id": PROJECT_ID_PARAM,
                "dry_run": _bool_param(
                    "If true, show what would be removed without deleting anything.",
                    default=True,
                ),
                "confirm": _bool_param(
                    "Required true when dry_run=false to confirm deletion."
                ),
                "directories": _bool_param(
                    "If true, include untracked directories with git clean -d."
                ),
                "ignored": {
                    "description": (
                        "Ignored-file behavior: none leaves ignored files alone, "
                        "matching removes ignored and unignored files (-x), only removes "
                        "ignored files only (-X)."
                    ),
                    "type": "string",
                    "required": False,
                    "default": "none",
                    "enum": ["none", "matching", "only"],
                    "examples": ["none", "matching", "only"],
                },
                "paths": {
                    "description": "Optional project-relative pathspecs to limit cleaning.",
                    "type": "array",
                    "required": False,
                    "items": "string pathspec",
                    "examples": [["build/"], ["tmp/output.txt"]],
                },
            },
            "return_value": _standard_return("git clean"),
            "usage_examples": [
                {
                    "description": "Preview untracked files that would be removed",
                    "command": {"project_id": "<uuid>", "dry_run": True},
                    "explanation": "Safe default equivalent to git clean -n.",
                },
                {
                    "description": "Remove untracked build directory",
                    "command": {
                        "project_id": "<uuid>",
                        "dry_run": False,
                        "confirm": True,
                        "directories": True,
                        "paths": ["build/"],
                    },
                    "explanation": "Deletes only the selected untracked directory.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "Deletion requested without confirm=true or invalid ignored mode.",
                    "message": "git_clean deletion requires dry_run=false and confirm=true.",
                    "solution": "Run a dry-run first, then retry with confirm=true.",
                },
                "GIT_CLEAN_FAILED": {
                    "description": "git clean returned non-zero.",
                    "message": "details.stderr contains git's diagnostic.",
                    "solution": "Check pathspecs and file permissions.",
                },
            },
            "best_practices": [
                "Always run the default dry-run before deleting.",
                "Use paths to avoid removing unrelated untracked work.",
                "Avoid ignored=matching unless generated ignored artifacts are intended targets.",
            ],
        }
    )
    return metadata


def get_git_tag_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_tag."""
    metadata = _base_metadata(
        cls,
        (
            "List, create, delete, push, or delete remote git tags for a registered "
            "project. This single command wraps common git tag workflows so release "
            "management can be done through MCP. Local deletion and remote deletion "
            "require explicit confirmation flags because tags are shared coordination "
            "points in many teams.\n\n"
            "Actions:\n"
            "- list: return local tags matching an optional pattern.\n"
            "- create: create lightweight or annotated tags at a target ref.\n"
            "- delete: delete a local tag, requiring confirm_delete=true.\n"
            "- push: push one tag or all local tags to a remote.\n"
            "- delete_remote: delete a tag from a remote, requiring confirm_delete=true."
        ),
    )
    metadata.update(
        {
            "parameters": {
                "project_id": PROJECT_ID_PARAM,
                "action": {
                    "description": "Tag action to perform.",
                    "type": "string",
                    "required": False,
                    "default": "list",
                    "enum": ["list", "create", "delete", "push", "delete_remote"],
                    "examples": ["list", "create", "push"],
                },
                "name": {
                    "description": "Tag name for create/delete/push/delete_remote actions.",
                    "type": "string",
                    "required": False,
                    "examples": ["v1.6.29"],
                },
                "target": _ref_param(
                    "Target commit-ish for create. Defaults to HEAD.", required=False
                ),
                "message": {
                    "description": "Annotated tag message. When set, git tag -a -m is used.",
                    "type": "string",
                    "required": False,
                    "examples": ["Release 1.6.29"],
                },
                "remote": {
                    "description": "Remote name for push/delete_remote. Defaults to origin.",
                    "type": "string",
                    "required": False,
                    "default": "origin",
                    "examples": ["origin"],
                },
                "pattern": {
                    "description": "Optional pattern for list, for example v1.*.",
                    "type": "string",
                    "required": False,
                    "examples": ["v1.*"],
                },
                "all": _bool_param("For action=push, push all local tags."),
                "force": _bool_param("Force create or push where git supports it."),
                "confirm_delete": _bool_param(
                    "Required true for local or remote tag deletion."
                ),
            },
            "return_value": _standard_return("git tag or git push"),
            "usage_examples": [
                {
                    "description": "List release tags",
                    "command": {
                        "project_id": "<uuid>",
                        "action": "list",
                        "pattern": "v1.*",
                    },
                    "explanation": "Returns sorted local tag names and count.",
                },
                {
                    "description": "Create annotated release tag",
                    "command": {
                        "project_id": "<uuid>",
                        "action": "create",
                        "name": "v1.6.29",
                        "message": "Release 1.6.29",
                    },
                    "explanation": "Creates an annotated tag at HEAD.",
                },
                {
                    "description": "Push one tag",
                    "command": {
                        "project_id": "<uuid>",
                        "action": "push",
                        "name": "v1.6.29",
                    },
                    "explanation": "Pushes refs/tags/v1.6.29 to origin.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "Required tag name missing, invalid action, or deletion unconfirmed.",
                    "message": "Tag deletion requires confirm_delete=true.",
                    "solution": "Provide the required fields for the selected action.",
                },
                "GIT_TAG_FAILED": {
                    "description": "git tag or git push returned non-zero.",
                    "message": "details.stderr contains git's diagnostic.",
                    "solution": "Check tag existence, remote access, and push permissions.",
                },
            },
            "best_practices": [
                "Prefer annotated tags for releases.",
                "List tags before deletion.",
                "Avoid force-pushing tags unless coordinating with the team.",
            ],
        }
    )
    return metadata


def get_git_merge_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_merge."""
    metadata = _base_metadata(
        cls,
        (
            "Merge another branch or ref into the current branch of a registered "
            "project. The command supports normal merges, --no-ff, --ff-only, "
            "--squash, --no-commit, and merge abort. It is queued because it mutates "
            "the index, worktree, and possibly history.\n\n"
            "Operation flow:\n"
            "1. Resolve project_id and verify git repository availability.\n"
            "2. If abort=true, run git merge --abort and ignore all merge-target flags.\n"
            "3. Validate ref and mutually exclusive ff_only/squash combinations.\n"
            "4. Run git merge with requested flags and optional message.\n"
            "5. Return stdout/stderr so conflict diagnostics are visible."
        ),
    )
    metadata.update(
        {
            "parameters": {
                "project_id": PROJECT_ID_PARAM,
                "ref": _ref_param("Branch or commit-ish to merge.", required=False),
                "no_ff": _bool_param(
                    "Create a merge commit even when fast-forward is possible."
                ),
                "ff_only": _bool_param("Fail unless the merge can fast-forward."),
                "squash": _bool_param(
                    "Squash changes into the index without creating a merge commit."
                ),
                "commit": _bool_param(
                    "Allow git to create a merge commit.", default=True
                ),
                "message": {
                    "description": "Optional merge commit message passed with -m.",
                    "type": "string",
                    "required": False,
                    "examples": ["Merge feature/api"],
                },
                "abort": _bool_param(
                    "Run git merge --abort to leave an in-progress merge."
                ),
            },
            "return_value": _standard_return("git merge"),
            "usage_examples": [
                {
                    "description": "Fast-forward only merge",
                    "command": {
                        "project_id": "<uuid>",
                        "ref": "origin/main",
                        "ff_only": True,
                    },
                    "explanation": "Updates current branch only if no merge commit is needed.",
                },
                {
                    "description": "Abort conflicted merge",
                    "command": {"project_id": "<uuid>", "abort": True},
                    "explanation": "Equivalent to git merge --abort.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "Missing ref for normal merge or incompatible options.",
                    "message": "ref is required unless abort=true.",
                    "solution": "Provide a ref or set abort=true.",
                },
                "GIT_MERGE_FAILED": {
                    "description": "git merge returned non-zero, commonly due to conflicts.",
                    "message": "details.stderr contains git's diagnostic.",
                    "solution": "Inspect git_status, resolve conflicts, or abort.",
                },
            },
            "best_practices": [
                "Run git_status before merging.",
                "Use ff_only when synchronizing with upstream branches.",
                "Use squash for review branches when a merge commit is not desired.",
            ],
        }
    )
    return metadata


def get_git_cherry_pick_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_cherry_pick."""
    metadata = _base_metadata(
        cls,
        (
            "Apply one or more existing commits onto the current branch with git "
            "cherry-pick. The command also exposes --abort and --continue for "
            "conflict recovery through MCP. It is queued because it mutates history, "
            "the index, and the worktree.\n\n"
            "Operation flow:\n"
            "1. Resolve project_id and repository availability.\n"
            "2. If abort or continue_pick is set, run the corresponding recovery command.\n"
            "3. Otherwise validate at least one commit ref.\n"
            "4. Run git cherry-pick with --no-commit when requested.\n"
            "5. Return stdout/stderr for conflict or success diagnostics."
        ),
    )
    metadata.update(
        {
            "parameters": {
                "project_id": PROJECT_ID_PARAM,
                "commits": {
                    "description": "Commit refs to cherry-pick in the order provided.",
                    "type": "array",
                    "required": False,
                    "items": "string commit-ish",
                    "examples": [["abc1234"], ["abc1234", "def5678"]],
                },
                "no_commit": _bool_param(
                    "Apply changes to index/worktree without committing."
                ),
                "abort": _bool_param("Abort an in-progress cherry-pick."),
                "continue_pick": _bool_param(
                    "Continue an in-progress cherry-pick after conflicts are resolved."
                ),
            },
            "return_value": _standard_return("git cherry-pick"),
            "usage_examples": [
                {
                    "description": "Cherry-pick one commit",
                    "command": {"project_id": "<uuid>", "commits": ["abc1234"]},
                    "explanation": "Creates a new commit on the current branch.",
                },
                {
                    "description": "Apply without committing",
                    "command": {
                        "project_id": "<uuid>",
                        "commits": ["abc1234"],
                        "no_commit": True,
                    },
                    "explanation": "Leaves changes staged for inspection or a custom commit.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "No commit was provided or recovery flags conflict.",
                    "message": "commits is required unless abort=true or continue_pick=true.",
                    "solution": "Provide commits or choose one recovery action.",
                },
                "GIT_CHERRY_PICK_FAILED": {
                    "description": "git cherry-pick returned non-zero, often due to conflicts.",
                    "message": "details.stderr contains git's diagnostic.",
                    "solution": "Resolve conflicts and continue, or abort.",
                },
            },
            "best_practices": [
                "Use a fresh branch before cherry-picking.",
                "Cherry-pick the oldest commit first when applying a series.",
                "Use no_commit=true when combining several commits into one.",
            ],
        }
    )
    return metadata


def get_git_revert_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_revert."""
    metadata = _base_metadata(
        cls,
        (
            "Create inverse commits for one or more existing commits with git revert. "
            "The command exposes --abort and --continue for conflict recovery. It is "
            "safer than reset for shared branches because it preserves history by "
            "adding new commits instead of moving existing refs.\n\n"
            "Operation flow:\n"
            "1. Resolve project_id and repository availability.\n"
            "2. If abort or continue_revert is set, run the corresponding recovery command.\n"
            "3. Otherwise validate commits and optional mainline parent for merge commits.\n"
            "4. Run git revert, optionally with --no-commit.\n"
            "5. Return stdout/stderr for success or conflict diagnostics."
        ),
    )
    metadata.update(
        {
            "parameters": {
                "project_id": PROJECT_ID_PARAM,
                "commits": {
                    "description": "Commit refs to revert in the order provided.",
                    "type": "array",
                    "required": False,
                    "items": "string commit-ish",
                    "examples": [["abc1234"], ["abc1234", "def5678"]],
                },
                "no_commit": _bool_param("Apply inverse changes without committing."),
                "mainline": {
                    "description": "Parent number for reverting a merge commit, passed as -m.",
                    "type": "integer",
                    "required": False,
                    "examples": [1, 2],
                },
                "abort": _bool_param("Abort an in-progress revert."),
                "continue_revert": _bool_param(
                    "Continue an in-progress revert after conflicts are resolved."
                ),
            },
            "return_value": _standard_return("git revert"),
            "usage_examples": [
                {
                    "description": "Revert one commit",
                    "command": {"project_id": "<uuid>", "commits": ["abc1234"]},
                    "explanation": "Creates a new commit that undoes abc1234.",
                },
                {
                    "description": "Stage inverse changes without committing",
                    "command": {
                        "project_id": "<uuid>",
                        "commits": ["abc1234"],
                        "no_commit": True,
                    },
                    "explanation": "Allows inspection before creating a custom revert commit.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "No commits, invalid mainline, or conflicting recovery flags.",
                    "message": "commits is required unless abort=true or continue_revert=true.",
                    "solution": "Provide commits or choose one recovery action.",
                },
                "GIT_REVERT_FAILED": {
                    "description": "git revert returned non-zero, often due to conflicts.",
                    "message": "details.stderr contains git's diagnostic.",
                    "solution": "Resolve conflicts and continue, or abort.",
                },
            },
            "best_practices": [
                "Prefer revert over reset on shared branches.",
                "Use no_commit=true when reverting multiple commits into one commit.",
                "For merge commits, pass the intended mainline parent explicitly.",
            ],
        }
    )
    return metadata


def get_git_rebase_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed metadata for git_rebase."""
    metadata = _base_metadata(
        cls,
        (
            "Replay the current branch on top of another base with git rebase. The "
            "command supports normal rebase, --onto, --autostash, --abort, "
            "--continue, and --skip. Interactive rebase is intentionally not exposed "
            "because it requires editor-driven todo-file interaction; use explicit "
            "non-interactive operations instead. The command is queued because it "
            "rewrites local history and mutates the index and worktree.\n\n"
            "Operation flow:\n"
            "1. Resolve project_id to the registered repository root.\n"
            "2. Verify git is installed and the root is a git repository.\n"
            "3. If abort/continue_rebase/skip is set, run exactly one recovery action.\n"
            "4. Otherwise validate upstream and optional branch/onto parameters.\n"
            "5. Run git rebase with requested non-interactive flags.\n"
            "6. Return stdout/stderr so conflict and replay diagnostics are visible.\n\n"
            "Safety notes: rebase rewrites local commits. Prefer it for unpublished "
            "branches or after coordinating with collaborators."
        ),
    )
    metadata.update(
        {
            "parameters": {
                "project_id": PROJECT_ID_PARAM,
                "upstream": _ref_param(
                    "Upstream/base ref to replay the branch onto.", required=False
                ),
                "branch": _ref_param(
                    "Optional branch to check out and rebase instead of current branch.",
                    required=False,
                ),
                "onto": _ref_param(
                    "Optional new base passed as git rebase --onto <onto>.",
                    required=False,
                ),
                "autostash": _bool_param(
                    "Automatically stash and re-apply local changes around the rebase."
                ),
                "abort": _bool_param("Abort an in-progress rebase."),
                "continue_rebase": _bool_param(
                    "Continue an in-progress rebase after conflicts are resolved."
                ),
                "skip": _bool_param(
                    "Skip the current patch during an in-progress rebase."
                ),
            },
            "return_value": _standard_return("git rebase"),
            "usage_examples": [
                {
                    "description": "Rebase current branch onto origin/main",
                    "command": {"project_id": "<uuid>", "upstream": "origin/main"},
                    "explanation": "Equivalent to git rebase origin/main.",
                },
                {
                    "description": "Abort conflicted rebase",
                    "command": {"project_id": "<uuid>", "abort": True},
                    "explanation": "Equivalent to git rebase --abort.",
                },
                {
                    "description": "Rebase a named branch with autostash",
                    "command": {
                        "project_id": "<uuid>",
                        "upstream": "origin/main",
                        "branch": "feature/api",
                        "autostash": True,
                    },
                    "explanation": "Checks out/rebases the named branch using git rebase syntax.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "Missing upstream or multiple recovery actions were selected.",
                    "message": "upstream is required unless abort, continue_rebase, or skip is true.",
                    "solution": "Provide upstream for a normal rebase or choose one recovery action.",
                },
                "GIT_REBASE_FAILED": {
                    "description": "git rebase returned non-zero, commonly because of conflicts.",
                    "message": "details.stderr contains git's diagnostic.",
                    "solution": "Resolve conflicts and continue, skip, or abort.",
                },
            },
            "best_practices": [
                "Run git_status before rebasing.",
                "Use rebase mainly on local/unpublished branches.",
                "Use abort to return to the pre-rebase state when conflicts are not intended.",
            ],
        }
    )
    return metadata
