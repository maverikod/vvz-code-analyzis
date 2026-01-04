"""
MCP command: rebuild_faiss_index.

Rebuild the FAISS index file from embeddings stored in SQLite.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ...core.faiss_manager import FaissIndexManager

logger = logging.getLogger(__name__)


class RebuildFaissCommand(BaseMCPCommand):
    """
    Rebuild FAISS index file from database embeddings.

    The SQLite database is the source of truth for embedding vectors
    (`code_chunks.embedding_vector`). This command recreates the FAISS index file
    and rewrites `code_chunks.vector_id` to a dense range so FAISS ids match DB.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Description.
        category: Command category.
        author: Author name.
        email: Author email.
        use_queue: Whether the command is executed via queue.
    """

    name = "rebuild_faiss_index"
    version = "1.0.0"
    descr = "Rebuild FAISS index file from embeddings stored in SQLite database"
    category = "vector"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @classmethod
    def get_schema(cls: type["RebuildFaissCommand"]) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema describing command parameters.
        """

        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "description": "Rebuild FAISS index file from database embeddings.",
            "properties": {
                **base_props,
                "file_path": {
                    "type": "string",
                    "description": "Optional override path to FAISS index file (absolute or relative to root_dir).",
                },
                "vector_dim": {
                    "type": "integer",
                    "description": "Optional override vector dimension (default: config value or 384).",
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self: "RebuildFaissCommand",
        root_dir: str,
        file_path: Optional[str] = None,
        vector_dim: Optional[int] = None,
        project_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute rebuild operation.

        Args:
            self: Command instance.
            root_dir: Project root directory.
            file_path: Optional override FAISS index path.
            vector_dim: Optional override embedding dimension.
            project_id: Optional project UUID (not used; rebuild is global within DB).
            **kwargs: Extra args (ignored).

        Returns:
            SuccessResult with rebuild stats or ErrorResult.
        """

        _ = kwargs
        _ = project_id

        root_path = self._validate_root_dir(root_dir)

        # Read config.json for default faiss_index_path and vector_dim
        config_path = root_path / "config.json"
        cfg: dict[str, Any] = {}
        if config_path.exists():
            try:
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception as e:
                return ErrorResult(
                    message=f"Failed to parse config.json: {e}",
                    code="CONFIG_ERROR",
                )

        code_analysis_cfg = cfg.get("code_analysis", cfg)
        cfg_vector_dim = int(code_analysis_cfg.get("vector_dim", 384))
        cfg_index_path = str(
            code_analysis_cfg.get("faiss_index_path", "data/faiss_index.bin")
        )

        eff_vector_dim = int(vector_dim or cfg_vector_dim)

        eff_index_path = Path(file_path) if file_path else Path(cfg_index_path)
        if not eff_index_path.is_absolute():
            eff_index_path = root_path / eff_index_path

        try:
            db = self._open_database(root_dir)
        except Exception as e:
            return ErrorResult(message=f"Failed to open database: {e}", code="DB_ERROR")

        try:
            # Ensure the project exists (mainly for consistent behavior with other commands)
            proj_id = self._get_project_id(db, root_path, None)
            if not proj_id:
                return ErrorResult(
                    message="Project not found", code="PROJECT_NOT_FOUND"
                )

            faiss_manager = FaissIndexManager(
                index_path=str(eff_index_path),
                vector_dim=eff_vector_dim,
            )
            vectors_loaded = await faiss_manager.rebuild_from_database(db)

            # Reload to validate
            faiss_manager._load_index()
            stats = faiss_manager.get_stats()

            return SuccessResult(
                data={
                    "index_path": str(eff_index_path),
                    "vector_dim": eff_vector_dim,
                    "vectors_loaded": int(vectors_loaded),
                    "faiss_stats": stats,
                }
            )
        finally:
            try:
                db.close()
            except Exception:
                pass
