"""
MCP commands for FAISS rebuild and selective re-vectorization.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult
from mcp_proxy_adapter.config import get_config as get_adapter_config

from ..core.database import CodeDatabase
from ..core.config import ServerConfig
from ..core.svo_client_manager import SVOClientManager
from ..core.faiss_manager import FaissIndexManager
from ..core.docstring_chunker import DocstringChunker

logger = logging.getLogger(__name__)


def _load_server_config() -> ServerConfig:
    adapter_config = get_adapter_config()
    adapter_config_data = getattr(adapter_config, "config_data", {}) if adapter_config else {}
    code_analysis_config = adapter_config_data.get("code_analysis", {})
    return ServerConfig(**code_analysis_config) if code_analysis_config else ServerConfig()


def _open_database(root_dir: Path) -> CodeDatabase:
    data_dir = root_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "code_analysis.db"
    return CodeDatabase(db_path)


class RebuildFaissCommand(Command):
    """Rebuild FAISS index from database embeddings."""

    name = "rebuild_faiss"
    version = "1.0.0"
    descr = "Rebuild FAISS index from database for a project"
    category = "vectorization"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root containing data/code_analysis.db",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; inferred from root_dir if omitted",
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(self, root_dir: str, project_id: Optional[str] = None, **kwargs) -> SuccessResult:
        try:
            root_path = Path(root_dir).resolve()
            db = _open_database(root_path)

            proj_id = project_id or db.get_or_create_project(str(root_path), name=root_path.name)
            if not proj_id:
                return ErrorResult(message="Project not found", code="PROJECT_NOT_FOUND")

            server_config = _load_server_config()
            if not server_config.vector_dim:
                return ErrorResult(message="vector_dim not configured", code="INVALID_CONFIG")

            svo_client_manager = SVOClientManager(server_config)
            await svo_client_manager.initialize()

            faiss_path = (
                Path(server_config.faiss_index_path)
                if server_config.faiss_index_path
                else root_path / "data" / "faiss_index"
            )
            faiss_path.parent.mkdir(parents=True, exist_ok=True)
            faiss_manager = FaissIndexManager(str(faiss_path), server_config.vector_dim)

            vectors_count = await faiss_manager.rebuild_from_database(db, svo_client_manager)

            await svo_client_manager.close()
            db.close()

            return SuccessResult(
                data={
                    "success": True,
                    "message": f"FAISS rebuilt from DB, vectors loaded: {vectors_count}",
                    "vectors": vectors_count,
                    "faiss_index_path": str(faiss_path),
                    "vector_dim": server_config.vector_dim,
                }
            )
        except Exception as e:
            logger.exception("Failed to rebuild FAISS: %s", e)
            return ErrorResult(message=f"Failed to rebuild FAISS: {e}", code="REBUILD_FAISS_ERROR")


class RevectorizeCommand(Command):
    """Re-chunk and re-vectorize specific files/directories."""

    name = "revectorize"
    version = "1.0.0"
    descr = "Re-chunk and re-vectorize selected files/directories from scratch"
    category = "vectorization"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root containing data/code_analysis.db",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files or directories to revectorize (relative or absolute). If omitted, all project files are processed.",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; inferred from root_dir if omitted",
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        paths: Optional[List[str]] = None,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            root_path = Path(root_dir).resolve()
            db = _open_database(root_path)
            proj_id = project_id or db.get_or_create_project(str(root_path), name=root_path.name)
            if not proj_id:
                return ErrorResult(message="Project not found", code="PROJECT_NOT_FOUND")

            server_config = _load_server_config()
            if not server_config.vector_dim:
                return ErrorResult(message="vector_dim not configured", code="INVALID_CONFIG")

            svo_client_manager = SVOClientManager(server_config)
            await svo_client_manager.initialize()

            faiss_path = (
                Path(server_config.faiss_index_path)
                if server_config.faiss_index_path
                else root_path / "data" / "faiss_index"
            )
            faiss_path.parent.mkdir(parents=True, exist_ok=True)
            faiss_manager = FaissIndexManager(str(faiss_path), server_config.vector_dim)

            chunker = DocstringChunker(
                database=db,
                svo_client_manager=svo_client_manager,
                faiss_manager=faiss_manager,
                min_chunk_length=server_config.min_chunk_length or 30,
            )

            # Collect targets
            target_files: List[Path] = []
            if paths:
                for p in paths:
                    path_obj = Path(p)
                    if not path_obj.is_absolute():
                        path_obj = root_path / path_obj
                    if path_obj.is_file():
                        target_files.append(path_obj.resolve())
                    elif path_obj.is_dir():
                        for sub in path_obj.rglob("*.py"):
                            target_files.append(sub.resolve())
            else:
                for sub in root_path.rglob("*.py"):
                    target_files.append(sub.resolve())

            processed = 0
            errors = 0

            for file_path in target_files:
                try:
                    if not file_path.exists():
                        continue
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    import ast

                    tree = ast.parse(content, filename=str(file_path))

                    # ensure file entry exists
                    file_rec = db.get_file_by_path(str(file_path), proj_id)
                    if not file_rec:
                        file_id = db.add_file(str(file_path), len(content.splitlines()), file_path.stat().st_mtime, True, proj_id)
                    else:
                        file_id = file_rec["id"]

                    await chunker.process_file(
                        file_id=file_id,
                        project_id=proj_id,
                        file_path=str(file_path),
                        tree=tree,
                        file_content=content,
                    )
                    processed += 1
                except Exception as e:
                    errors += 1
                    logger.error(f"Revectorize failed for {file_path}: {e}", exc_info=True)

            await svo_client_manager.close()
            db.close()

            return SuccessResult(
                data={
                    "success": errors == 0,
                    "processed_files": processed,
                    "errors": errors,
                }
            )
        except Exception as e:
            logger.exception("Revectorize command failed: %s", e)
            return ErrorResult(message=f"Revectorize failed: {e}", code="REVECTORIZE_ERROR")

