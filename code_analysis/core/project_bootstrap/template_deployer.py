"""
Template deployer for project bootstrap.

Deploys the rules_template into a new project directory and substitutes
project-specific values into selected files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""
from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Optional

from .template_data import TEMPLATE_FILES, TEMPLATE_ZIP_BYTES

logger = logging.getLogger(__name__)
@dataclass
class DeployResult:
    """Result of template deployment.

    Attributes:
        success: True if no errors occurred during deployment.
        deployed: Relative paths that were written.
        skipped: Relative paths that already existed and were skipped.
        errors: Error messages for files that could not be written.
        message: Human-readable summary.
    """

    success: bool
    deployed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    message: str = ""
class TemplateDeployer:
    """Deploys the rules_template into a new project directory.

    Source priority:
    1. external zip at template_path (if given)
    2. docs/rules_template/ directory on disk (relative to this package)
    3. embedded TEMPLATE_ZIP_BYTES (non-empty)
    4. embedded TEMPLATE_FILES dict

    Files are never overwritten by default; set overwrite=True to replace.
    After deploying, project_params are substituted into selected files.
    """

    _PARAM_FILES = frozenset({
        "docs/PROJECT_RULES.md",
        "docs/agents/project_overlay.md",
        "README.md",
    })

    def __init__(
        self,
        project_root: Path,
        template_path: Optional[Path] = None,
        project_params: Optional[dict] = None,
    ) -> None:
        """Initialise TemplateDeployer.

        Args:
            project_root: Absolute path to the new project directory.
            template_path: Optional external zip. If None, tries
                           docs/rules_template/ on disk, then embedded data.
            project_params: Values injected into selected template files.

                Recognised keys: project_name, project_slug, description,
                package_root, author, email, use_code_map, chat_locale.
        """
        self.project_root = Path(project_root)
        self.template_path = Path(template_path) if template_path else None
        self.project_params: dict = project_params or {}

    def deploy(self, overwrite: bool = False) -> DeployResult:
        """Deploy template files into the project root.

        Args:
            overwrite: If True, overwrite existing files.

        Returns:
            DeployResult with lists of deployed / skipped / errored paths.
        """
        if self.template_path is not None:
            result = self._deploy_from_zip(self.template_path, overwrite)
        else:
            disk_tpl = self._find_disk_template()
            if disk_tpl is not None:
                result = self._deploy_from_dir(disk_tpl, overwrite)
            elif TEMPLATE_ZIP_BYTES:
                result = self._deploy_from_zip_bytes(TEMPLATE_ZIP_BYTES, overwrite)
            else:
                result = self._deploy_from_dict(overwrite)
        if self.project_params and result.deployed:
            self._apply_project_params(result)
        return result

    def _find_disk_template(self) -> Optional[Path]:
        """Return path to docs/rules_template/ relative to repo root.

        Returns:
            Path to the on-disk template directory, or None if not found.
        """
        try:
            repo_root = Path(__file__).resolve().parents[3]
            candidate = repo_root / "docs" / "rules_template"
            if candidate.is_dir():
                logger.debug("Using on-disk template at %s", candidate)
                return candidate
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not resolve disk template: %s", exc)
        return None

    def _deploy_from_dir(self, tpl_dir: Path, overwrite: bool) -> DeployResult:
        """Deploy from a directory tree on disk.

        Args:
            tpl_dir: Root of the template directory.
            overwrite: If True, overwrite existing target files.

        Returns:
            DeployResult with outcome details.
        """
        deployed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []
        for src in sorted(tpl_dir.rglob("*")):
            if src.is_dir():
                continue
            rel = src.relative_to(tpl_dir).as_posix()
            try:
                content = src.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{rel}: read error: {exc}")
                continue
            res = self._write_file(rel, content, overwrite)
            if res == "deployed":
                deployed.append(rel)
            elif res == "skipped":
                skipped.append(rel)
            else:
                errors.append(f"{rel}: {res}")
        return self._make_result(deployed, skipped, errors)

    def _deploy_from_dict(self, overwrite: bool) -> DeployResult:
        """Deploy from the embedded TEMPLATE_FILES dict.

        Args:
            overwrite: If True, overwrite existing target files.

        Returns:
            DeployResult with outcome details.
        """
        deployed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []
        for rel_path, content in TEMPLATE_FILES.items():
            result = self._write_file(rel_path, content, overwrite)
            if result == "deployed":
                deployed.append(rel_path)
            elif result == "skipped":
                skipped.append(rel_path)
            else:
                errors.append(f"{rel_path}: {result}")
        return self._make_result(deployed, skipped, errors)

    def _deploy_from_zip(self, zip_path: Path, overwrite: bool) -> DeployResult:
        """Deploy from an external zip file.

        Args:
            zip_path: Path to the zip archive.
            overwrite: If True, overwrite existing target files.

        Returns:
            DeployResult with outcome details.
        """
        deployed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []
        try:
            with zipfile.ZipFile(zip_path) as zf:
                for name in zf.namelist():
                    if name.endswith("/"):
                        continue
                    rel = self._strip_template_prefix(name)
                    if not rel:
                        continue
                    content = zf.read(name).decode("utf-8", errors="replace")
                    result = self._write_file(rel, content, overwrite)
                    if result == "deployed":
                        deployed.append(rel)
                    elif result == "skipped":
                        skipped.append(rel)
                    else:
                        errors.append(f"{rel}: {result}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Failed to open zip {zip_path}: {exc}")
        return self._make_result(deployed, skipped, errors)

    def _deploy_from_zip_bytes(self, zip_bytes: bytes, overwrite: bool) -> DeployResult:
        """Deploy from embedded zip bytes.

        Args:
            zip_bytes: Raw bytes of a zip archive.
            overwrite: If True, overwrite existing target files.

        Returns:
            DeployResult with outcome details.
        """
        deployed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []
        try:
            with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
                for name in zf.namelist():
                    if name.endswith("/"):
                        continue
                    rel = self._strip_template_prefix(name)
                    if not rel:
                        continue
                    content = zf.read(name).decode("utf-8", errors="replace")
                    result = self._write_file(rel, content, overwrite)
                    if result == "deployed":
                        deployed.append(rel)
                    elif result == "skipped":
                        skipped.append(rel)
                    else:
                        errors.append(f"{rel}: {result}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Failed to read embedded zip: {exc}")
        return self._make_result(deployed, skipped, errors)

    def _apply_project_params(self, result: DeployResult) -> None:
        """Rewrite deployed param-files substituting project_params values.

        Args:
            result: DeployResult from the deploy step; modified in place.
        """
        p = self.project_params
        project_name: str = p.get("project_name") or p.get("project_slug") or ""
        project_slug: str = p.get("project_slug") or project_name
        description: str = p.get("description") or project_name
        package_root: str = (
            p.get("package_root") or (f"{project_slug}/" if project_slug else "")
        )
        ctx = {
            "project_name": project_name,
            "project_slug": project_slug,
            "description": description,
            "package_root": package_root,
            "author": p.get("author") or "Vasiliy Zdanovskiy",
            "email": p.get("email") or "vasilyvz@gmail.com",
            "use_code_map": p.get("use_code_map") or "no",
            "chat_locale": p.get("chat_locale") or "ru",
        }
        for rel in list(result.deployed):
            if rel not in self._PARAM_FILES:
                continue
            target = self.project_root / rel
            if not target.exists():
                continue
            try:
                original = target.read_text(encoding="utf-8")
                patched = self._patch_file(rel, original, ctx)
                if patched != original:
                    target.write_text(patched, encoding="utf-8")
                    logger.info("Applied project params to %s", target)
            except Exception as exc:  # noqa: BLE001
                msg = f"param_patch:{rel}: {exc}"
                logger.warning(msg)
                result.errors.append(msg)

    @staticmethod
    def _patch_file(rel: str, content: str, ctx: dict) -> str:
        """Dispatch to the per-file patcher.

        Args:
            rel: Relative path of the file.
            content: Current file content.
            ctx: Substitution context.

        Returns:
            Patched content string.
        """
        if rel == "docs/PROJECT_RULES.md":
            return TemplateDeployer._patch_project_rules(content, ctx)
        if rel == "docs/agents/project_overlay.md":
            return TemplateDeployer._patch_overlay(content, ctx)
        if rel == "README.md":
            return TemplateDeployer._patch_readme(content, ctx)
        return content

    @staticmethod
    def _patch_project_rules(content: str, ctx: dict) -> str:
        """Fill section 7 table in PROJECT_RULES.md with actual project values.

        Args:
            content: Full file content.
            ctx: Substitution context.

        Returns:
            Patched content string.
        """
        import re
        slug = ctx["project_slug"] or ctx["project_name"]
        table_subs = [
            (r"(\| `PROJECT_SLUG` \| )`[^`]+`", f"| `PROJECT_SLUG` | `{slug}`"),
            (r"(\| `PACKAGE_ROOT` \| )`[^`]+`", f"| `PACKAGE_ROOT` | `{ctx['package_root']}`"),
            (r"(\| `HEADER_AUTHOR` \| )`[^`]+`", f"| `HEADER_AUTHOR` | `{ctx['author']}`"),
            (r"(\| `HEADER_EMAIL` \| )`[^`]+`", f"| `HEADER_EMAIL` | `{ctx['email']}`"),
            (r"(\| `USE_CODE_MAP` \| )`[^`]+`", f"| `USE_CODE_MAP` | `{ctx['use_code_map']}`"),
            (r"(\| `CHAT_LOCALE` \| )`[^`]+`", f"| `CHAT_LOCALE` | `{ctx['chat_locale']}`"),
        ]
        for pattern, replacement in table_subs:
            content = re.sub(pattern, replacement, content)
        return content

    @staticmethod
    def _patch_overlay(content: str, ctx: dict) -> str:
        """Substitute project name and description into project_overlay.md.

        Args:
            content: Full file content.
            ctx: Substitution context.

        Returns:
            Patched content string.
        """
        import re
        slug = ctx["project_slug"] or ctx["project_name"]
        if slug:
            content = re.sub(
                r"# Project overlay \u2014 `[^`]+`",
                f"# Project overlay \u2014 `{slug}`",
                content,
            )
        desc = ctx["description"]
        if desc:
            content = re.sub(
                r"(## Functional context\n+- \*\*Role:\*\* )[^\n]+",
                rf"\g<1>{desc}.",
                content,
            )
        return content

    @staticmethod
    def _patch_readme(content: str, ctx: dict) -> str:
        """Replace the generic H1 title with the project name.

        Args:
            content: Full file content.
            ctx: Substitution context.

        Returns:
            Patched content string.
        """
        import re
        slug = ctx["project_slug"] or ctx["project_name"]
        if not slug:
            return content
        return re.sub(
            r"^# Rules bundle.*$",
            f"# {slug}",
            content,
            count=1,
            flags=re.MULTILINE,
        )

    def _write_file(self, rel_path: str, content: str, overwrite: bool) -> str:
        """Write a single file to the project root.

        Args:
            rel_path: Relative path inside project_root.
            content: Text content to write.
            overwrite: If True, replace existing file.

        Returns:
            'deployed', 'skipped', or an error message string.
        """
        target = self.project_root / rel_path
        try:
            if target.exists() and not overwrite:
                logger.debug("Skipping existing file: %s", target)
                return "skipped"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            logger.info("Deployed: %s", target)
            return "deployed"
        except Exception as exc:  # noqa: BLE001
            return str(exc)

    @staticmethod
    def _strip_template_prefix(name: str) -> str:
        """Strip the first path component from a zip entry name.

        Args:
            name: Zip entry name, e.g. 'rules_template/docs/foo.md'.

        Returns:
            Path without the leading directory, e.g. 'docs/foo.md'.
        """
        parts = name.split("/", 1)
        if len(parts) == 2:
            return parts[1]
        return name

    @staticmethod
    def _make_result(
        deployed: list[str],
        skipped: list[str],
        errors: list[str],
    ) -> DeployResult:
        """Build a DeployResult from the three outcome lists.

        Args:
            deployed: Paths successfully written.
            skipped: Paths skipped (already existed).
            errors: Error messages.

        Returns:
            DeployResult with success flag and human-readable message.
        """
        parts = []
        if deployed:
            parts.append(f"deployed {len(deployed)} files")
        if skipped:
            parts.append(f"skipped {len(skipped)} existing")
        if errors:
            parts.append(f"{len(errors)} errors")
        return DeployResult(
            success=len(errors) == 0,
            deployed=deployed,
            skipped=skipped,
            errors=errors,
            message="; ".join(parts) if parts else "nothing to deploy",
        )
