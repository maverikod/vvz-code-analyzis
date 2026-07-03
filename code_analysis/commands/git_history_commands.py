"""Advanced git history, cleanup, and tag MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.git_history_metadata import (
    get_git_cherry_pick_metadata,
    get_git_clean_metadata,
    get_git_merge_metadata,
    get_git_rebase_metadata,
    get_git_reset_metadata,
    get_git_revert_metadata,
    get_git_tag_metadata,
)
from code_analysis.commands.git_worktree_base import (
    GitWorktreeCommand,
    string_list,
    validation_error,
)


def _git_output_data(
    *,
    success: bool,
    stdout: str,
    stderr: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a common success payload for git commands."""
    payload: Dict[str, Any] = {
        "success": success,
        "output": stdout.strip(),
        "stderr": stderr.strip(),
    }
    payload.update(extra or {})
    return payload


class GitResetCommand(GitWorktreeCommand):
    """Reset HEAD, index, or selected paths in a project's git repository."""

    name = "git_reset"
    version = "1.0.0"
    descr = "Reset HEAD, index, or selected paths in a project's git repository."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_reset"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID. Use list_projects to discover valid values.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["soft", "mixed", "hard"],
                    "default": "mixed",
                    "description": "Reset mode: soft, mixed, or hard.",
                },
                "target": {
                    "type": "string",
                    "default": "HEAD",
                    "description": "Commit-ish to reset to. Defaults to HEAD.",
                },
                "paths": {
                    "type": "array",
                    "description": (
                        "Optional pathspecs for a path-limited mixed reset. "
                        "Not allowed with soft or hard mode."
                    ),
                    "items": {"type": "string"},
                },
                "confirm_hard": {
                    "type": "boolean",
                    "default": False,
                    "description": "Required true when mode=hard.",
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_reset."""
        return get_git_reset_metadata(cls)

    async def execute(
        self,
        project_id: str,
        mode: str = "mixed",
        target: str = "HEAD",
        paths: Optional[List[str]] = None,
        confirm_hard: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_reset command."""
        _ = kwargs
        pathspecs = string_list(paths)
        mode_value = (mode or "mixed").strip().lower()
        target_value = (target or "HEAD").strip() or "HEAD"
        if mode_value not in {"soft", "mixed", "hard"}:
            return validation_error("mode must be soft, mixed, or hard", "mode")
        if pathspecs and mode_value != "mixed":
            return validation_error("paths are allowed only with mode=mixed", "paths")
        if mode_value == "hard" and not confirm_hard:
            return validation_error(
                "Hard reset requires confirm_hard=true",
                "confirm_hard",
            )
        args = ["reset", f"--{mode_value}", target_value]
        if pathspecs:
            args.extend(["--", *pathspecs])
        result, error = self._run_local_git(
            project_id,
            args,
            error_code="GIT_RESET_FAILED",
            action="git reset",
            details={
                "mode": mode_value,
                "target": target_value,
                "paths": pathspecs,
                "confirm_hard": confirm_hard,
            },
        )
        if error is not None:
            return error
        stdout, stderr = result or ("", "")
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                _git_output_data(
                    success=True,
                    stdout=stdout,
                    stderr=stderr,
                    extra={
                        "mode": mode_value,
                        "target": target_value,
                        "paths": pathspecs,
                    },
                ),
            )
        )


