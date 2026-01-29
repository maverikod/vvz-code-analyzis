# Project Management Commands — Detailed Descriptions

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

All MCP commands in `commands/project_management_mcp_commands.py`. Internal logic: `CreateProjectCommand` in `project_creation.py`, `DeleteProjectCommand` / `DeleteUnwatchedProjectsCommand` in `project_deletion.py`. Schema from `get_schema()`; metadata from `metadata()`.

---

## change_project_id — ChangeProjectIdMCPCommand

**Description:** Change project UUID for an existing project (e.g. after cloning or fixing id).

**Behavior:** Accepts root_dir (or project_id) and new project_id; updates DB and related records to use new id; validates UUID format and uniqueness.

---

## create_project — CreateProjectMCPCommand

**Description:** Register a new project. If project already exists (same root), returns existing info; may update watch_dir.

**Behavior:** Validates root_dir, ensures projectid file if required, creates project and dataset in DB, optionally registers watch dir; returns project_id and metadata.

---

## delete_project — DeleteProjectMCPCommand

**Description:** Remove project and its data (files, AST, CST, chunks, etc.) from the database.

**Behavior:** Accepts project_id or root_dir; deletes project and cascaded data; does not delete files on disk unless explicitly requested (if supported).

---

## delete_unwatched_projects — DeleteUnwatchedProjectsMCPCommand

**Description:** Delete projects that are no longer under any watch directory (orphaned registrations).

**Behavior:** Finds projects whose root is not in any active watch dir and removes them (with same cascade as delete_project).

---

## list_projects — ListProjectsMCPCommand

**Description:** List all registered projects with metadata.

**Behavior:** Returns list of projects (project_id, root_dir, watch_dir_id, created_at, etc.) from DB.
