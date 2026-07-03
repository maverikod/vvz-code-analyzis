"""Administrative git repository maintenance MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import grp
import pwd
import stat
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.git_worktree_base import (
    LOCAL_GIT_TIMEOUT_SECONDS,
    GitWorktreeCommand,
    validation_error,
)
from code_analysis.core.git_remote_ops import (
    GIT_REMOTE_NOT_CONFIGURED,
    GIT_REMOTE_TIMEOUT,
    build_full_subprocess_env,
    git_remote_error_result,
    load_git_remote_config,
    run_git_subprocess,
)
from code_analysis.core.git_ssh_auth import GIT_AUTH_FAILED, classify_ssh_auth_stderr


SCOPE_VALUES = ["git_only", "worktree", "all"]
GIT_ADMIN_TIMEOUT_SECONDS = 60.0


def _user_name(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def _group_name(gid: int) -> str:
    try:
        return grp.getgrgid(gid).gr_name
    except KeyError:
        return str(gid)


def _uid_for(name: Optional[str]) -> int:
    if not name:
        return os.geteuid()
    try:
        return pwd.getpwnam(name).pw_uid
    except KeyError as exc:
        raise ValueError(f"Unknown user: {name}") from exc


def _gid_for(name: Optional[str]) -> int:
    if not name:
        return os.getegid()
    try:
        return grp.getgrnam(name).gr_gid
    except KeyError as exc:
        raise ValueError(f"Unknown group: {name}") from exc


def _scope_roots(root: Path, scope: str) -> List[Path]:
    git_dir = root / ".git"
    if scope == "git_only":
        return [git_dir]
    if scope == "worktree":
        return [root]
    return [root]


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _iter_paths(root: Path, scope: str) -> Iterable[Path]:
    for base in _scope_roots(root, scope):
        if not base.exists():
            continue
        yield base
        for current, dirs, files in os.walk(base):
            current_path = Path(current)
            if scope == "worktree" and current_path == root:
                dirs[:] = [item for item in dirs if item != ".git"]
            for dirname in dirs:
                yield current_path / dirname
            for filename in files:
                yield current_path / filename


def _path_entry(root: Path, path: Path, expected_uid: int, expected_gid: int) -> Dict[str, Any]:
    st = path.lstat()
    issues: List[str] = []
    if st.st_uid != expected_uid:
        issues.append("owner_mismatch")
    if st.st_gid != expected_gid:
        issues.append("group_mismatch")
    if not os.access(path, os.W_OK):
        issues.append("not_writable_by_service")
    if path.is_dir() and not os.access(path, os.X_OK):
        issues.append("not_searchable_by_service")
    return {
        "path": _relative(root, path),
        "owner": _user_name(st.st_uid),
        "group": _group_name(st.st_gid),
        "uid": st.st_uid,
        "gid": st.st_gid,
        "mode": oct(stat.S_IMODE(st.st_mode)),
        "kind": "dir" if path.is_dir() else "file",
        "issues": issues,
    }


def _write_probe(directory: Path) -> Dict[str, Any]:
    probe = directory / f".casmgr-write-probe-{os.getpid()}-{int(time.time() * 1000)}"
    try:
        probe.write_text("probe\n", encoding="utf-8")
        probe.unlink()
        return {"path": str(directory), "writable": True, "error": None}
    except OSError as exc:
        try:
            if probe.exists():
                probe.unlink()
        except OSError:
            pass
        return {"path": str(directory), "writable": False, "error": str(exc)}


def _collect_permission_report(
    root: Path,
    *,
    scope: str,
    expected_uid: int,
    expected_gid: int,
    max_entries: int,
    include_ok: bool,
) -> Dict[str, Any]:
    checked = 0
    problem_count = 0
    problems: List[Dict[str, Any]] = []
    ok_entries: List[Dict[str, Any]] = []
    for path in _iter_paths(root, scope):
        checked += 1
        entry = _path_entry(root, path, expected_uid, expected_gid)
        if entry["issues"]:
            problem_count += 1
            if len(problems) < max_entries:
                problems.append(entry)
        elif include_ok and len(ok_entries) < max_entries:
            ok_entries.append(entry)
    probes = [
        _write_probe(root),
        _write_probe(root / ".git" / "objects") if (root / ".git" / "objects").is_dir() else None,
    ]
    return {
        "checked_count": checked,
        "problem_count": problem_count,
        "problems": problems,
        "ok_entries": ok_entries,
        "write_probes": [item for item in probes if item is not None],
        "clean": not problems and all(item is not None and item["writable"] for item in probes),
    }


def _run_git(
    root: Path,
    args: List[str],
    timeout: float = LOCAL_GIT_TIMEOUT_SECONDS,
) -> Tuple[int, str, str, bool]:
    return run_git_subprocess(
        ["git", *args],
        cwd=root,
        env=None,
        timeout_seconds=timeout,
    )


def _status_snapshot(root: Path) -> Dict[str, Any]:
    branch_rc, branch_out, branch_err, branch_timeout = _run_git(
        root, ["status", "--porcelain=2", "--branch"]
    )
    stash_rc, stash_out, stash_err, stash_timeout = _run_git(root, ["stash", "list"])
    return {
        "status": {
            "returncode": branch_rc,
            "stdout": branch_out.strip(),
            "stderr": branch_err.strip(),
            "timed_out": branch_timeout,
        },
        "stash": {
            "returncode": stash_rc,
            "stdout": stash_out.strip(),
            "stderr": stash_err.strip(),
            "timed_out": stash_timeout,
        },
    }


def _metadata(
    name: str,
    description: str,
    detailed_description: str,
    parameters: Dict[str, Any],
    return_value: Dict[str, Any],
    usage_examples: List[Dict[str, Any]],
    error_cases: Dict[str, Any],
    best_practices: List[str],
) -> Dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "version": "1.0.0",
        "category": "git",
        "author": "Vasiliy Zdanovskiy",
        "email": "vasilyvz@gmail.com",
        "detailed_description": detailed_description,
        "parameters": parameters,
        "return_value": return_value,
        "usage_examples": usage_examples,
        "error_cases": error_cases,
        "best_practices": best_practices,
    }


def _project_param(required: bool = True) -> Dict[str, Any]:
    return {
        "description": "Project UUID. Use list_projects to discover valid values.",
        "type": "string",
        "required": required,
    }


def _scope_param() -> Dict[str, Any]:
    return {
        "description": "Repository area to inspect or repair.",
        "type": "string",
        "required": False,
        "default": "all",
        "enum": SCOPE_VALUES,
    }


def _standard_errors() -> Dict[str, Any]:
    return {
        "PROJECT_NOT_FOUND": {
            "description": "project_id does not resolve to a registered project.",
            "solution": "Call list_projects and use a returned project id.",
        },
        "GIT_NOT_AVAILABLE": {
            "description": "git executable is not available to the server process.",
            "solution": "Install git or fix PATH for the service process.",
        },
        "GIT_NOT_A_REPO": {
            "description": "The project root is not a git repository.",
            "solution": "Verify project_id and repository registration.",
        },
        "VALIDATION_ERROR": {
            "description": "A parameter failed validation or a destructive operation was not confirmed.",
            "solution": "Fix parameters per schema and retry.",
        },
    }


class GitRepoPermissionsCheckCommand(GitWorktreeCommand):
    """Inspect ownership, modes, and writeability of a project git repository."""

    name = "git_repo_permissions_check"
    version = "1.0.0"
    descr = "Check git repository ownership, modes, and service writeability."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        return "git_repo_permissions_check"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project UUID."},
                "scope": {
                    "type": "string",
                    "enum": SCOPE_VALUES,
                    "default": "all",
                    "description": "Area to check: .git only, worktree only, or all.",
                },
                "expected_user": {
                    "type": "string",
                    "description": "Expected owner user. Defaults to the CAS process user.",
                },
                "expected_group": {
                    "type": "string",
                    "description": "Expected owner group. Defaults to the CAS process group.",
                },
                "max_entries": {
                    "type": "integer",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 1000,
                    "description": "Maximum problem entries to return.",
                },
                "include_ok": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include a sample of entries without issues.",
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["GitRepoPermissionsCheckCommand"]) -> Dict[str, Any]:
        return _metadata(
            cls.name,
            cls.descr,
            "Inspect repository ownership, group, file modes, and effective write access "
            "from the CAS process. The command checks .git, the working tree, or both, "
            "and performs write probes in the project root and .git/objects. It is read-only "
            "except for temporary probe files that are immediately removed.",
            {
                "project_id": _project_param(),
                "scope": _scope_param(),
                "expected_user": {
                    "description": "Expected owner user; defaults to the running CAS user.",
                    "type": "string",
                    "required": False,
                },
                "expected_group": {
                    "description": "Expected owner group; defaults to the running CAS group.",
                    "type": "string",
                    "required": False,
                },
                "max_entries": {
                    "description": "Maximum number of problem rows returned.",
                    "type": "integer",
                    "required": False,
                    "default": 100,
                },
                "include_ok": {
                    "description": "Return a small sample of healthy entries.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
            },
            {
                "success": {
                    "description": "Permission report was produced.",
                    "data": {
                        "clean": "True when no mismatches and all write probes succeed.",
                        "effective_user": "User running the CAS process.",
                        "expected_user": "Owner expected by the check.",
                        "problems": "Entries with owner/group/mode/writeability issues.",
                        "write_probes": "Root and .git/objects write-test results.",
                    },
                },
                "error": {"description": "Validation, project, or git availability failure."},
            },
            [
                {
                    "description": "Check the whole repository for CAS write access",
                    "command": {"project_id": "<uuid>"},
                    "explanation": "Returns mismatched owners and failing write probes.",
                },
                {
                    "description": "Check only .git before stash/pull",
                    "command": {"project_id": "<uuid>", "scope": "git_only"},
                    "explanation": "Focuses on refs, logs, objects, and lock-file writeability.",
                },
            ],
            _standard_errors(),
            [
                "Run before git_stash_push, git_pull, and git_commit when permissions are suspect.",
                "Use expected_user/expected_group only when the service account is known.",
                "Keep max_entries bounded on large repositories.",
            ],
        )

    async def execute(
        self,
        project_id: str,
        scope: str = "all",
        expected_user: Optional[str] = None,
        expected_group: Optional[str] = None,
        max_entries: int = 100,
        include_ok: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = kwargs
        if scope not in SCOPE_VALUES:
            return validation_error(
                "scope must be one of git_only, worktree, all",
                "scope",
            )
        try:
            expected_uid = _uid_for(expected_user)
            expected_gid = _gid_for(expected_group)
        except ValueError as exc:
            return validation_error(str(exc), "expected_user")
        root, error = self._resolve_git_root_or_error(project_id)
        if error is not None:
            return error
        report = _collect_permission_report(
            cast(Path, root),
            scope=scope,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            max_entries=max_entries,
            include_ok=include_ok,
        )
        report.update(
            {
                "success": True,
                "scope": scope,
                "project_id": project_id,
                "root": str(root),
                "effective_user": _user_name(os.geteuid()),
                "effective_group": _group_name(os.getegid()),
                "expected_user": _user_name(expected_uid),
                "expected_group": _group_name(expected_gid),
            }
        )
        return SuccessResult(data=cast(Dict[str, Any], report))


class GitRepoPermissionsRepairCommand(GitWorktreeCommand):
    """Repair ownership and mode bits for a project git repository."""

    name = "git_repo_permissions_repair"
    version = "1.0.0"
    descr = "Repair git repository ownership and write permissions for the CAS process."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        return "git_repo_permissions_repair"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project UUID."},
                "scope": {
                    "type": "string",
                    "enum": SCOPE_VALUES,
                    "default": "all",
                    "description": "Area to repair.",
                },
                "expected_user": {
                    "type": "string",
                    "description": "Owner user to set. Defaults to the CAS process user.",
                },
                "expected_group": {
                    "type": "string",
                    "description": "Owner group to set. Defaults to the CAS process group.",
                },
                "directory_mode": {
                    "type": "string",
                    "default": "775",
                    "description": "Octal mode for directories, for example 775.",
                },
                "file_mode": {
                    "type": "string",
                    "default": "664",
                    "description": "Octal mode for files, for example 664.",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": True,
                    "description": "Report actions without changing files.",
                },
                "confirm_repair": {
                    "type": "boolean",
                    "default": False,
                    "description": "Required true when dry_run=false.",
                },
                "max_entries": {
                    "type": "integer",
                    "default": 200,
                    "minimum": 1,
                    "maximum": 5000,
                    "description": "Maximum action/error rows to return.",
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["GitRepoPermissionsRepairCommand"]) -> Dict[str, Any]:
        errors = _standard_errors()
        errors["PERMISSION_REPAIR_FAILED"] = {
            "description": "chmod/chown failed for one or more paths.",
            "solution": "Run with sufficient service privileges or repair through an approved host command.",
        }
        return _metadata(
            cls.name,
            cls.descr,
            "Repair owner, group, and write/search modes for .git, the working tree, or both. "
            "The command is intentionally guarded: dry_run defaults to true, and actual repair "
            "requires confirm_repair=true. It can fix files the CAS process is allowed to change; "
            "root-owned files may still require a host-level command.",
            {
                "project_id": _project_param(),
                "scope": _scope_param(),
                "expected_user": {
                    "description": "Owner to set; defaults to the running CAS user.",
                    "type": "string",
                    "required": False,
                },
                "expected_group": {
                    "description": "Group to set; defaults to the running CAS group.",
                    "type": "string",
                    "required": False,
                },
                "directory_mode": {
                    "description": "Octal directory mode, usually 775.",
                    "type": "string",
                    "required": False,
                    "default": "775",
                },
                "file_mode": {
                    "description": "Octal file mode, usually 664.",
                    "type": "string",
                    "required": False,
                    "default": "664",
                },
                "dry_run": {
                    "description": "Preview mode; no filesystem changes.",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "confirm_repair": {
                    "description": "Required true for actual repair.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "max_entries": {
                    "description": "Maximum action/error rows returned.",
                    "type": "integer",
                    "required": False,
                    "default": 200,
                },
            },
            {
                "success": {
                    "description": "Repair completed or dry-run plan was produced.",
                    "data": {
                        "changed_count": "Number of paths changed.",
                        "planned_count": "Number of paths that would change in dry-run.",
                        "errors": "Per-path chmod/chown failures.",
                    },
                },
                "error": {"description": "Validation, project, git, or permission failure."},
            },
            [
                {
                    "description": "Preview repair for all repository files",
                    "command": {"project_id": "<uuid>", "dry_run": True},
                    "explanation": "Shows planned chown/chmod operations.",
                },
                {
                    "description": "Repair .git only",
                    "command": {
                        "project_id": "<uuid>",
                        "scope": "git_only",
                        "dry_run": False,
                        "confirm_repair": True,
                    },
                    "explanation": "Fixes refs, logs, objects, and lock writeability where permitted.",
                },
            ],
            errors,
            [
                "Run dry_run first and inspect planned actions.",
                "Prefer scope=git_only when only stash/fetch/pull object writes are failing.",
                "Use scope=all when checkout/pull cannot unlink or rewrite tracked files.",
            ],
        )

    async def execute(
        self,
        project_id: str,
        scope: str = "all",
        expected_user: Optional[str] = None,
        expected_group: Optional[str] = None,
        directory_mode: str = "775",
        file_mode: str = "664",
        dry_run: bool = True,
        confirm_repair: bool = False,
        max_entries: int = 200,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = kwargs
        if scope not in SCOPE_VALUES:
            return validation_error(
                "scope must be one of git_only, worktree, all",
                "scope",
            )
        if not dry_run and not confirm_repair:
            return validation_error(
                "confirm_repair=true is required when dry_run=false",
                "confirm_repair",
            )
        try:
            expected_uid = _uid_for(expected_user)
            expected_gid = _gid_for(expected_group)
            dir_mode = int(directory_mode, 8)
            regular_mode = int(file_mode, 8)
        except ValueError as exc:
            return validation_error(str(exc), "mode")
        root, error = self._resolve_git_root_or_error(project_id)
        if error is not None:
            return error
        actions: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        changed_count = 0
        planned_count = 0
        for path in _iter_paths(cast(Path, root), scope):
            if path.is_symlink():
                continue
            entry = _path_entry(cast(Path, root), path, expected_uid, expected_gid)
            target_mode = dir_mode if path.is_dir() else regular_mode
            needs_mode = stat.S_IMODE(path.lstat().st_mode) != target_mode
            needs_owner = entry["uid"] != expected_uid or entry["gid"] != expected_gid
            if not needs_mode and not needs_owner:
                continue
            planned_count += 1
            if len(actions) < max_entries:
                actions.append(
                    {
                        "path": entry["path"],
                        "from_owner": entry["owner"],
                        "from_group": entry["group"],
                        "from_mode": entry["mode"],
                        "to_owner": _user_name(expected_uid),
                        "to_group": _group_name(expected_gid),
                        "to_mode": oct(target_mode),
                    }
                )
            if dry_run:
                continue
            try:
                if needs_owner:
                    os.chown(path, expected_uid, expected_gid, follow_symlinks=False)
                if needs_mode:
                    os.chmod(path, target_mode, follow_symlinks=False)
                changed_count += 1
            except OSError as exc:
                if len(errors) < max_entries:
                    errors.append({"path": entry["path"], "error": str(exc)})
        payload = {
            "success": not errors,
            "dry_run": dry_run,
            "scope": scope,
            "project_id": project_id,
            "root": str(root),
            "planned_count": planned_count,
            "changed_count": changed_count,
            "actions": actions,
            "errors": errors,
        }
        if errors:
            return git_remote_error_result(
                "PERMISSION_REPAIR_FAILED",
                "One or more permission repair operations failed",
                payload,
            )
        return SuccessResult(data=cast(Dict[str, Any], payload))


class GitRepoDoctorCommand(GitWorktreeCommand):
    """Run a combined repository health report for MCP git workflows."""

    name = "git_repo_doctor"
    version = "1.0.0"
    descr = "Run repository diagnostics for status, stash, locks, permissions, and write probes."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        return "git_repo_doctor"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project UUID."},
                "scope": {
                    "type": "string",
                    "enum": SCOPE_VALUES,
                    "default": "all",
                    "description": "Area to check for permissions.",
                },
                "max_entries": {
                    "type": "integer",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 1000,
                    "description": "Maximum rows per diagnostic section.",
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["GitRepoDoctorCommand"]) -> Dict[str, Any]:
        return _metadata(
            cls.name,
            cls.descr,
            "Produce one operational report for repository automation: git status, stash list, "
            "branch/ahead/behind text, stale lock candidates, ownership/mode problems, and write probes. "
            "Use this before destructive or multi-step workflows such as safe pull.",
            {
                "project_id": _project_param(),
                "scope": _scope_param(),
                "max_entries": {
                    "description": "Maximum diagnostic rows per section.",
                    "type": "integer",
                    "required": False,
                    "default": 100,
                },
            },
            {
                "success": {
                    "description": "Doctor report was produced.",
                    "data": {
                        "healthy": "True when status commands, permissions, probes, and locks are OK.",
                        "status": "git status --porcelain=2 --branch output.",
                        "stash": "git stash list output.",
                        "permissions": "Embedded git_repo_permissions_check-style report.",
                        "locks": "Lock file candidates under .git.",
                    },
                },
                "error": {"description": "Project or git availability failure."},
            },
            [
                {
                    "description": "Check whether a repo is ready for pull",
                    "command": {"project_id": "<uuid>"},
                    "explanation": "Returns status, stash, lock, and permission diagnostics.",
                }
            ],
            _standard_errors(),
            [
                "Run doctor before safe_pull when a previous git operation failed.",
                "Use the embedded permission report to decide whether repair is required.",
            ],
        )

    async def execute(
        self,
        project_id: str,
        scope: str = "all",
        max_entries: int = 100,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = kwargs
        if scope not in SCOPE_VALUES:
            return validation_error(
                "scope must be one of git_only, worktree, all",
                "scope",
            )
        root, error = self._resolve_git_root_or_error(project_id)
        if error is not None:
            return error
        expected_uid = os.geteuid()
        expected_gid = os.getegid()
        permissions = _collect_permission_report(
            cast(Path, root),
            scope=scope,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            max_entries=max_entries,
            include_ok=False,
        )
        locks = [
            {"path": _relative(cast(Path, root), path), "age_seconds": time.time() - path.stat().st_mtime}
            for path in (cast(Path, root) / ".git").rglob("*.lock")
        ][:max_entries]
        snapshot = _status_snapshot(cast(Path, root))
        healthy = permissions["clean"] and not locks and snapshot["status"]["returncode"] == 0
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                {
                    "success": True,
                    "healthy": healthy,
                    "project_id": project_id,
                    "root": str(root),
                    "effective_user": _user_name(os.geteuid()),
                    "effective_group": _group_name(os.getegid()),
                    "status": snapshot["status"],
                    "stash": snapshot["stash"],
                    "permissions": permissions,
                    "locks": locks,
                },
            )
        )


class GitRepoLockCleanupCommand(GitWorktreeCommand):
    """Remove stale git lock files after explicit confirmation."""

    name = "git_repo_lock_cleanup"
    version = "1.0.0"
    descr = "List or remove stale .git lock files with explicit confirmation."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        return "git_repo_lock_cleanup"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project UUID."},
                "min_age_seconds": {
                    "type": "integer",
                    "default": 300,
                    "minimum": 0,
                    "description": "Only locks older than this are stale candidates.",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": True,
                    "description": "List stale locks without deleting.",
                },
                "confirm_cleanup": {
                    "type": "boolean",
                    "default": False,
                    "description": "Required true when dry_run=false.",
                },
                "max_entries": {
                    "type": "integer",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 1000,
                    "description": "Maximum lock rows returned.",
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["GitRepoLockCleanupCommand"]) -> Dict[str, Any]:
        errors = _standard_errors()
        errors["LOCK_CLEANUP_FAILED"] = {
            "description": "One or more stale lock files could not be removed.",
            "solution": "Check permissions and whether another git process is still active.",
        }
        return _metadata(
            cls.name,
            cls.descr,
            "Find .git lock files such as index.lock and refs/*.lock and optionally remove "
            "only those older than min_age_seconds. Actual deletion is destructive and requires "
            "confirm_cleanup=true.",
            {
                "project_id": _project_param(),
                "min_age_seconds": {
                    "description": "Minimum age for a lock to be considered stale.",
                    "type": "integer",
                    "required": False,
                    "default": 300,
                },
                "dry_run": {
                    "description": "Preview mode; no deletion.",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "confirm_cleanup": {
                    "description": "Required true for deletion.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "max_entries": {
                    "description": "Maximum lock rows returned.",
                    "type": "integer",
                    "required": False,
                    "default": 100,
                },
            },
            {
                "success": {
                    "description": "Lock scan or cleanup completed.",
                    "data": {
                        "locks": "Candidate lock files.",
                        "removed_count": "Number removed when dry_run=false.",
                    },
                },
                "error": {"description": "Validation or removal failure."},
            },
            [
                {
                    "description": "Preview stale locks",
                    "command": {"project_id": "<uuid>", "dry_run": True},
                    "explanation": "Lists lock files older than five minutes.",
                },
                {
                    "description": "Delete stale locks",
                    "command": {
                        "project_id": "<uuid>",
                        "dry_run": False,
                        "confirm_cleanup": True,
                    },
                    "explanation": "Removes only stale lock candidates.",
                },
            ],
            errors,
            [
                "Use dry_run first.",
                "Do not set min_age_seconds=0 unless you know no git process is active.",
                "Run git_repo_doctor again after cleanup.",
            ],
        )

    async def execute(
        self,
        project_id: str,
        min_age_seconds: int = 300,
        dry_run: bool = True,
        confirm_cleanup: bool = False,
        max_entries: int = 100,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = kwargs
        if not dry_run and not confirm_cleanup:
            return validation_error(
                "confirm_cleanup=true is required when dry_run=false",
                "confirm_cleanup",
            )
        root, error = self._resolve_git_root_or_error(project_id)
        if error is not None:
            return error
        now = time.time()
        locks: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        removed_count = 0
        for path in (cast(Path, root) / ".git").rglob("*.lock"):
            age = now - path.stat().st_mtime
            if age < min_age_seconds:
                continue
            lock = {"path": _relative(cast(Path, root), path), "age_seconds": age}
            if len(locks) < max_entries:
                locks.append(lock)
            if dry_run:
                continue
            try:
                path.unlink()
                removed_count += 1
            except OSError as exc:
                if len(errors) < max_entries:
                    errors.append({"path": lock["path"], "error": str(exc)})
        payload = {
            "success": not errors,
            "dry_run": dry_run,
            "project_id": project_id,
            "root": str(root),
            "locks": locks,
            "removed_count": removed_count,
            "errors": errors,
        }
        if errors:
            return git_remote_error_result("LOCK_CLEANUP_FAILED", "Some stale locks were not removed", payload)
        return SuccessResult(data=cast(Dict[str, Any], payload))


class GitPullSafeCommand(GitWorktreeCommand):
    """Safely pull remote changes using diagnostics and temporary stash."""

    name = "git_pull_safe"
    version = "1.0.0"
    descr = "Run a guarded stash/pull/apply/drop workflow with diagnostics."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        return "git_pull_safe"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project UUID."},
                "remote": {"type": "string", "default": "origin", "description": "Remote name."},
                "ref": {"type": "string", "description": "Remote branch/ref to pull."},
                "rebase": {"type": "boolean", "default": False, "description": "Use git pull --rebase."},
                "include_untracked": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include untracked files in the temporary stash.",
                },
                "apply_stash": {
                    "type": "boolean",
                    "default": True,
                    "description": "Apply the temporary stash after successful pull.",
                },
                "drop_stash_after_apply": {
                    "type": "boolean",
                    "default": False,
                    "description": "Drop the temporary stash after successful apply.",
                },
                "stash_message": {
                    "type": "string",
                    "description": "Custom stash message.",
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["GitPullSafeCommand"]) -> Dict[str, Any]:
        errors = _standard_errors()
        errors["SAFE_PULL_FAILED"] = {
            "description": "One step of the safe pull workflow failed.",
            "solution": "Read steps; use git_repo_doctor and stash commands to recover.",
        }
        return _metadata(
            cls.name,
            cls.descr,
            "High-level pull workflow for agents: capture a preflight status, stash dirty work "
            "when needed, run git pull with remote auth config, optionally apply the stash, and "
            "optionally drop it after a clean apply. The response is a step-by-step audit trail. "
            "It does not repair permissions automatically; run git_repo_permissions_check/repair first.",
            {
                "project_id": _project_param(),
                "remote": {
                    "description": "Remote name.",
                    "type": "string",
                    "required": False,
                    "default": "origin",
                },
                "ref": {
                    "description": "Remote branch/ref to pull.",
                    "type": "string",
                    "required": False,
                },
                "rebase": {
                    "description": "Use git pull --rebase instead of --ff-only.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "include_untracked": {
                    "description": "Include untracked files in the temporary stash.",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "apply_stash": {
                    "description": "Apply the temporary stash after pull.",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "drop_stash_after_apply": {
                    "description": "Drop the temporary stash after successful apply.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "stash_message": {
                    "description": "Custom stash message.",
                    "type": "string",
                    "required": False,
                },
            },
            {
                "success": {
                    "description": "Workflow completed.",
                    "data": {
                        "steps": "Ordered audit entries for status, stash, pull, apply, drop.",
                        "stash_ref": "Temporary stash reference when one was created.",
                        "final_status": "Post-workflow git status snapshot.",
                    },
                },
                "error": {"description": "One workflow step failed; details include completed steps."},
            },
            [
                {
                    "description": "Pull origin/main with a safety stash",
                    "command": {"project_id": "<uuid>", "remote": "origin", "ref": "main"},
                    "explanation": "Stashes dirty work, fast-forwards, and reapplies the stash.",
                },
                {
                    "description": "Keep stash as an audit backup",
                    "command": {
                        "project_id": "<uuid>",
                        "remote": "origin",
                        "ref": "main",
                        "drop_stash_after_apply": False,
                    },
                    "explanation": "Leaves the temporary stash available after apply.",
                },
            ],
            errors,
            [
                "Run git_repo_doctor first if previous git operations failed.",
                "Keep drop_stash_after_apply=false for high-risk automated pulls.",
                "Use include_untracked=true when generated plan files or new tests may exist.",
            ],
        )

    async def execute(
        self,
        project_id: str,
        remote: str = "origin",
        ref: Optional[str] = None,
        rebase: bool = False,
        include_untracked: bool = True,
        apply_stash: bool = True,
        drop_stash_after_apply: bool = False,
        stash_message: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = kwargs
        root, error = self._resolve_git_root_or_error(project_id)
        if error is not None:
            return error
        config_data = self._get_raw_config()
        git_config = load_git_remote_config(config_data)
        if not git_config["remote_enabled"]:
            return git_remote_error_result(
                GIT_REMOTE_NOT_CONFIGURED,
                "Remote git operations are not enabled in configuration",
                {},
            )
        env, auth_error = build_full_subprocess_env(git_config)
        if auth_error is not None:
            return git_remote_error_result(
                GIT_AUTH_FAILED,
                str(auth_error.get("message", "SSH authentication is not configured correctly")),
                {},
            )
        steps: List[Dict[str, Any]] = []
        status_before = _status_snapshot(cast(Path, root))
        steps.append({"step": "status_before", "result": status_before})
        dirty = any(
            line and not line.startswith("# ")
            for line in status_before["status"]["stdout"].splitlines()
        )
        stash_ref: Optional[str] = None
        if dirty:
            message = stash_message or f"git_pull_safe {remote} {ref or ''}".strip()
            args = ["stash", "push", "-m", message]
            if include_untracked:
                args.append("--include-untracked")
            code, out, err, timed_out = _run_git(cast(Path, root), args)
            steps.append(
                {
                    "step": "stash_push",
                    "returncode": code,
                    "stdout": out.strip(),
                    "stderr": err.strip(),
                    "timed_out": timed_out,
                }
            )
            if timed_out or code != 0:
                return git_remote_error_result(
                    "SAFE_PULL_FAILED",
                    "Temporary stash failed before pull",
                    {"steps": steps},
                )
            stash_ref = "stash@{0}"
        pull_args = ["git", "pull", "--rebase" if rebase else "--ff-only", remote]
        if ref:
            pull_args.append(ref)
        code, out, err, timed_out = run_git_subprocess(
            pull_args,
            cwd=cast(Path, root),
            env=env,
            timeout_seconds=git_config["remote_timeout_seconds"],
        )
        steps.append(
            {
                "step": "pull",
                "returncode": code,
                "stdout": out.strip(),
                "stderr": err.strip(),
                "timed_out": timed_out,
            }
        )
        if timed_out:
            return git_remote_error_result(
                GIT_REMOTE_TIMEOUT,
                f"git pull exceeded timeout of {git_config['remote_timeout_seconds']} seconds",
                {"steps": steps, "stash_ref": stash_ref},
            )
        if code != 0:
            auth_code = classify_ssh_auth_stderr(err)
            return git_remote_error_result(
                auth_code if auth_code == GIT_AUTH_FAILED else "SAFE_PULL_FAILED",
                "git pull failed during safe pull",
                {"steps": steps, "stash_ref": stash_ref},
            )
        if stash_ref and apply_stash:
            code, out, err, timed_out = _run_git(cast(Path, root), ["stash", "apply", stash_ref])
            steps.append(
                {
                    "step": "stash_apply",
                    "returncode": code,
                    "stdout": out.strip(),
                    "stderr": err.strip(),
                    "timed_out": timed_out,
                }
            )
            if timed_out or code != 0:
                return git_remote_error_result(
                    "SAFE_PULL_FAILED",
                    "Temporary stash apply failed after pull; stash was retained",
                    {"steps": steps, "stash_ref": stash_ref},
                )
            if drop_stash_after_apply:
                code, out, err, timed_out = _run_git(cast(Path, root), ["stash", "drop", stash_ref])
                steps.append(
                    {
                        "step": "stash_drop",
                        "returncode": code,
                        "stdout": out.strip(),
                        "stderr": err.strip(),
                        "timed_out": timed_out,
                    }
                )
                if timed_out or code != 0:
                    return git_remote_error_result(
                        "SAFE_PULL_FAILED",
                        "Temporary stash drop failed after successful apply",
                        {"steps": steps, "stash_ref": stash_ref},
                    )
        final_status = _status_snapshot(cast(Path, root))
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                {
                    "success": True,
                    "remote": remote,
                    "ref": ref,
                    "rebase": rebase,
                    "stash_ref": stash_ref,
                    "stash_retained": bool(stash_ref and not drop_stash_after_apply),
                    "steps": steps,
                    "final_status": final_status,
                },
            )
        )
