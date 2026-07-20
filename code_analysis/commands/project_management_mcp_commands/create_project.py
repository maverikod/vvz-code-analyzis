"""
MCP command: create_project.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from ._shared import (
    Any,
    BaseMCPCommand,
    Dict,
    ErrorResult,
    List,
    Optional,
    SuccessResult,
    ValidationError,
    logger,
    uuid,
)


class CreateProjectMCPCommand(BaseMCPCommand):
    """
    Create or register a new project.

    This command:
    1. Validates that watched directory exists and does not contain projectid file
    2. Validates that project directory exists
    3. Checks if project is already registered in database
    4. Creates projectid file with UUID4 and description
    5. Registers project in database

    Returns project ID, whether project already existed, and description.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "create_project"

    version = "1.0.0"

    descr = (
        "Create or register a new project. "
        "Creates projectid file and registers project in database."
    )

    category = "project_management"

    author = "Vasiliy Zdanovskiy"

    email = "vasilyvz@gmail.com"

    use_queue = False

    @classmethod
    def get_schema(
        cls: type["CreateProjectMCPCommand"],
    ) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": (
                "Create a new project atomically. "
                "Default: creates project subdirectory in watch_dir, "
                "projectid file, and registers in DB. "
                "Optional use_existing_dir=true: for existing directory, "
                "create only projectid file and register. "
                "Optional create_venv=true (default): creates .venv. "
                "Optional apply_template=true (default): deploys "
                ".cursor/agents, docs/PROJECT_RULES.md, README.md, etc."
                " Creates or updates .gitignore with Python and code_analysis "
                "service artifacts before git initialization."
                " Git is initialized automatically in the project directory; "
                "git failures are returned as bootstrap warnings and do not "
                "roll back project creation."
            ),
            "properties": {
                "watch_dir_id": {
                    "type": "string",
                    "description": (
                        "Watch directory ID (UUID4) from watch_dirs table. "
                        "Must exist in database. Required."
                    ),
                },
                "project_name": {
                    "type": "string",
                    "description": (
                        "Name of project subdirectory to create in watch_dir. "
                        "Required. Must be a valid directory name."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable description of the project. Required.",
                },
                "project_id": {
                    "type": "string",
                    "description": (
                        "Optional project ID (UUID4). "
                        "If not provided, will be generated automatically."
                    ),
                },
                "use_existing_dir": {
                    "type": "boolean",
                    "description": (
                        "Optional. Default false. "
                        "If true: when project directory already exists, "
                        "create only projectid file and register."
                    ),
                    "default": False,
                },
                "create_venv": {
                    "type": "boolean",
                    "description": (
                        "Optional. Default true. "
                        "Create .venv virtual environment in the project "
                        "using python -m venv. "
                        "Python and pip availability are checked first. "
                        "Warnings are returned but do not fail the command."
                    ),
                    "default": True,
                },
                "apply_template": {
                    "type": "boolean",
                    "description": (
                        "Optional. Default true. "
                        "Deploy the embedded rules_template into the project: "
                        ".cursor/agents/*.md, .cursor/rules/project_canonical.mdc, "
                        "docs/PROJECT_RULES.md, docs/agents/*.md, "
                        "README.md, scripts/.gitkeep. "
                        "Warnings are returned but do not fail the command."
                    ),
                    "default": True,
                },
                "template_path": {
                    "type": "string",
                    "description": (
                        "Optional. Path to an external rules_template zip. "
                        "If not provided, the embedded template is used."
                    ),
                },
                "python_executable": {
                    "type": "string",
                    "description": (
                        "Optional. Python interpreter for venv creation. "
                        "Default: 'python3'."
                    ),
                    "default": "python3",
                },
            },
            "required": ["watch_dir_id", "project_name", "description"],
            "additionalProperties": False,
        }

    def validate_params(
        self: "CreateProjectMCPCommand", params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate params and reject unknown watch_dir_id before execution."""
        params = super().validate_params(params)
        BaseMCPCommand._validate_watch_dir_id_exists(params["watch_dir_id"])
        return params

    async def execute(
        self: "CreateProjectMCPCommand",
        watch_dir_id: str,
        project_name: str,
        description: str,
        project_id: Optional[str] = None,
        use_existing_dir: bool = False,
        create_venv: bool = True,
        apply_template: bool = True,
        template_path: Optional[str] = None,
        python_executable: str = "python3",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute create project command.

        Steps:
        1. Create project (projectid file + DB registration).
        2. Scaffold standard directories (tests/, docs/plans/, etc.).
        3. Optionally create .venv.
        4. Optionally deploy rules_template.

        Args:
            self: Command instance.
            watch_dir_id: Watch directory ID from watch_dirs table.
            project_name: Name of project subdirectory to create.
            description: Project description (required).
            project_id: Optional project ID (UUID4).
            use_existing_dir: If True, create only projectid in existing dir.
            create_venv: If True (default), create .venv virtual environment.
            apply_template: If True (default), deploy embedded rules_template.
            template_path: Path to external template zip (overrides embedded).
            python_executable: Python interpreter for venv. Default 'python3'.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with project_id and bootstrap details,
            or ErrorResult on failure.
        """
        try:
            database = self._open_database_from_config(auto_analyze=False)
            try:
                from ..project_creation import CreateProjectCommand

                cmd = CreateProjectCommand(
                    database=database,
                    watch_dir_id=watch_dir_id,
                    project_name=project_name,
                    description=description,
                    project_id=project_id,
                    use_existing_dir=use_existing_dir,
                    scaffold=False,
                    create_venv=False,
                )
                result = await cmd.execute()

                if not result.get("success"):
                    error_code = result.get("error", "CREATE_PROJECT_ERROR")
                    return self._handle_error(
                        ValidationError(
                            result.get("message", "Failed to create project"),
                            field="project_name",
                            details=result,
                        ),
                        error_code,
                        "create_project",
                    )
            finally:
                database.disconnect()

            # ── Bootstrap steps ─────────────────────────────────────
            import pathlib
            from ..project_creation import CreateProjectCommand  # noqa: F811

            # Resolve project root from watch_dir path + project_name.
            # watch_dir_id is in the DB; we can get the path from result.
            project_root_str = result.get("project_root") or result.get("project_path")
            bootstrap_warnings: List[str] = []

            if project_root_str:
                project_root = pathlib.Path(project_root_str)
            elif result.get("project_id"):
                project_root = BaseMCPCommand._resolve_project_root(
                    result["project_id"]
                )
            else:
                project_root = None
            gitignore_result: Dict[str, Any] = {"success": False, "skipped": True}
            git_init_result: Dict[str, Any] = {"success": False, "skipped": True}

            if project_root is not None and project_root.is_dir():
                from ...core.project_bootstrap import (
                    DirScaffold,
                    GitignoreBootstrap,
                    TemplateDeployer,
                    VenvCreator,
                )

                # 1. Standard directory layout
                scaffold = DirScaffold(project_root)
                scaffold_result = scaffold.scaffold()
                if not scaffold_result.success:
                    bootstrap_warnings.extend(
                        f"scaffold: {e}" for e in scaffold_result.errors
                    )

                # 2. .venv virtual environment
                if create_venv:
                    venv = VenvCreator(
                        project_root, python_executable=python_executable
                    )
                    venv_result = venv.create()
                    if not venv_result.success:
                        bootstrap_warnings.append(f"venv: {venv_result.message}")
                    if venv_result.errors:
                        bootstrap_warnings.extend(
                            f"venv_warn: {e}" for e in venv_result.errors
                        )

                # 3. rules_template deployment
                if apply_template:
                    tpl_path = pathlib.Path(template_path) if template_path else None
                    deployer = TemplateDeployer(project_root, tpl_path)
                    deploy_result = deployer.deploy()
                    if not deploy_result.success:
                        bootstrap_warnings.extend(
                            f"template: {e}" for e in deploy_result.errors
                        )

                gitignore = GitignoreBootstrap(project_root)
                gitignore_bootstrap_result = gitignore.ensure()
                gitignore_result = {
                    "success": gitignore_bootstrap_result.success,
                    "path": gitignore_bootstrap_result.path,
                    "created": gitignore_bootstrap_result.created,
                    "appended": gitignore_bootstrap_result.appended,
                    "skipped": gitignore_bootstrap_result.skipped,
                    "errors": gitignore_bootstrap_result.errors,
                }
                if not gitignore_bootstrap_result.success:
                    bootstrap_warnings.extend(
                        f"gitignore: {e}" for e in gitignore_bootstrap_result.errors
                    )

                try:
                    from ...core.git_integration import is_git_available
                    from ...core.git_remote_ops import run_git_subprocess

                    if is_git_available():
                        resolved_project_root = project_root.resolve()
                        returncode, stdout, stderr, timed_out = run_git_subprocess(
                            ["git", "init", str(resolved_project_root)],
                            cwd=resolved_project_root,
                            env=None,
                            timeout_seconds=30.0,
                        )
                        git_init_result = {
                            "success": returncode == 0 and not timed_out,
                            "skipped": False,
                            "returncode": returncode,
                            "timed_out": timed_out,
                            "stdout": stdout.strip(),
                            "stderr": stderr.strip(),
                        }
                        if timed_out:
                            bootstrap_warnings.append("git_init: git init timed out")
                        elif returncode != 0:
                            bootstrap_warnings.append(
                                f"git_init: git init failed: {stderr.strip()}"
                            )
                    else:
                        bootstrap_warnings.append(
                            "git_init: git executable not available"
                        )
                except Exception as e:
                    git_init_result = {
                        "success": False,
                        "skipped": False,
                        "error": str(e),
                    }
                    bootstrap_warnings.append(f"git_init: {e}")
            else:
                bootstrap_warnings.append(
                    "project_root not found; skipped bootstrap steps"
                )

            return SuccessResult(
                data={
                    "success": True,
                    "project_id": result.get("project_id"),
                    "already_existed": result.get("already_existed", False),
                    "description": description,
                    "watch_dir_id": watch_dir_id,
                    "project_root": str(project_root) if project_root else None,
                    "gitignore": gitignore_result,
                    "git_initialized": bool(git_init_result.get("success")),
                    "git_init": git_init_result,
                    "bootstrap_warnings": bootstrap_warnings,
                    "bootstrap_report": result.get("bootstrap_report"),
                },
                message=result.get("message", "Project created successfully"),
            )
        except Exception as e:
            return self._handle_error(e, "CREATE_PROJECT_ERROR", "create_project")

    @classmethod
    def metadata(cls: type["CreateProjectMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The create_project command creates or registers a new project in the system. "
                "It validates prerequisites, creates a projectid file with UUID4 identifier, "
                "registers the project in the database, performs bootstrap steps, "
                "and initializes git in the project directory.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Gets or creates watch_dir_id for watched_dir:\n"
                "   - Searches for existing watch_dir by normalized path\n"
                "   - If found: Uses existing watch_dir_id\n"
                "   - If not found: Creates new watch_dir and watch_dir_path entries\n"
                "4. Validates watched_dir exists and is a directory\n"
                "5. Checks if watched_dir contains projectid file (raises error if found)\n"
                "6. Validates project_dir exists and is a directory\n"
                "7. Checks if project_dir is already registered in database:\n"
                "   - If registered: Updates watch_dir_id if needed, returns existing project info (already_existed=True)\n"
                "   - If not registered: Continues to creation\n"
                "8. Checks if projectid file exists in project_dir:\n"
                "   - If exists and valid: Registers in database using existing ID with watch_dir_id\n"
                "   - If exists but invalid: Recreates projectid file\n"
                "   - If not exists: Creates new projectid file with UUID4\n"
                "9. Registers project in database with watch_dir_id\n"
                "10. Runs bootstrap steps: standard directories, optional .venv, optional template\n"
                "11. Creates .gitignore when absent, or appends missing default ignore entries "
                "for Python and code_analysis service artifacts when the file already exists\n"
                "12. Runs git init for the resolved project root. Native git behavior applies: "
                "missing .git is created, and an existing repository is reinitialized successfully. "
                "If git is unavailable or git init fails, project creation still succeeds and the "
                "issue is returned in bootstrap_warnings and git_init.\n"
                "13. Returns project information including watch_dir_id, .gitignore status, "
                "and git initialization status\n\n"
                "Project ID File Format:\n"
                "The projectid file is created in JSON format:\n"
                "{\n"
                '  "id": "550e8400-e29b-41d4-a716-446655440000",\n'
                '  "description": "Human readable description"\n'
                "}\n\n"
                "Validation Rules:\n"
                "- watched_dir must exist and be a directory\n"
                "- watched_dir must NOT contain projectid file\n"
                "- project_dir must exist and be a directory\n"
                "- project_dir must NOT be already registered in database (unless projectid exists)\n"
                "- description is optional (defaults to project directory name)\n\n"
                "Return Values:\n"
                "- project_id: UUID4 identifier of the project\n"
                "- already_existed: True if project was already registered, False if newly created\n"
                "- description: Project description (from file if existed, or provided)\n"
                "- old_description: Previous description if projectid file was recreated\n"
                "- watch_dir_id: UUID4 identifier of the watch directory (project is linked to this watch_dir)\n"
                "- gitignore: .gitignore creation/update status\n"
                "- git_initialized: True when automatic git init completed successfully\n"
                "- git_init: stdout/stderr/returncode details from automatic git init\n"
                "- message: Status message\n\n"
                "Use cases:\n"
                "- Register a new project for code analysis\n"
                "- Register an existing project that has projectid file but not in database\n"
                "- Create a new project from scratch\n"
                "- Re-register a project after database cleanup\n\n"
                "Option use_existing_dir (default false = old behaviour):\n"
                "- use_existing_dir=false (default): if the project directory already exists and is not "
                "registered, the command fails with PROJECT_DIR_EXISTS (same as before this option existed).\n"
                "- use_existing_dir=true: if the project directory already exists, the command creates "
                "only the projectid file (id + description) in that directory and registers the project in "
                "the database. Use this to register an existing folder without creating a new directory.\n\n"
                "Git initialization:\n"
                "- create_project creates or updates .gitignore before git initialization.\n"
                "- The default .gitignore covers Python caches, venvs, build outputs, logs, .env files, "
                "old_code, backups, versions, trash, *.tree, .cst, and .trees artifacts.\n"
                "- create_project automatically runs git init for the resolved project root.\n"
                "- If the directory is already a git repository, native git behavior reinitializes it successfully.\n"
                "- If git is unavailable or git init fails, project creation still succeeds and the issue is reported "
                "in bootstrap_warnings and git_init."
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Server root directory path. Contains config.json and data/code_analysis.db. "
                        "Can be absolute or relative. Used to locate database."
                    ),
                    "type": "string",
                    "required": True,
                },
                "watched_dir": {
                    "description": (
                        "Watched directory path. Must exist and be a directory. "
                        "Must NOT contain projectid file. This is the parent directory "
                        "that will be monitored for projects. Project will be linked to this watch_dir "
                        "via watch_dir_id. If watch_dir doesn't exist in database, it will be created. "
                        "Can be absolute or relative."
                    ),
                    "type": "string",
                    "required": True,
                },
                "project_dir": {
                    "description": (
                        "Project directory path. Must exist and be a directory. "
                        "If already registered in database, returns existing project info. "
                        "If projectid file exists, uses its ID. Otherwise creates new project. "
                        "Can be absolute or relative."
                    ),
                    "type": "string",
                    "required": True,
                },
                "description": {
                    "description": (
                        "Human-readable description of the project. Optional. "
                        "If projectid file already exists, its description takes precedence. "
                        "If not provided and no existing description, defaults to project directory name."
                    ),
                    "type": "string",
                    "required": False,
                    "default": "",
                },
                "use_existing_dir": {
                    "description": (
                        "Default false (old behaviour). If true: when project directory already exists, "
                        "create only projectid file and register; do not fail with PROJECT_DIR_EXISTS."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Register existing directory (use_existing_dir=true)",
                    "command": {
                        "watch_dir_id": "550e8400-e29b-41d4-a716-446655440001",
                        "project_name": "vast_srv",
                        "description": "AI Admin",
                        "use_existing_dir": True,
                    },
                    "explanation": (
                        "When the folder watch_dir/vast_srv already exists, creates projectid file with "
                        "description and registers the project without failing with PROJECT_DIR_EXISTS."
                    ),
                },
                {
                    "description": "Create new project",
                    "command": {
                        "root_dir": "/home/user/projects/tools/code_analysis",
                        "watched_dir": "/home/user/projects/test_data",
                        "project_dir": "/home/user/projects/test_data/my_project",
                        "description": "My new project for testing",
                    },
                    "explanation": (
                        "Creates a new project in /home/user/projects/test_data/my_project. "
                        "Creates projectid file with UUID4 and registers in database."
                    ),
                },
                {
                    "description": "Register existing project with projectid file",
                    "command": {
                        "root_dir": "/home/user/projects/tools/code_analysis",
                        "watched_dir": "/home/user/projects/test_data",
                        "project_dir": "/home/user/projects/test_data/existing_project",
                    },
                    "explanation": (
                        "Registers an existing project that already has projectid file. "
                        "Uses existing project ID from file."
                    ),
                },
                {
                    "description": "Get existing project info",
                    "command": {
                        "root_dir": "/home/user/projects/tools/code_analysis",
                        "watched_dir": "/home/user/projects/test_data",
                        "project_dir": "/home/user/projects/test_data/registered_project",
                    },
                    "explanation": (
                        "If project is already registered in database, returns existing project info "
                        "without creating new projectid file."
                    ),
                },
            ],
            "error_cases": {
                "WATCHED_DIR_NOT_FOUND": {
                    "description": "Watched directory does not exist",
                    "example": "watched_dir='/path/to/missing'",
                    "solution": "Verify watched directory path exists and is accessible.",
                },
                "WATCHED_DIR_NOT_DIRECTORY": {
                    "description": "Watched path is not a directory",
                    "example": "watched_dir='/path/to/file.txt'",
                    "solution": "Ensure watched_dir points to a directory, not a file.",
                },
                "PROJECTID_EXISTS_IN_WATCHED_DIR": {
                    "description": "Watched directory already contains projectid file",
                    "example": "watched_dir='/path' contains projectid file",
                    "solution": (
                        "Watched directory should not contain projectid file. "
                        "Use a parent directory as watched_dir, or remove projectid file if not needed."
                    ),
                },
                "PROJECT_DIR_NOT_FOUND": {
                    "description": "Project directory does not exist",
                    "example": "project_dir='/path/to/missing'",
                    "solution": "Verify project directory path exists and is accessible.",
                },
                "PROJECT_DIR_NOT_DIRECTORY": {
                    "description": "Project path is not a directory",
                    "example": "project_dir='/path/to/file.txt'",
                    "solution": "Ensure project_dir points to a directory, not a file.",
                },
                "PROJECT_DIR_EXISTS": {
                    "description": (
                        "Project directory already exists and use_existing_dir was not set. "
                        "Set use_existing_dir=true to create only projectid file and register."
                    ),
                    "example": "project_name='vast_srv' but test_data/vast_srv already exists",
                    "solution": "Pass use_existing_dir=true to register the existing directory.",
                },
                "PROJECTID_WRITE_ERROR": {
                    "description": "Failed to write projectid file",
                    "example": "Permission denied or disk full",
                    "solution": (
                        "Check file permissions, ensure directory is writable, "
                        "verify disk space is available."
                    ),
                },
                "DATABASE_REGISTRATION_ERROR": {
                    "description": "Failed to register project in database",
                    "example": "Database locked, constraint violation, or connection error",
                    "solution": (
                        "Check database integrity, ensure database is not locked, "
                        "verify database connection is working."
                    ),
                },
                "WATCH_DIR_ERROR": {
                    "description": "Failed to get or create watch_dir for watched_dir",
                    "example": "Error during watch_dir lookup or creation",
                    "solution": "Check database connection and permissions. Verify watched_dir path is valid.",
                },
                "CREATE_PROJECT_ERROR": {
                    "description": "General error during project creation",
                    "example": "Unexpected error in validation or creation process",
                    "solution": "Check error message for specific details and resolve accordingly.",
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "success": "Whether operation was successful (always True)",
                        "project_id": "UUID4 identifier of the project",
                        "already_existed": "Whether project was already registered (True) or newly created (False)",
                        "description": "Project description (from file if existed, or provided)",
                        "old_description": "Previous description if projectid file was recreated, empty otherwise",
                        "watch_dir_id": "UUID4 identifier of the watch directory (project is linked to this watch_dir)",
                        "message": "Status message",
                    },
                    "example_new": {
                        "success": True,
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "already_existed": False,
                        "description": "My new project",
                        "old_description": "",
                        "watch_dir_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "message": "Created and registered new project: 550e8400-e29b-41d4-a716-446655440000",
                    },
                    "example_existing": {
                        "success": True,
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "already_existed": True,
                        "description": "Existing project description",
                        "old_description": "Previous description",
                        "watch_dir_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "message": "Project already registered: 928bcf10-db1c-47a3-8341-f60a6d997fe7",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., WATCHED_DIR_NOT_FOUND, PROJECTID_EXISTS_IN_WATCHED_DIR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Ensure watched_dir exists and does not contain projectid file",
                "Project will be automatically linked to watched_dir via watch_dir_id",
                "If watch_dir doesn't exist in database, it will be created automatically",
                "Use descriptive project descriptions for better organization",
                "If project already has projectid file, it will be used (not recreated)",
                "If project is already registered, command updates watch_dir_id if needed and returns existing info",
                "Always check already_existed flag to know if project was created or already existed",
                "watch_dir_id is returned in response and can be used for CST commands",
            ],
        }
