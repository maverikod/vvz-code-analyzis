from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Optional

from .template_data import TEMPLATE_FILES, TEMPLATE_ZIP_BYTES

logger = logging.getLogger(__name__)
# @node-id: 2c1e2d18-ecec-4096-a67c-8e0ea53d30b8


@dataclass
class DeployResult:
    """Result of template deployment."""

    success: bool
    deployed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    message: str = ""
# @node-id: 73bd66e4-f7da-4b18-8268-45c0abab4df9


class TemplateDeployer:
    """Deploys the embedded rules_template into a project directory.

    Supports two modes:
    - embedded: uses TEMPLATE_FILES dict (static content)
    - zip: uses TEMPLATE_ZIP_BYTES if template_path is not provided
    - external: uses an external zip at template_path

    Files are never overwritten by default; set overwrite=True to replace.
    """
    # @node-id: 6b1f3295-e48c-4af5-8e70-64f61a91e431

    def __init__(
        self,
        project_root: Path,
        template_path: Optional[Path] = None,
    ) -> None:
        """Initialise TemplateDeployer.

        Args:
            project_root: Absolute path to the new project directory.
            template_path: Optional path to an external zip template.
                           If None, uses the embedded template data.
        """
        self.project_root = Path(project_root)
        self.template_path = Path(template_path) if template_path else None
    # @node-id: aa1ca891-7bdc-4cd8-85aa-3eb1ebaa30a1

    def deploy(self, overwrite: bool = False) -> DeployResult:
        """Deploy template files into the project root.

        Args:
            overwrite: If True, overwrite existing files.

        Returns:
            DeployResult with lists of deployed / skipped / errored paths.
        """
        if self.template_path is not None:
            return self._deploy_from_zip(self.template_path, overwrite)
        if TEMPLATE_ZIP_BYTES:
            return self._deploy_from_zip_bytes(TEMPLATE_ZIP_BYTES, overwrite)
        return self._deploy_from_dict(overwrite)
    # @node-id: be6b5afb-e4b9-411b-adc2-69f1a4150218

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _deploy_from_dict(self, overwrite: bool) -> DeployResult:
        """Deploy from the embedded TEMPLATE_FILES dict."""
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
    # @node-id: 9d4584e1-5aa6-4943-ad04-de22d064823f

    def _deploy_from_zip(self, zip_path: Path, overwrite: bool) -> DeployResult:
        """Deploy from an external zip file."""
        deployed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        try:
            with zipfile.ZipFile(zip_path) as zf:
                for name in zf.namelist():
                    if name.endswith("/"):
                        continue
                    # Strip leading directory prefix (e.g. 'rules_template/')
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
        except Exception as exc:
            errors.append(f"Failed to open zip {zip_path}: {exc}")

        return self._make_result(deployed, skipped, errors)
    # @node-id: 8a8c8e18-6134-4425-93c5-36e408b3552a

    def _deploy_from_zip_bytes(self, zip_bytes: bytes, overwrite: bool) -> DeployResult:
        """Deploy from embedded zip bytes."""
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
        except Exception as exc:
            errors.append(f"Failed to read embedded zip: {exc}")

        return self._make_result(deployed, skipped, errors)
    # @node-id: b8022b33-3bde-45b9-95ad-4930b6025a54

    def _write_file(self, rel_path: str, content: str, overwrite: bool) -> str:
        """Write a single file. Returns 'deployed', 'skipped', or error message."""
        target = self.project_root / rel_path
        try:
            if target.exists() and not overwrite:
                logger.debug("Skipping existing file: %s", target)
                return "skipped"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            logger.info("Deployed: %s", target)
            return "deployed"
        except Exception as exc:
            return str(exc)
    # @node-id: c8739558-d698-4a78-a00d-9724c2e30adb

    @staticmethod
    def _strip_template_prefix(name: str) -> str:
        """Strip the first path component from a zip entry name."""
        parts = name.split("/", 1)
        if len(parts) == 2:
            return parts[1]
        return name
    # @node-id: a8407336-ea06-4778-ad06-29ba64bee0f4

    @staticmethod
    def _make_result(
        deployed: list[str],
        skipped: list[str],
        errors: list[str],
    ) -> DeployResult:
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