class GitCleanCommand(GitWorktreeCommand):
    """Remove untracked files from a project's git repository."""

    name = "git_clean"
    version = "1.0.0"
    descr = "Preview or remove untracked files from a project's git repository."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_clean"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID. Use list_projects to discover valid values.",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true, preview removals without deleting files.",
                },
                "confirm": {
                    "type": "boolean",
                    "default": False,
                    "description": "Required true when dry_run=false.",
                },
                "directories": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include untracked directories with git clean -d.",
                },
                "ignored": {
                    "type": "string",
                    "enum": ["none", "matching", "only"],
                    "default": "none",
                    "description": "Ignored-file handling: none, matching (-x), or only (-X).",
                },
                "paths": {
                    "type": "array",
                    "description": "Optional project-relative pathspecs limiting cleanup.",
                    "items": {"type": "string"},
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_clean."""
        return get_git_clean_metadata(cls)

    async def execute(
        self,
        project_id: str,
        dry_run: bool = True,
        confirm: bool = False,
        directories: bool = False,
        ignored: str = "none",
        paths: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_clean command."""
        _ = kwargs
        ignored_value = (ignored or "none").strip().lower()
        if ignored_value not in {"none", "matching", "only"}:
            return validation_error(
                "ignored must be none, matching, or only",
                "ignored",
            )
        if not dry_run and not confirm:
            return validation_error(
                "Deleting untracked files requires confirm=true",
                "confirm",
            )
        pathspecs = string_list(paths)
        args = ["clean", "-n" if dry_run else "-f"]
        if directories:
            args.append("-d")
        if ignored_value == "matching":
            args.append("-x")
        elif ignored_value == "only":
            args.append("-X")
        if pathspecs:
            args.extend(["--", *pathspecs])
        result, error = self._run_local_git(
            project_id,
            args,
            error_code="GIT_CLEAN_FAILED",
            action="git clean",
            details={
                "dry_run": dry_run,
                "directories": directories,
                "ignored": ignored_value,
                "paths": pathspecs,
            },
        )
        if error is not None:
            return error
        stdout, stderr = result or ("", "")
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                _git_output_data(
                    success=True,
                    stdout=stdout,
                    stderr=stderr,
                    extra={
                        "dry_run": dry_run,
                        "directories": directories,
                        "ignored": ignored_value,
                        "paths": pathspecs,
                    },
                ),
            )
        )


class GitTagCommand(GitWorktreeCommand):
    """List, create, delete, and push git tags."""

    name = "git_tag"
    version = "1.0.0"
    descr = "List, create, delete, push, or delete remote git tags."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_tag"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID. Use list_projects to discover valid values.",
                },
                "action": {
                    "type": "string",
                    "enum": ["list", "create", "delete", "push", "delete_remote"],
                    "default": "list",
                    "description": "Tag action to perform.",
                },
                "name": {
                    "type": "string",
                    "description": "Tag name for create/delete/push/delete_remote.",
                },
                "target": {
                    "type": "string",
                    "default": "HEAD",
                    "description": "Target commit-ish for create. Defaults to HEAD.",
                },
                "message": {
                    "type": "string",
                    "description": "Annotated tag message; when set, git tag -a -m is used.",
                },
                "remote": {
                    "type": "string",
                    "default": "origin",
                    "description": "Remote name for push/delete_remote.",
                },
                "pattern": {
                    "type": "string",
                    "description": "Optional pattern for list, for example v1.*.",
                },
                "all": {
                    "type": "boolean",
                    "default": False,
                    "description": "For action=push, push all local tags.",
                },
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "Force create or push where git supports it.",
                },
                "confirm_delete": {
                    "type": "boolean",
                    "default": False,
                    "description": "Required true for local or remote tag deletion.",
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_tag."""
        return get_git_tag_metadata(cls)

    async def execute(
        self,
        project_id: str,
        action: str = "list",
        name: Optional[str] = None,
        target: str = "HEAD",
        message: Optional[str] = None,
        remote: str = "origin",
        pattern: Optional[str] = None,
        all: bool = False,
        force: bool = False,
        confirm_delete: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_tag command."""
        _ = kwargs
        action_value = (action or "list").strip().lower()
        if action_value not in {"list", "create", "delete", "push", "delete_remote"}:
            return validation_error("Unsupported tag action", "action")
        tag_name = (name or "").strip()
        remote_value = (remote or "origin").strip() or "origin"

        args: List[str]
        if action_value == "list":
            args = ["tag", "--list"]
            if pattern:
                args.append(pattern)
        elif action_value == "create":
            if not tag_name:
                return validation_error("name is required for tag create", "name")
            args = ["tag"]
            if force:
                args.append("--force")
            if message and message.strip():
                args.extend(["-a", tag_name, "-m", message])
            else:
                args.append(tag_name)
            target_value = (target or "HEAD").strip() or "HEAD"
            args.append(target_value)
        elif action_value == "delete":
            if not tag_name:
                return validation_error("name is required for tag delete", "name")
            if not confirm_delete:
                return validation_error(
                    "Tag deletion requires confirm_delete=true",
                    "confirm_delete",
                )
            args = ["tag", "-d", tag_name]
        elif action_value == "push":
            if not all and not tag_name:
                return validation_error(
                    "name or all=true is required for tag push",
                    "name",
                )
            args = ["push"]
            if force:
                args.append("--force")
            args.append(remote_value)
            args.append("--tags" if all else tag_name)
        else:
            if not tag_name:
                return validation_error(
                    "name is required for remote tag delete",
                    "name",
                )
            if not confirm_delete:
                return validation_error(
                    "Remote tag deletion requires confirm_delete=true",
                    "confirm_delete",
                )
            args = ["push", remote_value, "--delete", tag_name]

        result, error = self._run_local_git(
            project_id,
            args,
            error_code="GIT_TAG_FAILED",
            action="git tag",
            details={
                "action": action_value,
                "name": tag_name,
                "remote": remote_value,
                "all": all,
                "force": force,
            },
        )
        if error is not None:
            return error
        stdout, stderr = result or ("", "")
        data = _git_output_data(
            success=True,
            stdout=stdout,
            stderr=stderr,
            extra={"action": action_value, "name": tag_name, "remote": remote_value},
        )
        if action_value == "list":
            tags = [line.strip() for line in stdout.splitlines() if line.strip()]
            data["tags"] = tags
            data["count"] = len(tags)
        return SuccessResult(data=cast(Dict[str, Any], data))


class GitMergeCommand(GitWorktreeCommand):
    """Merge a ref into the current branch."""

    name = "git_merge"
    version = "1.0.0"
    descr = "Merge a branch or ref into the current branch."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_merge"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID. Use list_projects to discover valid values.",
                },
                "ref": {
                    "type": "string",
                    "description": "Branch or commit-ish to merge.",
                },
                "no_ff": {
                    "type": "boolean",
                    "default": False,
                    "description": "Create a merge commit even when fast-forward is possible.",
                },
                "ff_only": {
                    "type": "boolean",
                    "default": False,
                    "description": "Fail unless the merge can fast-forward.",
                },
                "squash": {
                    "type": "boolean",
                    "default": False,
                    "description": "Squash changes into the index without a merge commit.",
                },
                "commit": {
                    "type": "boolean",
                    "default": True,
                    "description": "Allow git to create a merge commit.",
                },
                "message": {
                    "type": "string",
                    "description": "Optional merge commit message passed with -m.",
                },
                "abort": {
                    "type": "boolean",
                    "default": False,
                    "description": "Run git merge --abort.",
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_merge."""
        return get_git_merge_metadata(cls)

    async def execute(
        self,
        project_id: str,
        ref: Optional[str] = None,
        no_ff: bool = False,
        ff_only: bool = False,
        squash: bool = False,
        commit: bool = True,
        message: Optional[str] = None,
        abort: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_merge command."""
        _ = kwargs
        if abort:
            args = ["merge", "--abort"]
        else:
            ref_value = (ref or "").strip()
            if not ref_value:
                return validation_error("ref is required unless abort=true", "ref")
            if ff_only and (no_ff or squash or not commit):
                return validation_error(
                    "ff_only cannot be combined with no_ff, squash, or commit=false",
                    "ff_only",
                )
            args = ["merge"]
            if no_ff:
                args.append("--no-ff")
            if ff_only:
                args.append("--ff-only")
            if squash:
                args.append("--squash")
            if not commit:
                args.append("--no-commit")
            if message and message.strip():
                args.extend(["-m", message])
            args.append(ref_value)
        result, error = self._run_local_git(
            project_id,
            args,
            error_code="GIT_MERGE_FAILED",
            action="git merge",
            details={"ref": ref, "abort": abort},
        )
        if error is not None:
            return error
        stdout, stderr = result or ("", "")
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                _git_output_data(
                    success=True,
                    stdout=stdout,
                    stderr=stderr,
                    extra={"ref": ref, "abort": abort},
                ),
            )
        )


class GitCherryPickCommand(GitWorktreeCommand):
    """Cherry-pick commits onto the current branch."""

    name = "git_cherry_pick"
    version = "1.0.0"
    descr = "Cherry-pick commits onto the current branch."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_cherry_pick"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID. Use list_projects to discover valid values.",
                },
                "commits": {
                    "type": "array",
                    "description": "Commit refs to cherry-pick in order.",
                    "items": {"type": "string"},
                },
                "no_commit": {
                    "type": "boolean",
                    "default": False,
                    "description": "Apply changes without committing.",
                },
                "abort": {
                    "type": "boolean",
                    "default": False,
                    "description": "Abort an in-progress cherry-pick.",
                },
                "continue_pick": {
                    "type": "boolean",
                    "default": False,
                    "description": "Continue an in-progress cherry-pick.",
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_cherry_pick."""
        return get_git_cherry_pick_metadata(cls)

    async def execute(
        self,
        project_id: str,
        commits: Optional[List[str]] = None,
        no_commit: bool = False,
        abort: bool = False,
        continue_pick: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_cherry_pick command."""
        _ = kwargs
        if abort and continue_pick:
            return validation_error(
                "abort and continue_pick are mutually exclusive",
                "abort",
            )
        commit_refs = string_list(commits)
        args = ["cherry-pick"]
        if abort:
            args.append("--abort")
        elif continue_pick:
            args.append("--continue")
        else:
            if not commit_refs:
                return validation_error(
                    "commits is required unless abort or continue_pick is true",
                    "commits",
                )
            if no_commit:
                args.append("--no-commit")
            args.extend(commit_refs)
        result, error = self._run_local_git(
            project_id,
            args,
            error_code="GIT_CHERRY_PICK_FAILED",
            action="git cherry-pick",
            details={
                "commits": commit_refs,
                "abort": abort,
                "continue_pick": continue_pick,
            },
        )
        if error is not None:
            return error
        stdout, stderr = result or ("", "")
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                _git_output_data(
                    success=True,
                    stdout=stdout,
                    stderr=stderr,
                    extra={
                        "commits": commit_refs,
                        "no_commit": no_commit,
                        "abort": abort,
                        "continue_pick": continue_pick,
                    },
                ),
            )
        )


class GitRevertCommand(GitWorktreeCommand):
    """Revert commits by creating inverse changes."""

    name = "git_revert"
    version = "1.0.0"
    descr = "Revert commits by creating inverse changes or commits."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_revert"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID. Use list_projects to discover valid values.",
                },
                "commits": {
                    "type": "array",
                    "description": "Commit refs to revert in order.",
                    "items": {"type": "string"},
                },
                "no_commit": {
                    "type": "boolean",
                    "default": False,
                    "description": "Apply inverse changes without committing.",
                },
                "mainline": {
                    "type": "integer",
                    "description": "Parent number for reverting a merge commit.",
                },
                "abort": {
                    "type": "boolean",
                    "default": False,
                    "description": "Abort an in-progress revert.",
                },
                "continue_revert": {
                    "type": "boolean",
                    "default": False,
                    "description": "Continue an in-progress revert.",
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_revert."""
        return get_git_revert_metadata(cls)

    async def execute(
        self,
        project_id: str,
        commits: Optional[List[str]] = None,
        no_commit: bool = False,
        mainline: Optional[int] = None,
        abort: bool = False,
        continue_revert: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_revert command."""
        _ = kwargs
        if abort and continue_revert:
            return validation_error(
                "abort and continue_revert are mutually exclusive",
                "abort",
            )
        if mainline is not None and mainline < 1:
            return validation_error("mainline must be a positive integer", "mainline")
        commit_refs = string_list(commits)
        args = ["revert"]
        if abort:
            args.append("--abort")
        elif continue_revert:
            args.append("--continue")
        else:
            if not commit_refs:
                return validation_error(
                    "commits is required unless abort or continue_revert is true",
                    "commits",
                )
            if no_commit:
                args.append("--no-commit")
            if mainline is not None:
                args.extend(["-m", str(mainline)])
            args.extend(commit_refs)
        result, error = self._run_local_git(
            project_id,
            args,
            error_code="GIT_REVERT_FAILED",
            action="git revert",
            details={
                "commits": commit_refs,
                "abort": abort,
                "continue_revert": continue_revert,
            },
        )
        if error is not None:
            return error
        stdout, stderr = result or ("", "")
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                _git_output_data(
                    success=True,
                    stdout=stdout,
                    stderr=stderr,
                    extra={
                        "commits": commit_refs,
                        "no_commit": no_commit,
                        "mainline": mainline,
                        "abort": abort,
                        "continue_revert": continue_revert,
                    },
                ),
            )
        )


class GitRebaseCommand(GitWorktreeCommand):
    """Rebase the current or selected branch onto another base."""

    name = "git_rebase"
    version = "1.0.0"
    descr = "Rebase the current or selected branch onto another base."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_rebase"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID. Use list_projects to discover valid values.",
                },
                "upstream": {
                    "type": "string",
                    "description": "Upstream/base ref to replay the branch onto.",
                },
                "branch": {
                    "type": "string",
                    "description": "Optional branch to rebase instead of current branch.",
                },
                "onto": {
                    "type": "string",
                    "description": "Optional new base passed as --onto.",
                },
                "autostash": {
                    "type": "boolean",
                    "default": False,
                    "description": "Automatically stash and re-apply local changes.",
                },
                "abort": {
                    "type": "boolean",
                    "default": False,
                    "description": "Abort an in-progress rebase.",
                },
                "continue_rebase": {
                    "type": "boolean",
                    "default": False,
                    "description": "Continue an in-progress rebase.",
                },
                "skip": {
                    "type": "boolean",
                    "default": False,
                    "description": "Skip the current patch in an in-progress rebase.",
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_rebase."""
        return get_git_rebase_metadata(cls)

    async def execute(
        self,
        project_id: str,
        upstream: Optional[str] = None,
        branch: Optional[str] = None,
        onto: Optional[str] = None,
        autostash: bool = False,
        abort: bool = False,
        continue_rebase: bool = False,
        skip: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_rebase command."""
        _ = kwargs
        recovery_count = sum(1 for item in (abort, continue_rebase, skip) if item)
        if recovery_count > 1:
            return validation_error(
                "Choose only one rebase recovery action",
                "abort",
            )
        args = ["rebase"]
        if abort:
            args.append("--abort")
        elif continue_rebase:
            args.append("--continue")
        elif skip:
            args.append("--skip")
        else:
            upstream_value = (upstream or "").strip()
            branch_value = (branch or "").strip()
            onto_value = (onto or "").strip()
            if not upstream_value:
                return validation_error(
                    "upstream is required unless a recovery action is selected",
                    "upstream",
                )
            if autostash:
                args.append("--autostash")
            if onto_value:
                args.extend(["--onto", onto_value])
            args.append(upstream_value)
            if branch_value:
                args.append(branch_value)
        result, error = self._run_local_git(
            project_id,
            args,
            error_code="GIT_REBASE_FAILED",
            action="git rebase",
            details={
                "upstream": upstream,
                "branch": branch,
                "onto": onto,
                "abort": abort,
                "continue_rebase": continue_rebase,
                "skip": skip,
            },
        )
        if error is not None:
            return error
        stdout, stderr = result or ("", "")
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                _git_output_data(
                    success=True,
                    stdout=stdout,
                    stderr=stderr,
                    extra={
                        "upstream": upstream,
                        "branch": branch,
                        "onto": onto,
                        "autostash": autostash,
                        "abort": abort,
                        "continue_rebase": continue_rebase,
                        "skip": skip,
                    },
                ),
            )
        )
